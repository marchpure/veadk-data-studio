from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import select

import server.tools.agentic as agentic_module
from server.models.notebook_assets import NotebookAsset
from server.services.semantic_model_service import SemanticModelService
from server.services.unified_agent import (
    _build_agent_tools,
    _load_skills_for_agent,
    _requests_dashboard_output,
    _resolve_semantic_model_binding,
    _semantic_model_instructions,
    _tool_output_value,
)
from server.tests.asset_helpers import current_tenant, seed_notebook, seed_semantic_model
from server.tools.agentic import _query_semantic_metric_impl


def _tool_names(tools: list) -> set[str]:
    return {str(getattr(tool, "name", None) or getattr(tool, "__name__", "")) for tool in tools}


@pytest.mark.asyncio
async def test_semantic_model_binding_persists_and_cannot_switch(test_client, test_session) -> None:
    tenant = await current_tenant(test_session)
    notebook = await seed_notebook(test_session, tenant)
    first_model = await seed_semantic_model(test_session, tenant, published=True)
    second_model = await seed_semantic_model(test_session, tenant, published=True)

    payload = await _resolve_semantic_model_binding(
        test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        notebook_id=notebook.id,
        requested_model_id=first_model.slug,
    )

    assert payload is not None
    assert payload["id"] == first_model.slug
    binding = await test_session.scalar(
        select(NotebookAsset).where(
            NotebookAsset.notebook_id == notebook.id,
            NotebookAsset.asset_type == "semantic_model",
        )
    )
    assert binding is not None
    assert binding.asset_id == first_model.slug
    assert binding.usage_policy_json == {
        "purpose": "governed_ask_data",
        "published_version": "v1",
        "raw_sql_fallback": False,
    }

    with pytest.raises(ValueError, match="already bound"):
        await _resolve_semantic_model_binding(
            test_session,
            tenant_id=tenant.id,
            user_id=tenant.owner_id,
            notebook_id=notebook.id,
            requested_model_id=second_model.slug,
        )


@pytest.mark.asyncio
async def test_semantic_model_binding_rejects_unpublished_model(test_client, test_session) -> None:
    tenant = await current_tenant(test_session)
    notebook = await seed_notebook(test_session, tenant)
    draft_model = await seed_semantic_model(test_session, tenant, published=False)

    with pytest.raises(ValueError, match="Publish the Semantic Model"):
        await _resolve_semantic_model_binding(
            test_session,
            tenant_id=tenant.id,
            user_id=tenant.owner_id,
            notebook_id=notebook.id,
            requested_model_id=draft_model.slug,
        )


@pytest.mark.asyncio
async def test_bound_agent_defaults_to_governed_query_only(monkeypatch) -> None:
    tools = _build_agent_tools([], semantic_model_bound=True)

    assert _tool_names(tools) == {"query_semantic_metric"}

    dashboard_tools = _build_agent_tools(
        [],
        semantic_model_bound=True,
        allow_dashboard_tools=True,
    )
    assert _tool_names(dashboard_tools) == {
        "query_semantic_metric",
        "get_chart_styling",
        "start_html_generation",
        "get_existing_html",
        "apply_html_patch",
        "dashboard_search_replace",
        "generate_dashboard_screenshot",
    }

    async def fail_if_skills_are_loaded(*_args, **_kwargs):
        raise AssertionError("bound conversations must not load workspace skills")

    monkeypatch.setattr(
        "server.services.unified_agent.SkillRegistry.get_enabled_skills",
        fail_if_skills_are_loaded,
    )
    instructions, enabled, names, custom = await _load_skills_for_agent(
        tenant_id=SimpleNamespace(),
        user_id=SimpleNamespace(),
        session=SimpleNamespace(),
        tools=dashboard_tools,
        instructions="governed",
        allow_skill_tools=False,
    )
    assert instructions == "governed"
    assert enabled == {}
    assert names == []
    assert custom == {}
    assert _tool_names(dashboard_tools).isdisjoint(
        {
            "execute_sql_query",
            "execute_duckdb_query",
            "execute_mongo_query",
            "execute_skill_api",
            "search_datasets",
            "save_query",
        }
    )


