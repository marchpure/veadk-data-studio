import pytest

from server.tools.mongo import is_write_operation


class TestIsWriteOperationDetectsWriteOperators:
    @pytest.mark.parametrize(
        "operator",
        [
            "$set",
            "$unset",
            "$inc",
            "$dec",
            "$mul",
            "$rename",
            "$min",
            "$max",
            "$currentDate",
            "$addToSet",
            "$pop",
            "$pull",
            "$pullAll",
            "$push",
            "$pushAll",
            "$each",
            "$slice",
            "$sort",
            "$position",
            "$bit",
            "$out",
            "$merge",
            "$mod",
        ],
    )
    def test_detects_write_operator_in_dict(self, operator):
        query = {operator: {"field": "value"}}
        is_write, reason = is_write_operation(query)
        assert is_write is True
        assert operator in reason

    @pytest.mark.parametrize(
        "operator",
        ["$set", "$unset", "$inc", "$push", "$pull", "$addtoset", "$rename", "$out", "$merge"],
    )
    def test_detects_write_operator_in_string(self, operator):
        query = f'{{"update": {{{operator}: {{"name": "test"}}}}}}'
        is_write, reason = is_write_operation(query)
        assert is_write is True


class TestIsWriteOperationNestedDetection:
    def test_detects_nested_set(self):
        query = {"filter": {"status": "active"}, "update": {"$set": {"name": "new"}}}
        is_write, reason = is_write_operation(query)
        assert is_write is True
        assert "$set" in reason

    def test_detects_deeply_nested_push(self):
        query = {"a": {"b": {"c": {"$push": {"item": 1}}}}}
        is_write, reason = is_write_operation(query)
        assert is_write is True

    def test_detects_write_in_list(self):
        query = [{"$match": {}}, {"$out": "archive"}]
        is_write, reason = is_write_operation(query)
        assert is_write is True

    def test_detects_write_in_nested_list(self):
        query = [{"stages": [{"$merge": {"into": "dest"}}]}]
        is_write, reason = is_write_operation(query)
        assert is_write is True


class TestIsWriteOperationAllowsReads:
    def test_allows_empty_dict(self):
        is_write, reason = is_write_operation({})
        assert is_write is False

    def test_allows_empty_list(self):
        is_write, reason = is_write_operation([])
        assert is_write is False

    def test_allows_match_filter(self):
        is_write, reason = is_write_operation({"$match": {"status": "active"}})
        assert is_write is False

    def test_allows_group_stage(self):
        is_write, reason = is_write_operation({"$group": {"_id": "$category", "count": {"$sum": 1}}})
        assert is_write is False

    def test_allows_lookup(self):
        query = {"$lookup": {"from": "orders", "localField": "id", "foreignField": "userId", "as": "orders"}}
        is_write, reason = is_write_operation(query)
        assert is_write is False

    def test_allows_project(self):
        is_write, reason = is_write_operation({"$project": {"name": 1, "_id": 0}})
        assert is_write is False

    def test_allows_plain_filter(self):
        is_write, reason = is_write_operation({"status": "active", "age": {"$gte": 18}})
        assert is_write is False

    def test_allows_aggregate_pipeline_read_only(self):
        pipeline = [
            {"$match": {"status": "active"}},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
            {"$limit": 10},
        ]
        is_write, reason = is_write_operation(pipeline)
        assert is_write is False

    def test_sort_in_pipeline_triggers_false_positive(self):
        # NOTE: $sort is in write_operators set but is a valid read-only pipeline stage.
        # This documents the false positive. The tool-level code uses MongoConnector._parse_query
        # which has its own write detection, so this function is a secondary check.
        pipeline = [{"$match": {}}, {"$sort": {"total": -1}}]
        is_write, reason = is_write_operation(pipeline)
        assert is_write is True  # False positive — $sort is not actually a write op


class TestIsWriteOperationStringInput:
    def test_allows_read_query_string(self):
        query = '{"status": "active", "age": {"$gte": 18}}'
        is_write, reason = is_write_operation(query)
        assert is_write is False

    def test_detects_set_in_json_string(self):
        query = '{"$set": {"name": "test"}}'
        is_write, reason = is_write_operation(query)
        assert is_write is True

    def test_allows_non_json_string_without_operators(self):
        is_write, reason = is_write_operation("just some text")
        assert is_write is False

    def test_detects_operator_in_plain_string(self):
        is_write, reason = is_write_operation("something with $set in it")
        assert is_write is True


class TestIsWriteOperationEdgeCases:
    def test_handles_none_gracefully(self):
        is_write, reason = is_write_operation(None)
        assert is_write is False

    def test_handles_integer(self):
        is_write, reason = is_write_operation(42)
        assert is_write is False

    def test_handles_boolean(self):
        is_write, reason = is_write_operation(True)
        assert is_write is False

    def test_handles_malformed_json_string(self):
        is_write, reason = is_write_operation("{not valid json}")
        assert is_write is False
