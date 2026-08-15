"""Tests for compact schema formatting in database_operations and file_operations."""

import pytest

from server.services.database_operations import DatabaseOperationsService
from server.services.file_operations import DataFrameFileService


class TestTypeAbbreviation:
    """Tests for type abbreviation helpers."""

    @pytest.mark.parametrize(
        "input_type,expected",
        [
            ("varchar", "str"),
            ("character varying", "str"),
            ("text", "str"),
            ("string", "str"),
            ("integer", "int"),
            ("bigint", "int"),
            ("smallint", "int"),
            ("serial", "int"),
            ("timestamp", "ts"),
            ("timestamp without time zone", "ts"),
            ("timestamp with time zone", "ts"),
            ("timestamptz", "ts"),
            ("boolean", "bool"),
            ("jsonb", "json"),
            ("json", "json"),
            ("objectid", "oid"),
            ("decimal", "dec"),
            ("numeric", "dec"),
            ("double precision", "float"),
            ("real", "float"),
            ("bytea", "bytes"),
            ("array", "arr"),
        ],
    )
    def test_abbreviate_common_types(self, input_type, expected):
        result = DatabaseOperationsService._abbreviate_type(input_type)
        assert result == expected

    def test_abbreviate_unknown_type_passthrough(self):
        result = DatabaseOperationsService._abbreviate_type("custom_type")
        assert result == "custom_type"

    def test_abbreviate_type_with_precision(self):
        result = DatabaseOperationsService._abbreviate_type("varchar(255)")
        assert result == "str"

    def test_abbreviate_type_case_insensitive(self):
        assert DatabaseOperationsService._abbreviate_type("VARCHAR") == "str"
        assert DatabaseOperationsService._abbreviate_type("INTEGER") == "int"
        assert DatabaseOperationsService._abbreviate_type("Boolean") == "bool"

    def test_abbreviate_type_with_whitespace(self):
        result = DatabaseOperationsService._abbreviate_type("  varchar  ")
        assert result == "str"


class TestFileTypeAbbreviation:
    """Tests for file-specific type abbreviation."""

    @pytest.mark.parametrize(
        "input_type,expected",
        [
            ("varchar", "str"),
            ("integer", "int"),
            ("timestamp", "ts"),
            ("boolean", "bool"),
            ("double", "float"),
            ("date", "date"),
        ],
    )
    def test_abbreviate_file_types(self, input_type, expected):
        result = DataFrameFileService._abbreviate_file_type(input_type)
        assert result == expected

    def test_file_unknown_type_passthrough(self):
        result = DataFrameFileService._abbreviate_file_type("geometry")
        assert result == "geometry"


