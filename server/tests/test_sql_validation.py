import pytest

from server.tools.sql import DIALECT_MAP, validate_sql_query


class TestValidateSqlQueryAllowsReads:
    def test_simple_select(self):
        result = validate_sql_query("SELECT * FROM users")
        assert "SELECT" in result.upper()

    def test_select_with_where(self):
        result = validate_sql_query("SELECT id, name FROM users WHERE active = true")
        assert "WHERE" in result.upper()

    def test_select_with_join(self):
        result = validate_sql_query("SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id")
        assert "JOIN" in result.upper()

    def test_select_with_subquery(self):
        result = validate_sql_query("SELECT * FROM users WHERE id IN (SELECT user_id FROM orders)")
        assert "IN" in result.upper()

    def test_cte_select(self):
        result = validate_sql_query(
            "WITH active_users AS (SELECT * FROM users WHERE active = true) SELECT * FROM active_users"
        )
        assert "WITH" in result.upper()

    def test_union_select(self):
        result = validate_sql_query("SELECT id FROM users UNION SELECT id FROM admins")
        assert "UNION" in result.upper()

    def test_aggregate_functions(self):
        result = validate_sql_query(
            "SELECT COUNT(*), AVG(age), SUM(total) FROM users GROUP BY department HAVING COUNT(*) > 5"
        )
        assert "GROUP BY" in result.upper()

    def test_window_functions(self):
        result = validate_sql_query(
            "SELECT name, ROW_NUMBER() OVER (PARTITION BY dept ORDER BY salary DESC) FROM employees"
        )
        assert "OVER" in result.upper()

    def test_select_distinct(self):
        result = validate_sql_query("SELECT DISTINCT category FROM products")
        assert "DISTINCT" in result.upper()

    def test_select_with_limit(self):
        result = validate_sql_query("SELECT * FROM users LIMIT 10")
        assert "LIMIT" in result.upper()

    def test_select_with_order_by(self):
        result = validate_sql_query("SELECT * FROM users ORDER BY created_at DESC")
        assert "ORDER BY" in result.upper()

    def test_select_with_case(self):
        result = validate_sql_query("SELECT CASE WHEN age > 18 THEN 'adult' ELSE 'minor' END AS category FROM users")
        assert "CASE" in result.upper()


class TestValidateSqlQueryBlocksWrites:
    def test_blocks_delete(self):
        with pytest.raises(ValueError, match="DELETE"):
            validate_sql_query("DELETE FROM users WHERE id = 1")

    def test_blocks_insert(self):
        with pytest.raises(ValueError, match="INSERT"):
            validate_sql_query("INSERT INTO users (name) VALUES ('test')")

    def test_blocks_update(self):
        with pytest.raises(ValueError, match="UPDATE"):
            validate_sql_query("UPDATE users SET name = 'test' WHERE id = 1")

    def test_blocks_create_table(self):
        with pytest.raises(ValueError, match="CREATE"):
            validate_sql_query("CREATE TABLE test (id INT)")

    def test_blocks_alter_table(self):
        with pytest.raises(ValueError, match="ALTER"):
            validate_sql_query("ALTER TABLE users ADD COLUMN email VARCHAR(255)")

    def test_blocks_drop_table(self):
        with pytest.raises(ValueError, match="DROP"):
            validate_sql_query("DROP TABLE users")

    def test_blocks_drop_database(self):
        with pytest.raises(ValueError, match="DROP"):
            validate_sql_query("DROP DATABASE production")

    def test_blocks_truncate(self):
        with pytest.raises(ValueError, match="TRUNCATE|SELECT"):
            validate_sql_query("TRUNCATE TABLE users")

    def test_blocks_insert_into_select(self):
        with pytest.raises(ValueError, match="INSERT"):
            validate_sql_query("INSERT INTO archive SELECT * FROM users WHERE active = false")

    def test_blocks_create_index(self):
        with pytest.raises(ValueError, match="CREATE"):
            validate_sql_query("CREATE INDEX idx_name ON users (name)")

    def test_blocks_cte_wrapping_delete(self):
        with pytest.raises(ValueError, match="DELETE"):
            validate_sql_query(
                "WITH targets AS (SELECT id FROM users WHERE active = false) "
                "DELETE FROM users WHERE id IN (SELECT id FROM targets)"
            )

    def test_blocks_cte_wrapping_update(self):
        with pytest.raises(ValueError, match="UPDATE"):
            validate_sql_query(
                "WITH targets AS (SELECT id FROM users) "
                "UPDATE users SET active = false WHERE id IN (SELECT id FROM targets)"
            )


class TestValidateSqlQueryInjectionAttempts:
    def test_blocks_semicolon_drop(self):
        with pytest.raises(ValueError):
            validate_sql_query("SELECT * FROM users; DROP TABLE users")

    def test_blocks_semicolon_delete(self):
        with pytest.raises(ValueError):
            validate_sql_query("SELECT 1; DELETE FROM users")

    def test_blocks_semicolon_insert(self):
        with pytest.raises(ValueError):
            validate_sql_query("SELECT 1; INSERT INTO users (name) VALUES ('hack')")


class TestValidateSqlQueryPreprocessing:
    def test_strips_trailing_semicolon(self):
        result = validate_sql_query("SELECT * FROM users;")
        assert not result.endswith(";")

    def test_strips_whitespace(self):
        result = validate_sql_query("  SELECT * FROM users  ")
        assert result == "SELECT * FROM users"

    def test_handles_escaped_newlines(self):
        result = validate_sql_query("SELECT *\\nFROM users\\nWHERE id = 1")
        assert "\n" in result

    def test_handles_escaped_tabs(self):
        result = validate_sql_query("SELECT\\t*\\tFROM users")
        assert "\t" in result

    def test_empty_query_raises(self):
        with pytest.raises(ValueError):
            validate_sql_query("")


class TestValidateSqlQueryDialects:
    def test_postgres_dialect(self):
        result = validate_sql_query(
            "SELECT * FROM users WHERE data->>'name' = 'test'",
            dialect="postgres",
        )
        assert result is not None

    def test_mysql_dialect(self):
        result = validate_sql_query(
            "SELECT * FROM users LIMIT 10",
            dialect="mysql",
        )
        assert result is not None

    def test_tsql_dialect_top(self):
        result = validate_sql_query(
            "SELECT TOP 10 * FROM users",
            dialect="tsql",
        )
        assert result is not None

    def test_sqlite_dialect_none(self):
        result = validate_sql_query(
            "SELECT * FROM users WHERE typeof(value) = 'text'",
            dialect=None,
        )
        assert result is not None

    def test_dialect_map_keys(self):
        assert DIALECT_MAP["pg"] == "postgres"
        assert DIALECT_MAP["mysql"] == "mysql"
        assert DIALECT_MAP["mssql"] == "tsql"
        assert DIALECT_MAP["sqlite"] is None
        assert DIALECT_MAP["oracle"] == "oracle"

    def test_blocks_delete_across_dialects(self):
        for dialect in [None, "postgres", "mysql", "tsql", "oracle"]:
            with pytest.raises(ValueError, match="DELETE"):
                validate_sql_query("DELETE FROM users", dialect=dialect)

    def test_blocks_insert_across_dialects(self):
        for dialect in [None, "postgres", "mysql", "tsql", "oracle"]:
            with pytest.raises(ValueError, match="INSERT"):
                validate_sql_query("INSERT INTO users (name) VALUES ('x')", dialect=dialect)

    def test_oracle_dialect_fetch_first(self):
        result = validate_sql_query("SELECT * FROM users FETCH FIRST 10 ROWS ONLY", dialect="oracle")
        assert result is not None
