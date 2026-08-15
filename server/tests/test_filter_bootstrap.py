import json
from typing import Any

import pytest

from server.services.filter_config_service import (
    harmonize_filter_definitions,
    merge_filters_non_destructive,
    normalize_filters_for_client,
)
from server.services.filter_inference_service import DashboardFilterInferenceService
from server.tools import agentic as agentic_module


class _DummyCtx:
    def __init__(self, context: dict[str, Any]):
        self.context = context


def test_merge_filters_non_destructive_preserves_existing() -> None:
    existing = [
        {
            "id": "filter_status",
            "query_id": "q1",
            "field_name": "status",
            "display_label": "Status",
            "filter_type": "select",
            "operator": "eq",
        }
    ]
    inferred = [
        {
            "id": "auto_q1_status",
            "query_id": "q1",
            "field_name": "status",
            "display_label": "Status",
            "filter_type": "select",
            "operator": "eq",
        },
        {
            "id": "auto_q1_region",
            "query_id": "q1",
            "field_name": "region",
            "display_label": "Region",
            "filter_type": "select",
            "operator": "eq",
        },
    ]

    merged = merge_filters_non_destructive(existing, inferred)

    assert len(merged) == 2
    assert any(item["field_name"] == "status" and item["id"] == "filter_status" for item in merged)
    assert any(item["field_name"] == "region" for item in merged)


def test_merge_filters_non_destructive_allows_shared_id_for_same_field_across_queries() -> None:
    existing = [
        {
            "id": "filter_created_at",
            "query_id": "q1",
            "field_name": "t.created_at",
            "display_label": "Created Date",
            "filter_type": "date_range",
            "operator": "between",
        }
    ]
    inferred = [
        {
            "id": "filter_created_at",
            "query_id": "q2",
            "field_name": "t.created_at",
            "display_label": "Created Date",
            "filter_type": "date_range",
            "operator": "between",
        }
    ]

    merged = merge_filters_non_destructive(existing, inferred)

    assert len(merged) == 2
    ids = [item["id"] for item in merged]
    assert ids == ["filter_created_at", "filter_created_at"]


def test_normalize_filters_for_client_canonicalizes_ids_and_deduplicates() -> None:
    raw_filters = [
        {
            "id": "auto_q1_t_created_at",
            "query_id": "q1",
            "field_name": "t.created_at",
            "display_label": "Tenant Created Date",
        },
        {
            "id": "auto_q1_t_created_at_duplicate",
            "query_id": "q1",
            "field_name": "t.created_at",
            "display_label": "Tenant Created Date",
        },
        {
            "id": "auto_q2_t_created_at",
            "query_id": "q2",
            "field_name": "t.created_at",
            "display_label": "Tenant Created Date",
        },
    ]

    normalized = normalize_filters_for_client(raw_filters)

    assert len(normalized) == 2
    assert normalized[0]["id"] == "filter_t_created_at"
    assert normalized[1]["id"] == "filter_t_created_at"


def test_harmonize_filter_definitions_aligns_shared_filter_shapes() -> None:
    raw_filters = [
        {
            "id": "legacy_filter",
            "query_id": "q1",
            "field_name": "t.name",
            "display_label": "Tenant Name",
            "filter_type": "select",
            "operator": "eq",
            "options": ["Acme", "Globex"],
        },
        {
            "id": "legacy_filter",
            "query_id": "q2",
            "field_name": "t.name",
            "display_label": "t.name",
            "filter_type": "text",
            "operator": "contains",
            "options": None,
        },
    ]

    normalized = harmonize_filter_definitions(raw_filters)

    assert len(normalized) == 2
    assert all(item["id"] == "filter_t_name" for item in normalized)
    assert all(item["filter_type"] == "select" for item in normalized)
    assert all(item["operator"] == "eq" for item in normalized)
    assert all(item["display_label"] == "Tenant Name" for item in normalized)
    assert all(item["options"] == ["Acme", "Globex"] for item in normalized)


def test_infer_sql_filter_candidates_ignores_computed_and_aggregate() -> None:
    query = """
        SELECT o.region, COUNT(*) AS total, o.status AS order_status, UPPER(o.city) AS city_upper
        FROM orders o
        GROUP BY o.region, o.status, o.city
    """

    candidates = DashboardFilterInferenceService.infer_sql_filter_candidates(query, "pg")

    field_names = {candidate["field_name"] for candidate in candidates}
    output_names = {candidate["output_name"] for candidate in candidates}

    assert "o.region" in field_names
    assert "o.status" in field_names
    assert "region" in output_names
    assert "order_status" in output_names
    assert "total" not in output_names
    assert "city_upper" not in output_names


