"""
Tests for RedactionService — both column-level and table-level redaction.

Run with:
    cd server && PYTHONPATH=.. uv run pytest tests/test_redaction_service.py -v -s
"""

from __future__ import annotations

import copy
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.auth.tenant_context import set_tenant_id
from server.db.base import Base
from server.services.redaction_service import REDACTION_MASK, RedactionService

DATASOURCE_ID = str(uuid.uuid4())
TENANT_ID = uuid.uuid4()


@pytest_asyncio.fixture(scope="function")
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    set_tenant_id(TENANT_ID)
    async with factory() as session:
        yield session
    set_tenant_id(None)

    await engine.dispose()


async def _seed_annotations(session: AsyncSession, annotations: list[dict]) -> None:
    from server.models.datasource_annotations import DatasourceAnnotation

    for ann in annotations:
        obj = DatasourceAnnotation(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            datasource_id=uuid.UUID(DATASOURCE_ID),
            table_name=ann["table_name"],
            column_name=ann.get("column_name"),
            annotation_type=ann["annotation_type"],
            content=ann.get("content", "redacted"),
        )
        session.add(obj)
    await session.commit()


# ---------------------------------------------------------------------------
# get_redacted_columns
# ---------------------------------------------------------------------------


class TestGetRedactedColumns:
    @pytest.mark.asyncio
    async def test_no_annotations(self, db_session: AsyncSession):
        result = await RedactionService.get_redacted_columns(DATASOURCE_ID, db_session)
        assert result == {}

    @pytest.mark.asyncio
    async def test_single_column_redaction(self, db_session: AsyncSession):
        await _seed_annotations(
            db_session,
            [
                {"table_name": "users", "column_name": "ssn", "annotation_type": "column_redaction"},
            ],
        )
        result = await RedactionService.get_redacted_columns(DATASOURCE_ID, db_session)
        assert result == {"users": {"ssn"}}

    @pytest.mark.asyncio
    async def test_multiple_columns_across_tables(self, db_session: AsyncSession):
        await _seed_annotations(
            db_session,
            [
                {"table_name": "users", "column_name": "ssn", "annotation_type": "column_redaction"},
                {"table_name": "users", "column_name": "email", "annotation_type": "column_redaction"},
                {"table_name": "orders", "column_name": "credit_card", "annotation_type": "column_redaction"},
            ],
        )
        result = await RedactionService.get_redacted_columns(DATASOURCE_ID, db_session)
        assert result == {"users": {"ssn", "email"}, "orders": {"credit_card"}}

    @pytest.mark.asyncio
    async def test_ignores_table_redaction_annotations(self, db_session: AsyncSession):
        await _seed_annotations(
            db_session,
            [
                {"table_name": "users", "column_name": None, "annotation_type": "table_redaction"},
                {"table_name": "users", "column_name": "ssn", "annotation_type": "column_redaction"},
            ],
        )
        result = await RedactionService.get_redacted_columns(DATASOURCE_ID, db_session)
        assert result == {"users": {"ssn"}}


# ---------------------------------------------------------------------------
# get_redacted_tables
# ---------------------------------------------------------------------------


class TestGetRedactedTables:
    @pytest.mark.asyncio
    async def test_no_annotations(self, db_session: AsyncSession):
        result = await RedactionService.get_redacted_tables(DATASOURCE_ID, db_session)
        assert result == set()

    @pytest.mark.asyncio
    async def test_single_table_redaction(self, db_session: AsyncSession):
        await _seed_annotations(
            db_session,
            [
                {"table_name": "secrets", "column_name": None, "annotation_type": "table_redaction"},
            ],
        )
        result = await RedactionService.get_redacted_tables(DATASOURCE_ID, db_session)
        assert result == {"secrets"}

    @pytest.mark.asyncio
    async def test_multiple_table_redactions(self, db_session: AsyncSession):
        await _seed_annotations(
            db_session,
            [
                {"table_name": "secrets", "column_name": None, "annotation_type": "table_redaction"},
                {"table_name": "private_data", "column_name": None, "annotation_type": "table_redaction"},
            ],
        )
        result = await RedactionService.get_redacted_tables(DATASOURCE_ID, db_session)
        assert result == {"secrets", "private_data"}

    @pytest.mark.asyncio
    async def test_ignores_column_redaction(self, db_session: AsyncSession):
        await _seed_annotations(
            db_session,
            [
                {"table_name": "users", "column_name": "ssn", "annotation_type": "column_redaction"},
            ],
        )
        result = await RedactionService.get_redacted_tables(DATASOURCE_ID, db_session)
        assert result == set()


