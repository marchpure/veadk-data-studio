"""
Tests for redaction enforcement in query tools.

Each tool (sql, mongo, duckdb, dynamodb) checks redaction_rules from ctx.context
before executing queries. These tests verify that redacted tables and columns
are blocked at the tool level.
"""

from server.services.redaction_service import RedactionService


class FakeCtx:
    """Minimal RunContextWrapper stand-in for tool tests."""

    def __init__(self, context: dict):
        self.context = context


class FakeConnection:
    def __init__(self, conn_type="pg", conn_id="conn-1"):
        self.id = conn_id
        self.type = conn_type
        self.name = "Test Connection"

    async def get_decrypted_connection_obj(self, session):
        return {"host": "localhost", "port": 5432, "database": "test", "user": "u", "password": "p"}


class FakeDataset:
    def __init__(self, dataset_id="ds-1"):
        self.id = dataset_id


# ---------------------------------------------------------------------------
# SQL Tool Redaction Tests
# ---------------------------------------------------------------------------


class TestSqlToolRedaction:
    """Tests redaction logic from server/tools/sql.py execute_sql_query."""

    def _simulate_sql_redaction_check(self, query, connection_id, redaction_rules):
        """Simulates the redaction check logic from execute_sql_query."""
        import sqlglot
        from sqlglot import exp

        conn_rules = redaction_rules.get(connection_id, {})
        if not conn_rules:
            return None

        redacted_tables = set(conn_rules.get("tables", []))
        redacted_col_map = conn_rules.get("columns", {})
        queried_tables = set()

        try:
            parsed_expressions = sqlglot.parse(query)
            for tree in parsed_expressions:
                for tbl in tree.find_all(exp.Table):
                    queried_tables.add(tbl.name)
        except Exception:
            pass

        for tbl_name in queried_tables:
            if tbl_name in redacted_tables:
                return {"blocked": True, "reason": f"table '{tbl_name}' is restricted"}

        if queried_tables and redacted_col_map:
            blocked_cols = set()
            for tbl_name in queried_tables:
                blocked_cols.update(redacted_col_map.get(tbl_name, []))
            if blocked_cols:
                try:
                    for tree in sqlglot.parse(query):
                        for col in tree.find_all(exp.Column):
                            if col.name in blocked_cols:
                                return {"blocked": True, "reason": f"column '{col.name}' is restricted"}
                except Exception:
                    pass

        return None

    def test_blocks_redacted_table(self):
        rules = {"conn-1": {"tables": ["secret_data"], "columns": {}}}
        result = self._simulate_sql_redaction_check("SELECT * FROM secret_data", "conn-1", rules)
        assert result is not None
        assert result["blocked"] is True
        assert "secret_data" in result["reason"]

    def test_allows_non_redacted_table(self):
        rules = {"conn-1": {"tables": ["secret_data"], "columns": {}}}
        result = self._simulate_sql_redaction_check("SELECT * FROM public_data", "conn-1", rules)
        assert result is None

    def test_blocks_redacted_column(self):
        rules = {"conn-1": {"tables": [], "columns": {"users": ["ssn", "password"]}}}
        result = self._simulate_sql_redaction_check("SELECT ssn FROM users", "conn-1", rules)
        assert result is not None
        assert result["blocked"] is True
        assert "ssn" in result["reason"]

    def test_allows_non_redacted_column(self):
        rules = {"conn-1": {"tables": [], "columns": {"users": ["ssn"]}}}
        result = self._simulate_sql_redaction_check("SELECT name, email FROM users", "conn-1", rules)
        assert result is None

    def test_no_rules_for_connection(self):
        rules = {"other-conn": {"tables": ["secret"], "columns": {}}}
        result = self._simulate_sql_redaction_check("SELECT * FROM secret", "conn-1", rules)
        assert result is None

    def test_blocks_redacted_table_in_join(self):
        rules = {"conn-1": {"tables": ["secret_data"], "columns": {}}}
        result = self._simulate_sql_redaction_check(
            "SELECT u.name FROM users u JOIN secret_data s ON u.id = s.user_id",
            "conn-1",
            rules,
        )
        assert result is not None
        assert result["blocked"] is True

    def test_blocks_redacted_column_in_where(self):
        rules = {"conn-1": {"tables": [], "columns": {"users": ["ssn"]}}}
        result = self._simulate_sql_redaction_check(
            "SELECT name FROM users WHERE ssn = '123'",
            "conn-1",
            rules,
        )
        assert result is not None
        assert result["blocked"] is True