def test_semantic_model_instructions_require_governed_metric_tool() -> None:
    prompt = _semantic_model_instructions(
        {
            "id": "sales-model",
            "name": "Sales",
            "domain": "Revenue",
            "publishedVersion": "v3",
            "metrics": [
                {
                    "id": "paid_revenue",
                    "businessName": "Paid Revenue",
                    "definition": "Revenue from paid orders.",
                    "dimensions": ["region"],
                    "unit": "USD",
                }
            ],
            "dimensions": [{"id": "region", "name": "Region", "description": "Sales region"}],
        }
    )

    assert "call query_semantic_metric" in prompt
    assert "Do not use raw SQL" in prompt
    assert "state the gap instead of bypassing the model" in prompt
    assert "dashboard_output_requested: false" in prompt
    assert "Never create one merely" in prompt


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Show Revenue by Region", False),
        ("What is paid revenue?", False),
        ("Build a revenue dashboard", True),
        ("Visualize revenue by region", True),
        ("生成一个区域收入看板", True),
        ("把区域收入画图", True),
    ],
)
def test_dashboard_tools_require_explicit_user_intent(message: str, expected: bool) -> None:
    assert _requests_dashboard_output(message) is expected


def test_tool_output_value_prefers_sdk_output_over_raw_item() -> None:
    item = SimpleNamespace(
        output='{"success": true, "resolvedMetric": "Paid Revenue"}',
        raw_item=SimpleNamespace(call_id="call-semantic"),
    )
    assert json.loads(_tool_output_value(item))["resolvedMetric"] == "Paid Revenue"

    legacy_item = SimpleNamespace(
        output=None,
        raw_item={"call_id": "call-semantic", "output": '{"success": true}'},
    )
    assert json.loads(_tool_output_value(legacy_item))["success"] is True


def test_parallel_tool_output_uses_matching_call_identity() -> None:
    semantic_call = SimpleNamespace(call_id="call-semantic", name="query_semantic_metric")
    dashboard_call = SimpleNamespace(call_id="call-dashboard", name="start_html_generation")
    pending = {
        semantic_call.call_id: semantic_call.name,
        dashboard_call.call_id: dashboard_call.name,
    }

    dashboard_output = Mock(call_id="call-dashboard")
    semantic_output = Mock(call_id="call-semantic")

    assert pending.pop(dashboard_output.call_id) == "start_html_generation"
    assert pending.pop(semantic_output.call_id) == "query_semantic_metric"


@pytest.mark.asyncio
async def test_semantic_metric_query_persists_review_evidence(test_client, test_session, monkeypatch) -> None:
    tenant = await current_tenant(test_session)
    notebook = await seed_notebook(test_session, tenant)
    model = await seed_semantic_model(test_session, tenant, published=True)
    await _resolve_semantic_model_binding(
        test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        notebook_id=notebook.id,
        requested_model_id=model.slug,
    )

    async def fake_sessions():
        yield test_session

    async def fake_query_metric(**_kwargs):
        return {
            "status": "completed",
            "resolvedMetric": "Paid Revenue",
            "metricDefinition": "Revenue from paid orders.",
            "modelVersion": "v1",
            "freshness": "2026-08-18T10:00:00",
            "policyDecision": "allowed",
            "sql": "SELECT SUM(net_amount) AS paid_revenue FROM orders",
            "lineage": ["orders.net_amount"],
            "evidence": [{"kind": "sql", "content": "SELECT SUM(net_amount) FROM orders"}],
            "snapshot": {"id": "snapshot-1", "hash": "sha256:test"},
            "dataThrough": "2026-08-17T23:59:59",
            "snapshotId": "snapshot-1",
            "snapshotHash": "sha256:test",
            "returnedCount": 1,
            "result": [{"paid_revenue": 230}],
        }

    monkeypatch.setattr(agentic_module, "get_async_session", fake_sessions)
    monkeypatch.setattr(SemanticModelService, "run_query_metric", staticmethod(fake_query_metric))
    ctx = SimpleNamespace(
        context={
            "tenant_id": tenant.id,
            "user_id": tenant.owner_id,
            "notebook_id": notebook.id,
            "semantic_model_id": model.slug,
        }
    )

    response = json.loads(
        await _query_semantic_metric_impl(
            ctx,
            model_id=model.slug,
            metric="paid_revenue",
            dimension="order_status",
        )
    )

    assert response["success"] is True
    binding = await test_session.scalar(
        select(NotebookAsset).where(
            NotebookAsset.notebook_id == notebook.id,
            NotebookAsset.asset_type == "semantic_model",
            NotebookAsset.asset_id == model.slug,
        )
    )
    assert binding is not None
    latest = binding.usage_policy_json["latest_query"]
    assert latest["resolvedMetric"] == "Paid Revenue"
    assert latest["sql"].startswith("SELECT SUM")
    assert latest["snapshotHash"] == "sha256:test"
    assert latest["policyDecision"] == "allowed"
