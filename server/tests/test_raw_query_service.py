"""
Tests for AsyncRawQueryService — DuckDB literal rendering, parameter inlining, routing.
"""

from datetime import date, datetime, time
from decimal import Decimal

import pytest

from server.services.raw_query import AsyncRawQueryService

# ---------------------------------------------------------------------------
# _duckdb_sql_literal
# ---------------------------------------------------------------------------


class TestDuckdbSqlLiteral:
    def test_none(self):
        assert AsyncRawQueryService._duckdb_sql_literal(None) == "NULL"

    def test_bool_true(self):
        assert AsyncRawQueryService._duckdb_sql_literal(True) == "TRUE"

    def test_bool_false(self):
        assert AsyncRawQueryService._duckdb_sql_literal(False) == "FALSE"

    def test_integer(self):
        assert AsyncRawQueryService._duckdb_sql_literal(42) == "42"

    def test_decimal(self):
        assert AsyncRawQueryService._duckdb_sql_literal(Decimal("3.14")) == "3.14"

    def test_float(self):
        assert AsyncRawQueryService._duckdb_sql_literal(3.14) == "3.14"

    def test_float_nan_raises(self):
        with pytest.raises(ValueError, match="Non-finite"):
            AsyncRawQueryService._duckdb_sql_literal(float("nan"))

    def test_float_inf_raises(self):
        with pytest.raises(ValueError, match="Non-finite"):
            AsyncRawQueryService._duckdb_sql_literal(float("inf"))

    def test_datetime(self):
        dt = datetime(2025, 1, 15, 10, 30, 0)
        result = AsyncRawQueryService._duckdb_sql_literal(dt)
        assert result == "'2025-01-15T10:30:00'"

    def test_date(self):
        d = date(2025, 1, 15)
        result = AsyncRawQueryService._duckdb_sql_literal(d)
        assert result == "'2025-01-15'"

    def test_time(self):
        t = time(10, 30, 0)
        result = AsyncRawQueryService._duckdb_sql_literal(t)
        assert result == "'10:30:00'"

    def test_string(self):
        assert AsyncRawQueryService._duckdb_sql_literal("hello") == "'hello'"

    def test_string_with_single_quote_escaped(self):
        result = AsyncRawQueryService._duckdb_sql_literal("it's")
        assert result == "'it''s'"

    def test_string_sql_injection_escaped(self):
        result = AsyncRawQueryService._duckdb_sql_literal("'; DROP TABLE users; --")
        assert "''" in result
        assert result.startswith("'")
        assert result.endswith("'")


# ---------------------------------------------------------------------------
# _inline_duckdb_params
# ---------------------------------------------------------------------------


class TestInlineDuckdbParams:
    def test_no_params_returns_query(self):
        query = "SELECT * FROM data"
        result = AsyncRawQueryService._inline_duckdb_params(query, None)
        assert result == query

    def test_empty_params_returns_query(self):
        query = "SELECT * FROM data"
        result = AsyncRawQueryService._inline_duckdb_params(query, {})
        assert result == query

    def test_single_param(self):
        query = "SELECT * FROM data WHERE name = :name"
        result = AsyncRawQueryService._inline_duckdb_params(query, {"name": "Alice"})
        assert result == "SELECT * FROM data WHERE name = 'Alice'"

    def test_multiple_params(self):
        query = "SELECT * FROM data WHERE name = :name AND age > :age"
        result = AsyncRawQueryService._inline_duckdb_params(query, {"name": "Alice", "age": 25})
        assert "'Alice'" in result
        assert "25" in result
        assert ":name" not in result
        assert ":age" not in result

    def test_null_param(self):
        query = "SELECT * FROM data WHERE name = :name"
        result = AsyncRawQueryService._inline_duckdb_params(query, {"name": None})
        assert "NULL" in result

    def test_bool_param(self):
        query = "SELECT * FROM data WHERE active = :active"
        result = AsyncRawQueryService._inline_duckdb_params(query, {"active": True})
        assert "TRUE" in result

    def test_longer_param_name_replaced_first(self):
        # Params sorted by length descending to avoid partial replacement
        query = "SELECT * FROM data WHERE val = :val AND value = :value"
        result = AsyncRawQueryService._inline_duckdb_params(query, {"val": 1, "value": 2})
        assert "value = 2" in result
        assert ":val" not in result
        assert ":value" not in result

    def test_param_with_special_chars_in_value(self):
        query = "SELECT * FROM data WHERE name = :name"
        result = AsyncRawQueryService._inline_duckdb_params(query, {"name": "O'Brien"})
        assert "O''Brien" in result


# ---------------------------------------------------------------------------
# execute_raw_query routing
# ---------------------------------------------------------------------------


class TestExecuteRawQueryRouting:
    @pytest.mark.asyncio
    async def test_missing_connection_obj(self):
        result = await AsyncRawQueryService.execute_raw_query(
            query="SELECT 1",
            db_type="pg",
            connection_id="conn-1",
            connection_obj=None,
        )
        assert "error" in result
        assert "Missing connection" in result["error"]

    @pytest.mark.asyncio
    async def test_oracle_routes_to_sql_connector(self, monkeypatch):
        captured = {}

        class FakeConnector:
            async def execute_query(self, query, limit=None, timeout=30, params=None):
                captured["query"] = query
                captured["limit"] = limit
                captured["timeout"] = timeout
                captured["params"] = params
                return {"success": True, "result": [{"x": 1}], "returned_count": 1}

        async def fake_get_or_create_sql_connector(connection_id, connection_obj, db_type="pg"):
            captured["connection_id"] = connection_id
            captured["connection_obj"] = connection_obj
            captured["db_type"] = db_type
            return FakeConnector()

        monkeypatch.setattr(
            "server.services.raw_query.AsyncDatabaseService.get_or_create_sql_connector",
            fake_get_or_create_sql_connector,
        )

        result = await AsyncRawQueryService.execute_raw_query(
            query="SELECT 1",
            db_type="oracle",
            connection_id="conn-1",
            connection_obj={"host": "localhost", "service_name": "FREEPDB1", "user": "u", "password": "p"},
            limit=5,
            timeout=7,
            params={"store_id": 1},
        )

        assert result["success"] is True
        assert captured["db_type"] == "oracle"
        assert captured["connection_id"] == "conn-1"
        assert captured["limit"] == 5
        assert captured["timeout"] == 7
        assert captured["params"] == {"store_id": 1}

    @pytest.mark.asyncio
    async def test_mongo_write_blocked(self):
        result = await AsyncRawQueryService.execute_raw_query(
            query='db.users.insertOne({"name": "test"})',
            db_type="mongo",
            connection_id="conn-1",
            connection_obj={"connection_string": "mongodb://localhost/test"},
        )
        assert result.get("success") is False
        assert "not allowed" in result.get("error", "").lower() or "write" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_dynamodb_partiql_write_blocked(self):
        result = await AsyncRawQueryService.execute_raw_query(
            query="DELETE FROM Users WHERE userId='abc'",
            db_type="dynamodb",
            connection_id="conn-1",
            connection_obj={"region": "us-east-1", "access_key_id": "x", "secret_access_key": "y"},
        )
        assert result.get("success") is False

    @pytest.mark.asyncio
    async def test_dynamodb_native_write_blocked(self):
        result = await AsyncRawQueryService.execute_raw_query(
            query='{"operation": "put_item", "table": "Users"}',
            db_type="dynamodb",
            connection_id="conn-1",
            connection_obj={
                "region": "us-east-1",
                "access_key_id": "x",
                "secret_access_key": "y",
                "query_mode": "native",
            },
        )
        assert result.get("success") is False