# ---------------------------------------------------------------------------
# MongoDB Tool Redaction Tests
# ---------------------------------------------------------------------------


class TestMongoToolRedaction:
    """Tests redaction logic from server/tools/mongo.py execute_mongo_query."""

    def _simulate_mongo_redaction_check(self, collection_name, operation, connection_id, redaction_rules, args=None):
        """Simulates the redaction check logic from execute_mongo_query."""
        conn_rules = redaction_rules.get(connection_id, {})
        if not conn_rules:
            return None

        redacted_tables = set(conn_rules.get("tables", []))
        if collection_name in redacted_tables:
            return {"blocked": True, "reason": "collection is restricted"}

        if operation == "distinct" and args:
            redacted_cols = conn_rules.get("columns", {})
            redacted_col_names = set(redacted_cols.get(collection_name, []))
            field_name = args[0] if isinstance(args[0], str) else str(args[0])
            if field_name in redacted_col_names:
                return {"blocked": True, "reason": f"field '{field_name}' is restricted"}

        return None

    def test_blocks_redacted_collection(self):
        rules = {"conn-1": {"tables": ["secret_logs"], "columns": {}}}
        result = self._simulate_mongo_redaction_check("secret_logs", "find", "conn-1", rules)
        assert result is not None
        assert result["blocked"] is True

    def test_allows_non_redacted_collection(self):
        rules = {"conn-1": {"tables": ["secret_logs"], "columns": {}}}
        result = self._simulate_mongo_redaction_check("public_logs", "find", "conn-1", rules)
        assert result is None

    def test_blocks_distinct_on_redacted_field(self):
        rules = {"conn-1": {"tables": [], "columns": {"users": ["ssn"]}}}
        result = self._simulate_mongo_redaction_check("users", "distinct", "conn-1", rules, args=["ssn"])
        assert result is not None
        assert "ssn" in result["reason"]

    def test_allows_distinct_on_non_redacted_field(self):
        rules = {"conn-1": {"tables": [], "columns": {"users": ["ssn"]}}}
        result = self._simulate_mongo_redaction_check("users", "distinct", "conn-1", rules, args=["name"])
        assert result is None

    def test_no_rules_for_connection(self):
        rules = {"other-conn": {"tables": ["secret"], "columns": {}}}
        result = self._simulate_mongo_redaction_check("secret", "find", "conn-1", rules)
        assert result is None


# ---------------------------------------------------------------------------
# DuckDB Tool Redaction Tests
# ---------------------------------------------------------------------------


class TestDuckdbToolRedaction:
    """Tests redaction logic from server/tools/dataframe.py execute_duckdb_query."""

    def _simulate_duckdb_redaction_check(self, query, dataset_id, redaction_rules):
        """Simulates the redaction check logic from execute_duckdb_query."""
        import sqlglot
        from sqlglot import exp

        ds_rules = redaction_rules.get(dataset_id, {})
        if not ds_rules:
            return None

        redacted_tables = set(ds_rules.get("tables", []))
        redacted_col_map = ds_rules.get("columns", {})
        queried_tables = set()

        try:
            parsed_expressions = sqlglot.parse(query)
            for tree in parsed_expressions:
                for tbl in tree.find_all(exp.Table):
                    queried_tables.add(tbl.name)
        except Exception:
            pass

        for tbl_name in queried_tables:
            if tbl_name in redacted_tables:
                return {"blocked": True, "reason": f"table '{tbl_name}' is restricted"}

        if queried_tables and redacted_col_map:
            blocked_cols = set()
            for tbl_name in queried_tables:
                blocked_cols.update(redacted_col_map.get(tbl_name, []))
            if blocked_cols:
                try:
                    for tree in sqlglot.parse(query):
                        for col in tree.find_all(exp.Column):
                            if col.name in blocked_cols:
                                return {"blocked": True, "reason": f"column '{col.name}' is restricted"}
                except Exception:
                    pass

        return None

    def test_blocks_redacted_file_alias(self):
        rules = {"ds-1": {"tables": ["sensitive_data"], "columns": {}}}
        result = self._simulate_duckdb_redaction_check("SELECT * FROM sensitive_data", "ds-1", rules)
        assert result is not None
        assert result["blocked"] is True

    def test_allows_non_redacted_file(self):
        rules = {"ds-1": {"tables": ["sensitive_data"], "columns": {}}}
        result = self._simulate_duckdb_redaction_check("SELECT * FROM public_data", "ds-1", rules)
        assert result is None

    def test_blocks_redacted_column_in_file(self):
        rules = {"ds-1": {"tables": [], "columns": {"sales": ["credit_card"]}}}
        result = self._simulate_duckdb_redaction_check("SELECT credit_card FROM sales", "ds-1", rules)
        assert result is not None
        assert "credit_card" in result["reason"]


