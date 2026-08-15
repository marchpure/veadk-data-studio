import pytest

from server.schemas.query import QueryFilter
from server.services.database_operations import AsyncMongoConnector, DatabaseOperationsService, MongoConnector


class DummyCursor:
    def __init__(self, data):
        self.data = list(data)
        self.calls = []

    def sort(self, spec):
        self.calls.append(("sort", spec))
        return self

    def limit(self, value):
        self.calls.append(("limit", value))
        return self

    def skip(self, value):
        self.calls.append(("skip", value))
        return self

    def project(self, value):
        self.calls.append(("project", value))
        return self

    def collation(self, value):
        self.calls.append(("collation", value))
        return self

    def hint(self, value):
        self.calls.append(("hint", value))
        return self

    async def to_list(self, length=None):
        self.calls.append(("to_list", length))
        if length is None:
            return list(self.data)
        return list(self.data)[:length]


class DummyCollection:
    def __init__(self, data):
        self.data = data
        self.filter_used = None
        self.last_cursor = None
        self.aggregate_pipeline = None
        self.aggregate_options = None

    def __getitem__(self, name):
        return self

    def find(self, *args):
        if args:
            self.filter_used = args[0]
        self.last_cursor = DummyCursor(self.data)
        return self.last_cursor

    async def find_one(self, *args, **kwargs):
        return None

    async def count_documents(self, filter_doc):
        self.filter_used = filter_doc
        return 100

    async def distinct(self, *args, **kwargs):
        return ["a", "b"]

    def aggregate(self, pipeline, **options):
        self.aggregate_pipeline = pipeline
        self.aggregate_options = options
        self.last_cursor = DummyCursor(self.data)
        return self.last_cursor

    async def estimated_document_count(self):
        return 42


class DummyClient:
    def __init__(self, collection):
        self._collection = collection

    def __getitem__(self, name):
        return self._collection


def _contains_key_recursive(value, key: str) -> bool:
    if isinstance(value, dict):
        if key in value:
            return True
        return any(_contains_key_recursive(v, key) for v in value.values())
    if isinstance(value, list):
        return any(_contains_key_recursive(item, key) for item in value)
    return False


def test_parse_find_with_modifiers():
    connector = MongoConnector({})
    query = 'db.users.find({"active": true}, {"name": 1}).sort({"createdAt": -1}).limit(25)'

    parsed = connector._parse_query(query)

    assert parsed["collection"] == "users"
    assert parsed["operation"] == "find"
    assert parsed["args"][0]["active"] is True
    assert parsed["args"][1]["name"] == 1
    assert parsed["modifiers"] == [
        {"method": "sort", "args": {"createdAt": -1}},
        {"method": "limit", "args": 25},
    ]


def test_parse_allows_complex_find_query():
    connector = MongoConnector({})
    query = (
        "db.customers.find("
        '  {"tenant_id": ObjectId("65fb164d4a2c0d74c6993abf"),'
        '   "createdAt": {'
        '      "$gte": new Date("2025-01-01T00:00:00.000Z"),'
        '      "$lte": new Date("2025-03-31T23:59:59.999Z")'
        "   }"
        "  },"
        '  {"_id": 1, "firstName": 1, "lastName": 1, "gender": 1, "birthday": 1, "createdAt": 1}'
        ').sort({"createdAt": -1})'
    )

    parsed = connector._parse_query(query)

    assert parsed["collection"] == "customers"
    assert parsed["operation"] == "find"
    assert parsed["args"][0]["tenant_id"]
    assert parsed["args"][0]["createdAt"]["$gte"].year == 2025
    assert parsed["modifiers"] == [{"method": "sort", "args": {"createdAt": -1}}]


def test_parse_converts_extended_json_oid_wrapper():
    connector = MongoConnector({})
    query = 'db.users.find({"_id": {"$oid": "65fb164d4a2c0d74c6993abf"}})'

    parsed = connector._parse_query(query)

    assert parsed["collection"] == "users"
    assert parsed["operation"] == "find"
    assert not isinstance(parsed["args"][0]["_id"], dict)
    assert str(parsed["args"][0]["_id"]) == "65fb164d4a2c0d74c6993abf"