@pytest.mark.asyncio
async def test_bootstrap_for_saved_query_merges_existing_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeSession:
        def __init__(self):
            self.commits = 0

        async def commit(self) -> None:
            self.commits += 1

    class _FakeConnection:
        id = "conn-1"
        type = "pg"

        async def get_decrypted_connection_obj(self, session):
            return {"host": "localhost"}

    class _FakeDataset:
        type = "connection"
        connection = _FakeConnection()
        files = []
        id = "dataset-1"

    class _FakeQuery:
        id = "q1"
        query = "SELECT region, status, user_id FROM orders"
        query_type = "sql"
        dataset = _FakeDataset()
        filter_contract = None

    class _FakeNotebook:
        def __init__(self):
            self.filters_config = json.dumps(
                {
                    "version": 1,
                    "filters": [
                        {
                            "id": "filter_status",
                            "query_id": "q1",
                            "field_name": "status",
                            "display_label": "Status",
                            "filter_type": "select",
                            "operator": "eq",
                        }
                    ],
                }
            )

    fake_notebook = _FakeNotebook()
    fake_query_obj = _FakeQuery()

    class _FakeQueryRepository:
        def __init__(self, session):
            self._session = session

        async def get_with_relations(self, query_id: str):
            return fake_query_obj if query_id == "q1" else None

        async def get(self, query_id: str):
            return fake_query_obj if query_id == "q1" else None

    class _FakeNotebookRepository:
        def __init__(self, session):
            self._session = session

        async def get(self, notebook_id: str):
            return fake_notebook if notebook_id == "n1" else None

    async def _fake_execute_raw_query(
        query: str,
        db_type: str,
        connection_id: str,
        connection_obj: dict[str, Any] | None = None,
        limit: int = None,
        params: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        if 'SELECT "region" AS "__value"' in query:
            return {"success": True, "result": [{"__value": "EMEA"}, {"__value": "APAC"}, {"__value": "NA"}]}
        if 'SELECT "status" AS "__value"' in query:
            return {"success": True, "result": [{"__value": "open"}, {"__value": "closed"}]}
        if 'SELECT "user_id" AS "__value"' in query:
            return {
                "success": True,
                "result": [{"__value": f"user_{idx}"} for idx in range(40)],
            }
        return {"success": False, "error": "unexpected probe"}

    monkeypatch.setattr("server.services.filter_inference_service.QueryRepository", _FakeQueryRepository)
    monkeypatch.setattr("server.services.filter_inference_service.NotebookRepository", _FakeNotebookRepository)
    monkeypatch.setattr(
        "server.services.filter_inference_service.AsyncRawQueryService.execute_raw_query",
        _fake_execute_raw_query,
    )

    async def _fake_sync_query_filter_contracts(session, filters_list):
        return ["q1"]

    monkeypatch.setattr(
        "server.services.filter_inference_service.sync_query_filter_contracts",
        _fake_sync_query_filter_contracts,
    )

    session = _FakeSession()
    result = await DashboardFilterInferenceService.bootstrap_for_saved_query(
        session=session, notebook_id="n1", query_id="q1"
    )

    assert result["status"] == "added"
    assert result["added_count"] == 1
    assert result["filters"][0]["field_name"] == "region"
    assert session.commits == 1

    saved_config = json.loads(fake_notebook.filters_config)
    saved_fields = {f["field_name"] for f in saved_config["filters"]}
    assert saved_fields == {"status", "region"}


@pytest.mark.asyncio
async def test_save_query_includes_auto_filter_bootstrap_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeSession:
        async def close(self):
            return None

    async def _fake_get_async_session():
        yield _FakeSession()

    async def _fake_execute_and_save_query(
        session,
        query: str,
        connection_id: str,
        notebook_id: str,
        db_type: str,
        name: str,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "query_id": "q1",
            "generated_schema": {"region": "string"},
            "data": [{"region": "EMEA"}],
        }

    async def _fake_bootstrap(session, notebook_id: str, query_id: str) -> dict[str, Any]:
        return {
            "status": "added",
            "message": "Added 2 inferred filters",
            "added_count": 2,
            "filters": [{"id": "f1"}, {"id": "f2"}],
            "updated_query_contracts": ["q1"],
        }

    monkeypatch.setattr(agentic_module, "get_async_session", _fake_get_async_session)
    monkeypatch.setattr(agentic_module.QueryService, "execute_and_save_query", _fake_execute_and_save_query)
    monkeypatch.setattr(
        agentic_module.DashboardFilterInferenceService,
        "bootstrap_for_saved_query",
        _fake_bootstrap,
    )

    ctx = _DummyCtx(
        {
            "notebook_id": "n1",
            "db_type": "pg",
            "tenant_id": "t1",
            "user_id": "u1",
        }
    )

    # save_query is wrapped by @function_tool — extract the original async function
    save_query_fn = agentic_module.save_query
    if hasattr(save_query_fn, "on_invoke_tool"):
        save_query_fn = save_query_fn.on_invoke_tool._invoke_tool_impl.__closure__[-1].cell_contents

    response = await save_query_fn(
        ctx=ctx,
        query="SELECT region FROM orders",
        name="Sales By Region",
        connection_id="conn-1",
        is_dashboard=True,
    )
    payload = json.loads(response)

    assert payload["success"] is True
    assert payload["query_id"] == "q1"
    assert payload["filter_bootstrap_status"] == "added"
    assert payload["auto_filters_added_count"] == 2
    assert payload["updated_query_contracts"] == ["q1"]