class TestSQLCompactFormatting:
    """Tests for SQL schema compact formatting."""

    def test_format_sql_simple_table(self):
        schema = {
            "datasource_type": "pg",
            "datasource_name": "testdb",
            "schema": {
                "users": {
                    "columns": [
                        {"name": "id", "type": "integer", "nullable": False},
                        {"name": "email", "type": "varchar", "nullable": True},
                    ]
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "pg")
        assert "[PostgreSQL:testdb]" in result
        assert "users: id(int!), email(str)" in result

    def test_format_sql_not_null_marker(self):
        schema = {
            "datasource_type": "pg",
            "datasource_name": "db",
            "schema": {
                "test": {
                    "columns": [
                        {"name": "required", "type": "integer", "nullable": False},
                        {"name": "optional", "type": "integer", "nullable": True},
                    ]
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "pg")
        assert "required(int!)" in result
        assert "optional(int)" in result
        assert "optional(int!)" not in result

    def test_format_sql_with_foreign_keys(self):
        schema = {
            "datasource_type": "pg",
            "datasource_name": "db",
            "schema": {
                "orders": {
                    "columns": [
                        {"name": "id", "type": "integer", "nullable": False},
                        {"name": "user_id", "type": "integer", "nullable": False},
                    ],
                    "foreign_keys": [{"column": "user_id", "ref_table": "users"}],
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "pg")
        assert "FK:user_id→users" in result

    def test_format_sql_with_string_foreign_keys(self):
        schema = {
            "datasource_type": "pg",
            "datasource_name": "db",
            "schema": {
                "orders": {
                    "columns": [{"name": "id", "type": "integer", "nullable": False}],
                    "foreign_keys": ["user_id→users"],
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "pg")
        assert "FK:user_id→users" in result

    def test_format_sql_with_description(self):
        schema = {
            "datasource_type": "pg",
            "datasource_name": "db",
            "schema": {
                "users": {
                    "columns": [{"name": "id", "type": "integer", "nullable": False}],
                    "description": "Main user table",
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "pg")
        assert "// Main user table" in result

    def test_format_sql_with_json_column(self):
        schema = {
            "datasource_type": "pg",
            "datasource_name": "db",
            "schema": {
                "events": {
                    "columns": [
                        {
                            "name": "metadata",
                            "type": "jsonb",
                            "nullable": True,
                            "nested_schema": {
                                "type": "object",
                                "properties": {
                                    "source": {"type": "string"},
                                    "tags": {"type": "array", "items": {"type": "string"}},
                                },
                            },
                        }
                    ]
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "pg")
        assert "metadata(json)" in result
        assert "source(str)" in result
        assert "tags([str])" in result

    def test_format_sql_empty_schema(self):
        result = DatabaseOperationsService.format_schema_for_prompt({}, "pg")
        assert result == ""

    def test_format_sql_none_schema(self):
        result = DatabaseOperationsService.format_schema_for_prompt(None, "pg")  # type: ignore[arg-type]
        assert result == ""

    def test_format_sql_pg_type_normalization(self):
        schema = {
            "datasource_type": "pg",
            "datasource_name": "testdb",
            "schema": {"test": {"columns": []}},
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "pg")
        assert "PostgreSQL" in result
        assert "[PG:" not in result.upper()

    def test_format_sql_mysql_header(self):
        schema = {
            "datasource_type": "mysql",
            "datasource_name": "testdb",
            "schema": {"test": {"columns": []}},
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "mysql")
        assert "[MYSQL:testdb]" in result

    def test_format_sql_column_annotation(self):
        schema = {
            "datasource_type": "pg",
            "datasource_name": "db",
            "schema": {
                "users": {
                    "columns": [
                        {
                            "name": "status",
                            "type": "varchar",
                            "nullable": True,
                            "annotation": "active/inactive/pending",
                        },
                    ]
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "pg")
        assert "[active/inactive/pending]" in result


class TestMongoCompactFormatting:
    """Tests for MongoDB schema compact formatting."""

    def test_format_mongo_simple_collection(self):
        schema = {
            "database_name": "mydb",
            "schema": {
                "users": {
                    "nested_schema": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "age": {"type": "integer"},
                        },
                    }
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "mongo")
        assert "[MongoDB:mydb]" in result
        assert "users:" in result
        assert "name(str)" in result
        assert "age(int)" in result

    def test_format_mongo_nested_object(self):
        schema = {
            "database_name": "mydb",
            "schema": {
                "users": {
                    "nested_schema": {
                        "type": "object",
                        "properties": {
                            "address": {
                                "type": "object",
                                "properties": {"city": {"type": "string"}, "zip": {"type": "string"}},
                            }
                        },
                    }
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "mongo")
        assert "address({city(str), zip(str)})" in result

    def test_format_mongo_array_of_primitives(self):
        schema = {
            "database_name": "mydb",
            "schema": {
                "posts": {
                    "nested_schema": {
                        "type": "object",
                        "properties": {
                            "tags": {"type": "array", "items": {"type": "string"}},
                        },
                    }
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "mongo")
        assert "tags([str])" in result

    def test_format_mongo_array_of_objects(self):
        schema = {
            "database_name": "mydb",
            "schema": {
                "orders": {
                    "nested_schema": {
                        "type": "object",
                        "properties": {
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "product": {"type": "string"},
                                        "qty": {"type": "integer"},
                                    },
                                },
                            },
                        },
                    }
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "mongo")
        assert "items([{product(str), qty(int)}])" in result

    def test_format_mongo_with_description(self):
        schema = {
            "database_name": "mydb",
            "schema": {
                "users": {
                    "nested_schema": {"type": "object", "properties": {"name": {"type": "string"}}},
                    "description": "User profiles",
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "mongo")
        assert "// User profiles" in result

    def test_format_mongo_with_sample_fields(self):
        schema = {
            "database_name": "mydb",
            "schema": {
                "logs": {
                    "sample_fields": ["timestamp", "level", "message"],
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "mongo")
        assert "logs: timestamp, level, message" in result

    def test_format_mongo_empty_collection(self):
        schema = {
            "database_name": "mydb",
            "schema": {
                "empty": {},
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "mongo")
        assert "empty: (empty)" in result


class TestDuckDBCompactFormatting:
    """Tests for DuckDB/file schema compact formatting."""

    def test_format_duckdb_single_file(self):
        schema = {
            "database_name": "sales",
            "schema": {
                "sales": {
                    "filename": "sales.csv",
                    "row_count": 1000,
                    "columns": [
                        {"name": "date", "type": "date", "nullable": True},
                        {"name": "amount", "type": "double", "nullable": True},
                    ],
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "duckdb")
        assert "[DuckDB:sales.csv (1000 rows)]" in result
        assert "date(date)" in result
        assert "amount(float)" in result

    def test_format_duckdb_multiple_files(self):
        schema = {
            "database_name": "dataset",
            "schema": {
                "orders": {
                    "filename": "orders.csv",
                    "row_count": 500,
                    "columns": [{"name": "id", "type": "integer", "nullable": False}],
                },
                "products": {
                    "filename": "products.csv",
                    "row_count": 100,
                    "columns": [{"name": "name", "type": "varchar", "nullable": True}],
                },
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "duckdb")
        assert "[DuckDB:dataset]" in result
        assert "orders (500 rows)" in result
        assert "products (100 rows)" in result

    def test_format_duckdb_with_description(self):
        schema = {
            "database_name": "sales",
            "schema": {
                "data": {
                    "filename": "data.csv",
                    "row_count": 100,
                    "columns": [{"name": "id", "type": "integer", "nullable": False}],
                    "description": "Main data table",
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "duckdb")
        assert "// Main data table" in result


class TestFileSchemaFormatting:
    """Tests for file_operations schema formatting."""

    def test_format_file_single_csv(self):
        schema = {
            "filename": "data.csv",
            "row_count": 500,
            "datasource_type": "csv",
            "columns": [
                {"name": "id", "type": "integer", "nullable": False},
                {"name": "name", "type": "varchar", "nullable": True},
            ],
        }
        result = DataFrameFileService.format_file_schema_for_prompt(schema)
        assert "[DuckDB:data.csv (500 rows)]" in result
        assert "id(int!)" in result
        assert "name(str)" in result

    def test_format_file_excel_multiple_sheets(self):
        schema = {
            "filename": "workbook.xlsx",
            "datasource_type": "excel",
            "schema": {
                "Sheet1": {
                    "filename": "workbook.xlsx",
                    "row_count": 100,
                    "columns": [{"name": "a", "type": "integer", "nullable": True}],
                },
                "Sheet2": {
                    "filename": "workbook.xlsx",
                    "row_count": 200,
                    "columns": [{"name": "b", "type": "varchar", "nullable": True}],
                },
            },
        }
        result = DataFrameFileService.format_file_schema_for_prompt(schema)
        assert "[Excel:workbook.xlsx (2 sheets)]" in result
        assert "Sheet1 (100 rows)" in result
        assert "Sheet2 (200 rows)" in result

    def test_format_file_multiple_files(self):
        schema = {
            "datasource_type": "csv",
            "schema": {
                "file1": {
                    "filename": "file1.csv",
                    "row_count": 50,
                    "columns": [{"name": "x", "type": "integer", "nullable": True}],
                },
                "file2": {
                    "filename": "file2.csv",
                    "row_count": 75,
                    "columns": [{"name": "y", "type": "varchar", "nullable": True}],
                },
            },
        }
        result = DataFrameFileService.format_file_schema_for_prompt(schema)
        assert "[DuckDB:2 files]" in result
        assert "file1 (50 rows)" in result
        assert "file2 (75 rows)" in result

    def test_format_file_with_annotation(self):
        schema = {
            "filename": "data.csv",
            "row_count": 100,
            "datasource_type": "csv",
            "columns": [
                {"name": "status", "type": "varchar", "nullable": True, "annotation": "A/B/C"},
            ],
        }
        result = DataFrameFileService.format_file_schema_for_prompt(schema)
        assert "[A/B/C]" in result

    def test_format_file_with_description(self):
        schema = {
            "filename": "data.csv",
            "row_count": 100,
            "datasource_type": "csv",
            "columns": [{"name": "id", "type": "integer", "nullable": False}],
            "description": "Sales data",
        }
        result = DataFrameFileService.format_file_schema_for_prompt(schema)
        assert "// Sales data" in result


class TestNestedCompactFormatting:
    """Tests for nested schema compact formatting."""

    def test_nested_depth_limit(self):
        deeply_nested = {
            "type": "object",
            "properties": {
                "level1": {
                    "type": "object",
                    "properties": {
                        "level2": {
                            "type": "object",
                            "properties": {
                                "level3": {
                                    "type": "object",
                                    "properties": {"level4": {"type": "string"}},
                                }
                            },
                        }
                    },
                }
            },
        }
        result = DatabaseOperationsService._format_nested_compact(deeply_nested, max_depth=2)
        assert "obj" in result

    def test_nested_empty_schema(self):
        result = DatabaseOperationsService._format_nested_compact({})
        assert result == "obj"

    def test_nested_empty_object(self):
        schema = {"type": "object", "properties": {}}
        result = DatabaseOperationsService._format_nested_compact(schema)
        assert result == "obj"


class TestEdgeCases:
    """Edge case tests for schema formatting."""

    def test_empty_schema_returns_empty_string(self):
        assert DatabaseOperationsService.format_schema_for_prompt({}, "pg") == ""
        assert DatabaseOperationsService.format_schema_for_prompt(None, "pg") == ""  # type: ignore[arg-type]

    def test_unknown_db_type_returns_empty(self):
        schema = {"schema": {"test": {}}}
        result = DatabaseOperationsService.format_schema_compact(schema, "unknown_db")
        assert result == ""

    def test_large_table_count(self):
        schema = {
            "datasource_type": "pg",
            "datasource_name": "db",
            "schema": {
                f"table_{i}": {"columns": [{"name": "id", "type": "integer", "nullable": False}]} for i in range(50)
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "pg")
        lines = result.strip().split("\n")
        assert len(lines) == 51

    def test_special_characters_in_names(self):
        schema = {
            "datasource_type": "pg",
            "datasource_name": "db",
            "schema": {
                "user info": {
                    "columns": [
                        {"name": "first name", "type": "varchar", "nullable": True},
                    ]
                }
            },
        }
        result = DatabaseOperationsService.format_schema_for_prompt(schema, "pg")
        assert "user info:" in result
        assert "first name(str)" in result

    def test_format_column_compact_with_all_options(self):
        col = {
            "name": "data",
            "type": "jsonb",
            "nullable": False,
            "nested_schema": {"type": "object", "properties": {"key": {"type": "string"}}},
        }
        result = DatabaseOperationsService._format_column_compact(col)
        assert "data(json)" in result
        assert "key(str)" in result
        assert "!" in result

    def test_file_type_preserved(self):
        schema = {
            "datasource_type": "file",
            "database_name": "upload",
            "schema": {
                "data": {
                    "filename": "data.parquet",
                    "row_count": 1000,
                    "columns": [{"name": "id", "type": "integer", "nullable": False}],
                }
            },
        }
        result = DatabaseOperationsService.format_schema_compact(schema, "file")
        assert "[DuckDB:" in result