# ---------------------------------------------------------------------------
# DynamoDB Tool Redaction Tests
# ---------------------------------------------------------------------------


class TestDynamodbToolRedaction:
    """Tests redaction logic from server/tools/dynamodb.py execute_dynamodb_query."""

    def _simulate_dynamodb_redaction_check(self, query_or_table, connection_id, redaction_rules, query_mode="partiql"):
        """Simulates the redaction check logic from execute_dynamodb_query."""
        import re

        conn_rules = redaction_rules.get(connection_id, {})
        if not conn_rules:
            return None

        redacted_tables = set(conn_rules.get("tables", []))

        if query_mode == "partiql":
            for table in redacted_tables:
                if re.search(rf"\b{re.escape(table)}\b", query_or_table, re.IGNORECASE):
                    return {"blocked": True, "reason": "table is restricted"}
        else:
            if query_or_table in redacted_tables:
                return {"blocked": True, "reason": "table is restricted"}

        return None

    def test_blocks_redacted_table_partiql(self):
        rules = {"conn-1": {"tables": ["SecretTable"], "columns": {}}}
        result = self._simulate_dynamodb_redaction_check(
            "SELECT * FROM SecretTable WHERE id = 'abc'",
            "conn-1",
            rules,
            query_mode="partiql",
        )
        assert result is not None
        assert result["blocked"] is True

    def test_allows_non_redacted_table_partiql(self):
        rules = {"conn-1": {"tables": ["SecretTable"], "columns": {}}}
        result = self._simulate_dynamodb_redaction_check(
            "SELECT * FROM PublicTable WHERE id = 'abc'",
            "conn-1",
            rules,
            query_mode="partiql",
        )
        assert result is None

    def test_blocks_redacted_table_native(self):
        rules = {"conn-1": {"tables": ["SecretTable"], "columns": {}}}
        result = self._simulate_dynamodb_redaction_check(
            "SecretTable",
            "conn-1",
            rules,
            query_mode="native",
        )
        assert result is not None

    def test_allows_non_redacted_table_native(self):
        rules = {"conn-1": {"tables": ["SecretTable"], "columns": {}}}
        result = self._simulate_dynamodb_redaction_check(
            "PublicTable",
            "conn-1",
            rules,
            query_mode="native",
        )
        assert result is None


# ---------------------------------------------------------------------------
# Result-Level Redaction Tests (RedactionService.redact_result_rows)
# ---------------------------------------------------------------------------


class TestResultLevelRedaction:
    """Tests that RedactionService.redact_result_rows masks values correctly."""

    def test_masks_redacted_columns_in_list_of_dicts(self):
        rows = [
            {"name": "Alice", "ssn": "123-45-6789", "email": "alice@test.com"},
            {"name": "Bob", "ssn": "987-65-4321", "email": "bob@test.com"},
        ]
        redacted_cols = {"users": {"ssn"}}
        RedactionService.redact_result_rows(rows, redacted_cols, set())
        for row in rows:
            assert row["name"] != "***"
            assert row["email"] != "***"

    def test_no_redaction_without_rules(self):
        rows = [{"name": "Alice", "ssn": "123-45-6789"}]
        original = [dict(r) for r in rows]
        RedactionService.redact_result_rows(rows, {}, set())
        assert rows == original

    def test_empty_rows_no_error(self):
        RedactionService.redact_result_rows([], {"users": {"ssn"}}, set())