def test_apply_filters_to_mongo_rebuilt_query_keeps_oid_parseable():
    query = 'db.events.aggregate([{"$match": {"tenant_id": {"$oid": "65fb164d4a2c0d74c6993abf"}}}])'
    filters = [QueryFilter(field="status", operator="eq", value="active")]

    filtered_query = DatabaseOperationsService.apply_filters_to_mongo(query, filters)
    parsed = MongoConnector({})._parse_query(filtered_query)

    assert parsed["operation"] == "aggregate"
    assert "$oid" not in filtered_query
    assert 'ObjectId("65fb164d4a2c0d74c6993abf")' in filtered_query
    assert not _contains_key_recursive(parsed["args"], "$oid")
    assert "status" in str(parsed["args"])
    assert "active" in str(parsed["args"])


def test_parse_blocks_write_operation():
    connector = MongoConnector({})
    parsed = connector._parse_query('db.users.insertOne({"name": "A"})')

    assert parsed["is_write_operation"] is True
    assert parsed["operation"].lower().startswith("insert")


@pytest.mark.parametrize(
    "query",
    [
        'db.accounts.UpdateOne({"_id": 1}, {$set: {"name": "x"}})',
        'db.customers.find({}).findOneAndUpdate({"_id": 1}, {$set: {"name": "y"}})',
        'db.getCollection("orders").updateMany({"status": "pending"}, {"$set": {"status": "done"}})',
        'db.logs.remove({"level": "debug"})',
        'db.items.bulkWrite([{ "updateOne": { "filter": {"_id": 1}, "update": {"$set": {"q": 1}} } }])',
    ],
)
def test_parse_blocks_additional_write_operations(query):
    connector = MongoConnector({})
    parsed = connector._parse_query(query)

    assert parsed["is_write_operation"] is True


def test_parse_rejects_unsupported_modifier():
    connector = MongoConnector({})
    parsed = connector._parse_query("db.users.find({}).maxTimeMS(1000)")

    assert parsed["error"].startswith("Unsupported modifier")


@pytest.mark.parametrize(
    "pipeline, blocked",
    [
        ('[{ "$match": {} }, { "$out": "archive" }]', "$out"),
        ('[{ "$match": {} }, { "$MERGE": "archive" }]', "$MERGE"),
        ('[{ "$lookup": {}}, { "$merge": {"into": "dest"}}]', "$merge"),
    ],
)
def test_parse_detects_blocked_aggregate_stage(pipeline, blocked):
    connector = MongoConnector({})
    parsed = connector._parse_query(f"db.logs.aggregate({pipeline})")

    assert parsed["is_write_operation"] is True
    assert parsed["blocked_stage"].lower() == blocked.lower()


def test_parse_supports_get_collection():
    connector = MongoConnector({})
    parsed = connector._parse_query('db.getCollection("orders").find({})')

    assert parsed["collection"] == "orders"
    assert parsed["operation"] == "find"


@pytest.mark.asyncio
async def test_async_connector_applies_modifier_limit():
    collection = DummyCollection(data=[{"_id": i} for i in range(30)])
    connector = AsyncMongoConnector({})
    connector.client = DummyClient(collection)
    connector.database_name = "test"

    result = await connector.execute_query(
        "users",
        "find",
        [{"active": True}],
        limit=10,
        modifiers=[
            {"method": "sort", "args": {"createdAt": -1}},
            {"method": "limit", "args": 50},
        ],
    )

    assert result["success"] is True
    assert result["returned_count"] == 10
    assert result["limited"] is True
    assert collection.filter_used == {"active": True}
    assert ("limit", 50) in collection.last_cursor.calls
    assert ("limit", 10) in collection.last_cursor.calls
    assert collection.last_cursor.calls[-1] == ("to_list", 10)


@pytest.mark.asyncio
async def test_async_connector_appends_limit_to_pipeline():
    collection = DummyCollection(data=[{"_id": i} for i in range(5)])
    connector = AsyncMongoConnector({})
    connector.client = DummyClient(collection)
    connector.database_name = "test"

    result = await connector.execute_query(
        "logs",
        "aggregate",
        [[{"$match": {"level": "info"}}]],
        limit=3,
    )

    assert result["success"] is True
    assert collection.aggregate_pipeline[-1] == {"$limit": 3}
    assert collection.aggregate_options == {}


# ---------------------------------------------------------------------------
# Additional AsyncMongoConnector operation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_connector_find_no_filter():
    collection = DummyCollection(data=[{"_id": 1, "name": "Alice"}])
    connector = AsyncMongoConnector({})
    connector.client = DummyClient(collection)
    connector.database_name = "test"

    result = await connector.execute_query("users", "find", [{}], limit=10)
    assert result["success"] is True
    assert result["returned_count"] == 1