# ---------------------------------------------------------------------------
# redact_result_rows — column-level
# ---------------------------------------------------------------------------


class TestRedactResultRowsColumnLevel:
    def test_list_of_dicts(self):
        rows = [
            {"id": 1, "name": "Alice", "ssn": "123-45-6789"},
            {"id": 2, "name": "Bob", "ssn": "987-65-4321"},
        ]
        redacted_cols = {"users": {"ssn"}}
        result = RedactionService.redact_result_rows(rows, redacted_cols)
        for row in result:
            assert row["ssn"] == REDACTION_MASK
            assert row["name"] != REDACTION_MASK

    def test_dict_with_columns_and_rows(self):
        data = {
            "columns": ["id", "name", "ssn"],
            "rows": [
                [1, "Alice", "123-45-6789"],
                [2, "Bob", "987-65-4321"],
            ],
        }
        redacted_cols = {"users": {"ssn"}}
        result = RedactionService.redact_result_rows(data, redacted_cols)
        for row in result["rows"]:
            assert row[2] == REDACTION_MASK
            assert row[1] != REDACTION_MASK

    def test_no_redacted_columns_returns_unchanged(self):
        rows = [{"id": 1, "name": "Alice"}]
        original = copy.deepcopy(rows)
        result = RedactionService.redact_result_rows(rows, {})
        assert result == original

    def test_empty_results(self):
        assert RedactionService.redact_result_rows([], {"t": {"c"}}) == []
        assert RedactionService.redact_result_rows(None, {"t": {"c"}}) is None


# ---------------------------------------------------------------------------
# redact_result_rows — table-level (mask ALL columns)
# ---------------------------------------------------------------------------


class TestRedactResultRowsTableLevel:
    def test_list_of_dicts_all_masked(self):
        rows = [
            {"id": 1, "name": "Alice", "ssn": "123-45-6789"},
            {"id": 2, "name": "Bob", "ssn": "987-65-4321"},
        ]
        result = RedactionService.redact_result_rows(rows, {}, redacted_tables={"users"}, table_name="users")
        for row in result:
            assert all(v == REDACTION_MASK for v in row.values())

    def test_dict_with_columns_and_rows_all_masked(self):
        data = {
            "columns": ["id", "name", "email", "ssn"],
            "rows": [
                [1, "Alice", "a@b.com", "123"],
                [2, "Bob", "b@c.com", "456"],
            ],
        }
        result = RedactionService.redact_result_rows(data, {}, redacted_tables={"users"}, table_name="users")
        for row in result["rows"]:
            assert all(v == REDACTION_MASK for v in row)

    def test_dict_rows_as_dicts_all_masked(self):
        data = {
            "columns": ["id", "name"],
            "rows": [
                {"id": 1, "name": "Alice"},
            ],
        }
        result = RedactionService.redact_result_rows(data, {}, redacted_tables={"t"}, table_name="t")
        assert result["rows"][0]["id"] == REDACTION_MASK
        assert result["rows"][0]["name"] == REDACTION_MASK

    def test_no_redacted_tables_falls_through_to_column_redaction(self):
        rows = [{"id": 1, "name": "Alice", "ssn": "123"}]
        result = RedactionService.redact_result_rows(rows, {"t": {"ssn"}}, redacted_tables=set())
        assert result[0]["ssn"] == REDACTION_MASK
        assert result[0]["name"] != REDACTION_MASK


# ---------------------------------------------------------------------------
# Combined: column + table redaction coexistence
# ---------------------------------------------------------------------------


