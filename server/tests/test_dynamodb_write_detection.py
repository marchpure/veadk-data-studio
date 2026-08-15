import pytest

from server.tools.dynamodb import NATIVE_READ_OPERATIONS, is_native_write, is_partiql_write


class TestIsPartiqlWriteBlocksWrites:
    @pytest.mark.parametrize(
        "statement",
        [
            "INSERT INTO Users VALUE {'userId': 'abc'}",
            "  INSERT INTO Users VALUE {'userId': 'abc'}",
            "UPDATE Users SET name='test' WHERE userId='abc'",
            "  UPDATE Users SET name='test' WHERE userId='abc'",
            "DELETE FROM Users WHERE userId='abc'",
            "  DELETE FROM Users WHERE userId='abc'",
        ],
    )
    def test_blocks_write_statement(self, statement):
        is_write, reason = is_partiql_write(statement)
        assert is_write is True
        assert reason

    @pytest.mark.parametrize(
        "statement",
        [
            "insert into Users VALUE {'userId': 'abc'}",
            "update Users SET name='test'",
            "delete FROM Users WHERE userId='abc'",
        ],
    )
    def test_blocks_case_insensitive(self, statement):
        is_write, reason = is_partiql_write(statement)
        assert is_write is True


class TestIsPartiqlWriteAllowsReads:
    @pytest.mark.parametrize(
        "statement",
        [
            "SELECT * FROM Users",
            "SELECT * FROM Users WHERE userId = 'abc'",
            "SELECT name, email FROM Users",
            "  SELECT * FROM Users",
        ],
    )
    def test_allows_select(self, statement):
        is_write, reason = is_partiql_write(statement)
        assert is_write is False
        assert reason == ""

    def test_allows_empty_string(self):
        is_write, reason = is_partiql_write("")
        assert is_write is False


class TestIsNativeWriteBlocksWrites:
    @pytest.mark.parametrize(
        "operation",
        ["put_item", "update_item", "delete_item", "batch_write_item", "transact_write_items"],
    )
    def test_blocks_write_operation(self, operation):
        query_spec = {"operation": operation, "table": "Users"}
        is_write, reason = is_native_write(query_spec)
        assert is_write is True
        assert operation in reason


class TestIsNativeWriteAllowsReads:
    @pytest.mark.parametrize(
        "operation",
        ["get_item", "query", "scan", "batch_get_item", "describe_table"],
    )
    def test_allows_read_operation(self, operation):
        query_spec = {"operation": operation, "table": "Users"}
        is_write, reason = is_native_write(query_spec)
        assert is_write is False
        assert reason == ""

    def test_native_read_operations_constant(self):
        assert NATIVE_READ_OPERATIONS == {"get_item", "query", "scan", "batch_get_item", "describe_table"}

    def test_empty_operation_blocked(self):
        is_write, reason = is_native_write({"operation": "", "table": "Users"})
        assert is_write is True

    def test_missing_operation_blocked(self):
        is_write, reason = is_native_write({"table": "Users"})
        assert is_write is True