@pytest.mark.asyncio
async def test_async_connector_find_one():
    collection = DummyCollection(data=[{"_id": 1}])
    connector = AsyncMongoConnector({})
    connector.client = DummyClient(collection)
    connector.database_name = "test"

    result = await connector.execute_query("users", "findOne", [{"_id": 1}])
    assert result["success"] is True
    assert result["operation"] == "findOne"


@pytest.mark.asyncio
async def test_async_connector_count_documents():
    collection = DummyCollection(data=[])
    connector = AsyncMongoConnector({})
    connector.client = DummyClient(collection)
    connector.database_name = "test"

    result = await connector.execute_query("users", "countDocuments", [{}])
    assert result["success"] is True
    assert result["result"] == 100  # DummyCollection returns 100


@pytest.mark.asyncio
async def test_async_connector_count():
    collection = DummyCollection(data=[])
    connector = AsyncMongoConnector({})
    connector.client = DummyClient(collection)
    connector.database_name = "test"

    result = await connector.execute_query("users", "count", [{}])
    assert result["success"] is True
    assert result["result"] == 100


@pytest.mark.asyncio
async def test_async_connector_estimated_document_count():
    collection = DummyCollection(data=[])
    connector = AsyncMongoConnector({})
    connector.client = DummyClient(collection)
    connector.database_name = "test"

    result = await connector.execute_query("users", "estimatedDocumentCount", [])
    assert result["success"] is True
    assert result["result"] == 42  # DummyCollection returns 42


@pytest.mark.asyncio
async def test_async_connector_distinct():
    collection = DummyCollection(data=[])
    connector = AsyncMongoConnector({})
    connector.client = DummyClient(collection)
    connector.database_name = "test"

    result = await connector.execute_query("users", "distinct", ["status"])
    assert result["success"] is True
    assert result["result"] == ["a", "b"]  # DummyCollection returns ["a", "b"]
    assert result["total_count"] == 2


@pytest.mark.asyncio
async def test_async_connector_unsupported_operation_raises():
    collection = DummyCollection(data=[])
    connector = AsyncMongoConnector({})
    connector.client = DummyClient(collection)
    connector.database_name = "test"

    with pytest.raises(ValueError, match="Unsupported operation"):
        await connector.execute_query("users", "mapReduce", [])


@pytest.mark.asyncio
async def test_async_connector_not_connected_raises():
    connector = AsyncMongoConnector({})
    with pytest.raises(RuntimeError, match="MongoDB not connected"):
        await connector.execute_query("users", "find", [{}])


@pytest.mark.asyncio
async def test_async_connector_execution_time_tracked():
    collection = DummyCollection(data=[{"_id": 1}])
    connector = AsyncMongoConnector({})
    connector.client = DummyClient(collection)
    connector.database_name = "test"

    result = await connector.execute_query("users", "find", [{}])
    assert "execution_time_seconds" in result
    assert result["execution_time_seconds"] >= 0


@pytest.mark.asyncio
async def test_async_connector_aggregate_without_limit():
    collection = DummyCollection(data=[{"_id": i} for i in range(5)])
    connector = AsyncMongoConnector({})
    connector.client = DummyClient(collection)
    connector.database_name = "test"

    result = await connector.execute_query("logs", "aggregate", [[{"$match": {}}]])
    assert result["success"] is True
    assert result["total_count"] == 5


# ---------------------------------------------------------------------------
# _apply_cursor_modifiers edge case tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_connector_skip_modifier():
    collection = DummyCollection(data=[{"_id": i} for i in range(10)])
    connector = AsyncMongoConnector({})
    connector.client = DummyClient(collection)
    connector.database_name = "test"

    result = await connector.execute_query(
        "users",
        "find",
        [{}],
        limit=10,
        modifiers=[{"method": "skip", "args": 5}],
    )
    assert result["success"] is True
    assert ("skip", 5) in collection.last_cursor.calls


@pytest.mark.asyncio
async def test_async_connector_project_modifier():
    collection = DummyCollection(data=[{"_id": 1, "name": "Alice"}])
    connector = AsyncMongoConnector({})
    connector.client = DummyClient(collection)
    connector.database_name = "test"

    result = await connector.execute_query(
        "users",
        "find",
        [{}],
        limit=10,
        modifiers=[{"method": "project", "args": {"name": 1, "_id": 0}}],
    )
    assert result["success"] is True
    assert ("project", {"name": 1, "_id": 0}) in collection.last_cursor.calls