class TestRedactResultRowsCombined:
    @pytest.mark.asyncio
    async def test_both_column_and_table_redaction(self, db_session: AsyncSession):
        await _seed_annotations(
            db_session,
            [
                {"table_name": "users", "column_name": "ssn", "annotation_type": "column_redaction"},
                {"table_name": "secrets", "column_name": None, "annotation_type": "table_redaction"},
            ],
        )

        cols = await RedactionService.get_redacted_columns(DATASOURCE_ID, db_session)
        tables = await RedactionService.get_redacted_tables(DATASOURCE_ID, db_session)

        assert cols == {"users": {"ssn"}}
        assert tables == {"secrets"}

        # Simulate query against the redacted TABLE — all values masked
        table_rows = [{"id": 1, "secret_data": "top-secret", "level": 5}]
        RedactionService.redact_result_rows(table_rows, cols, redacted_tables=tables, table_name="secrets")
        for row in table_rows:
            assert all(v == REDACTION_MASK for v in row.values())

        # Simulate query against the non-redacted table with column redaction
        user_rows = [{"id": 1, "name": "Alice", "ssn": "123-45-6789"}]
        RedactionService.redact_result_rows(user_rows, cols, redacted_tables=tables, table_name="users")
        assert user_rows[0]["ssn"] == REDACTION_MASK
        assert user_rows[0]["name"] == "Alice"
        assert user_rows[0]["id"] == 1


# ---------------------------------------------------------------------------
# redact_result_rows — flat list (distinct results)
# ---------------------------------------------------------------------------


class TestRedactFlatList:
    def test_flat_list_masked_when_table_redacted(self):
        results = ["Electronics", "Clothing", "Food"]
        redacted = RedactionService.redact_result_rows(results, {}, redacted_tables={"products"}, table_name="products")
        assert redacted == [REDACTION_MASK, REDACTION_MASK, REDACTION_MASK]

    def test_flat_list_unchanged_when_other_table_redacted(self):
        results = ["Electronics", "Clothing", "Food"]
        redacted = RedactionService.redact_result_rows(results, {}, redacted_tables={"secrets"}, table_name="products")
        assert redacted == ["Electronics", "Clothing", "Food"]

    def test_empty_flat_list(self):
        results = []
        redacted = RedactionService.redact_result_rows(results, {}, redacted_tables={"products"}, table_name="products")
        assert redacted == []


# ---------------------------------------------------------------------------
# redact_result_rows — scalar (count/countDocuments)
# ---------------------------------------------------------------------------


class TestRedactScalar:
    def test_integer_masked_when_table_redacted(self):
        result = RedactionService.redact_result_rows(42, {}, redacted_tables={"secrets"}, table_name="secrets")
        assert result == REDACTION_MASK

    def test_integer_unchanged_when_other_table_redacted(self):
        result = RedactionService.redact_result_rows(42, {}, redacted_tables={"secrets"}, table_name="orders")
        assert result == 42

    def test_float_masked_when_table_redacted(self):
        result = RedactionService.redact_result_rows(3.14, {}, redacted_tables={"secrets"}, table_name="secrets")
        assert result == REDACTION_MASK

    def test_zero_not_falsy_skipped(self):
        result = RedactionService.redact_result_rows(0, {}, redacted_tables={"secrets"}, table_name="secrets")
        assert result == REDACTION_MASK


# ---------------------------------------------------------------------------
# redact_result_rows — collection-aware masking
# ---------------------------------------------------------------------------


class TestCollectionAwareMasking:
    def test_non_redacted_collection_not_over_masked(self):
        rows = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        result = RedactionService.redact_result_rows(rows, {}, redacted_tables={"secrets"}, table_name="orders")
        assert result[0]["name"] == "Alice"
        assert result[1]["name"] == "Bob"

    def test_redacted_collection_fully_masked(self):
        rows = [{"id": 1, "data": "secret-value"}]
        result = RedactionService.redact_result_rows(rows, {}, redacted_tables={"secrets"}, table_name="secrets")
        assert all(v == REDACTION_MASK for v in result[0].values())
