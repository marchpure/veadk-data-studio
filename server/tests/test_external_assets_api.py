from __future__ import annotations

import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.mcp_api_key import MCPAPIKey
from server.models.semantic_models import SemanticModel
from server.models.tenant import Tenant
from server.models.user import User
from server.services.dashboard import DashboardService
from server.tests.asset_helpers import (
    current_tenant,
    seed_dashboard_asset,
    seed_semantic_metric_dashboard_asset,
    seed_semantic_model,
)

pytestmark = pytest.mark.asyncio


async def _seed_mcp_key(session: AsyncSession, tenant: Tenant, api_key: str = "byaan_test_external_key") -> str:
    db_key = MCPAPIKey(
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        name="External test key",
        key_hash=hashlib.sha256(api_key.encode()).hexdigest(),
        key_prefix=api_key[:13],
        is_active=True,
    )
    session.add(db_key)
    await session.commit()
    return api_key


async def _seed_other_tenant(session: AsyncSession) -> Tenant:
    user_id = uuid4()
    tenant_id = uuid4()
    user = User(
        id=user_id,
        email=f"other-{user_id}@example.test",
        hashed_password="hash",
        is_active=True,
        is_verified=True,
    )
    tenant = Tenant(id=tenant_id, name="Other Tenant", slug=f"other-{tenant_id}", owner_id=user_id)
    session.add_all([user, tenant])
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def test_external_assets_require_mcp_key(test_client) -> None:
    response = await test_client.get("/api/external/assets")
    invalid = await test_client.get("/api/external/assets", headers={"Authorization": "Bearer byaan_invalid"})

    assert response.status_code == 401
    assert invalid.status_code == 401


async def test_external_assets_return_only_published_assets(test_client, test_session) -> None:
    tenant = await current_tenant(test_session)
    api_key = await _seed_mcp_key(test_session, tenant)
    published = await seed_dashboard_asset(test_session, tenant, slug="external-published-dashboard", publish=True)
    draft = await seed_dashboard_asset(test_session, tenant, slug="external-draft-dashboard", publish=False)

    list_response = await test_client.get(
        "/api/external/assets?types=dashboard&limit=100",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    draft_response = await test_client.get(
        f"/api/external/assets/dashboard/{draft.id}",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    published_response = await test_client.get(
        f"/api/external/assets/dashboard/{published.id}",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert list_response.status_code == 200
    assert {item["asset_id"] for item in list_response.json()["data"]["items"]} == {str(published.id)}
    assert draft_response.status_code == 404
    assert published_response.status_code == 200
    payload = published_response.json()["data"]
    assert payload["publish_state"] == "published"
    assert payload["gate"]["blockers"] == []
    assert payload["version"] == "v1"
    assert payload["capability_kind"] == "dashboard_skill"
    assert payload["capability_package"]["package_type"] == "dashboard_skill"
    assert payload["capability_package"]["runtime"]["query_url"] == f"/api/external/assets/dashboard/{published.id}/query"
    assert payload["capability_package"]["dashboard"]["data_views"]
    assert "connection_obj_encrypted" not in str(payload["capability_package"])
    assert payload["query_url"] == f"/api/external/assets/dashboard/{published.id}/query"
    assert "mcp_url" not in payload


async def test_external_dashboard_asset_describes_semantic_metric_views(test_client, test_session) -> None:
    tenant = await current_tenant(test_session)
    api_key = await _seed_mcp_key(test_session, tenant)
    dashboard = await seed_semantic_metric_dashboard_asset(
        test_session,
        tenant,
        slug="external-oracle-semantic-dashboard",
        publish=True,
    )

    response = await test_client.get(
        f"/api/external/assets/dashboard/{dashboard.id}",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["publish_state"] == "published"
    assert payload["query_url"] == f"/api/external/assets/dashboard/{dashboard.id}/query"
    assert payload["capabilities"]["metrics"][0]["id"] == "ticket_count"
    assert payload["provenance"]["lineage"]["data_views"][0]["lineage"][0]["ref"].startswith(
        "oracle-local-extract-sanitized/"
    )


async def test_external_assets_support_q_and_page_aliases(test_client, test_session) -> None:
    tenant = await current_tenant(test_session)
    api_key = await _seed_mcp_key(test_session, tenant)
    await seed_dashboard_asset(test_session, tenant, slug="alpha-revenue-dashboard", publish=True)
    second = await seed_dashboard_asset(test_session, tenant, slug="beta-revenue-dashboard", publish=True)
    await seed_dashboard_asset(test_session, tenant, slug="gamma-cost-dashboard", publish=True)

    filtered = await test_client.get(
        "/api/external/assets?types=dashboard&q=beta&page=1&page_size=1",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    first_page = await test_client.get(
        "/api/external/assets?types=dashboard&page=1&page_size=1",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    second_page = await test_client.get(
        f"/api/external/assets?types=dashboard&cursor={first_page.json()['data']['next_cursor']}&page_size=1",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert filtered.status_code == 200
    assert filtered.json()["data"]["total"] == 1
    assert filtered.json()["data"]["items"][0]["asset_id"] == str(second.id)
    assert first_page.status_code == 200
    assert first_page.json()["data"]["next_cursor"] == "1"
    assert second_page.status_code == 200
    assert len(second_page.json()["data"]["items"]) == 1


async def test_external_assets_cross_tenant_returns_404(test_client, test_session) -> None:
    tenant = await current_tenant(test_session)
    api_key = await _seed_mcp_key(test_session, tenant)
    other_tenant = await _seed_other_tenant(test_session)
    other_dashboard = await seed_dashboard_asset(
        test_session,
        other_tenant,
        slug="external-cross-tenant-dashboard",
        publish=True,
    )

    response = await test_client.get(
        f"/api/external/assets/dashboard/{other_dashboard.id}",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert response.status_code == 404


async def test_external_assets_reject_unsupported_type_and_clamp_limit(test_client, test_session) -> None:
    tenant = await current_tenant(test_session)
    api_key = await _seed_mcp_key(test_session, tenant)

    unsupported = await test_client.get(
        "/api/external/assets?types=skill",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    too_large = await test_client.get(
        "/api/external/assets?limit=101",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert unsupported.status_code == 400
    assert too_large.status_code == 200


async def test_external_dashboard_query_dispatches_service_and_rejects_writes(
    test_client,
    test_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = await current_tenant(test_session)
    api_key = await _seed_mcp_key(test_session, tenant)
    dashboard = await seed_dashboard_asset(test_session, tenant, slug="external-query-dashboard", publish=True)

    captured: dict[str, object] = {}

    async def fake_query_dashboard(self, **kwargs):
        captured.update(kwargs)
        return {"contract_version": "dashboard.run.v1", "views": [{"data_view_id": "dv-paid-revenue"}]}

    monkeypatch.setattr(DashboardService, "query_dashboard", fake_query_dashboard)

    write_response = await test_client.post(
        f"/api/external/assets/dashboard/{dashboard.id}/query",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"query": "CREATE TABLE x (id INT)"},
    )
    query_response = await test_client.post(
        f"/api/external/assets/dashboard/{dashboard.id}/query",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"filters": {"order_status": "PAID"}, "data_view_ids": ["dv-paid-revenue"]},
    )

    assert write_response.status_code == 403
    assert query_response.status_code == 200
    assert captured["tenant_id"] == tenant.id
    assert captured["asset_id"] == dashboard.id
    assert captured["filters"] == {"order_status": "PAID"}
    assert captured["actor_type"] == "service"


async def test_external_semantic_model_query_dispatches_service(
    test_client,
    test_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = await current_tenant(test_session)
    api_key = await _seed_mcp_key(test_session, tenant)
    model = await seed_semantic_model(test_session, tenant, published=True)

    captured: dict[str, object] = {}

    async def fake_run_query_metric(**kwargs):
        captured.update(kwargs)
        return {"status": "completed", "resolvedMetric": "Paid Revenue", "result": [{"paid_revenue": 10}]}

    monkeypatch.setattr("server.routers.external_assets.SemanticModelService.run_query_metric", fake_run_query_metric)

    response = await test_client.post(
        f"/api/external/assets/semantic_model/{model.id}/query",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"metric": "paid_revenue", "dimension": "order_status", "limit": 5},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "completed"
    assert captured["tenant_id"] == tenant.id
    assert captured["slug"] == model.slug
    assert captured["request"]["metric"] == "paid_revenue"


async def test_external_semantic_model_query_denies_customer_contact_fields(test_client, test_session) -> None:
    tenant = await current_tenant(test_session)
    api_key = await _seed_mcp_key(test_session, tenant)
    model = await seed_semantic_model(test_session, tenant, published=True)

    response = await test_client.post(
        f"/api/external/assets/semantic_model/{model.id}/query",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"query": "列出客户姓名和电话", "metric": "paid_revenue"},
    )

    assert response.status_code == 403
    body = response.json()
    assert "Policy denied" in (body.get("detail") or body.get("message") or str(body))


async def test_external_semantic_model_query_returns_completed_data_and_evidence(
    test_client,
    test_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = await current_tenant(test_session)
    api_key = await _seed_mcp_key(test_session, tenant)
    uploaded = await test_client.post(
        "/api/source-resources/files",
        files={
            "file": (
                "revenue.csv",
                b"order_id,region,revenue,paid_at\n"
                b"1,East,120,2026-08-01\n"
                b"2,West,80,2026-08-02\n",
                "text/csv",
            )
        },
        data={"name": "external projected revenue"},
    )
    assert uploaded.status_code == 201
    projected_dataset_id = uploaded.json()["data"]["projected_dataset_id"]

    analyzed = await test_client.post(
        f"/api/datasources/{projected_dataset_id}/understanding/analyze",
        json={},
    )
    assert analyzed.status_code == 200
    selected = [
        candidate
        for candidate in analyzed.json()["data"]["candidates"]
        if candidate["candidate_type"] in {"schema_map", "data_truth", "relationship"}
    ]
    assert {candidate["candidate_type"] for candidate in selected} >= {"schema_map", "data_truth"}
    for candidate in selected:
        reviewed = await test_client.post(
            f"/api/datasources/{projected_dataset_id}/understanding/candidates/{candidate['id']}/review",
            json={"action": "accept"},
        )
        assert reviewed.status_code == 200

    model_slug = f"external-revenue-{uuid4().hex[:8]}"
    drafted = await test_client.post(
        f"/api/datasources/{projected_dataset_id}/understanding/semantic-model-draft",
        json={
            "model_id": model_slug,
            "name": "External Revenue Semantic",
            "domain": "Sales / Orders",
            "owner": "Revenue Analytics",
            "candidate_ids": [candidate["id"] for candidate in selected],
        },
    )
    assert drafted.status_code == 200

    validated = await test_client.post(f"/api/data-models/{model_slug}/validate")
    assert validated.status_code == 200
    assert validated.json()["data"]["readinessDetail"]["blockers"] == []
    published = await test_client.post(f"/api/data-models/{model_slug}/publish")
    assert published.status_code == 200

    model = await test_session.scalar(
        select(SemanticModel).where(
            SemanticModel.tenant_id == tenant.id,
            SemanticModel.slug == model_slug,
        )
    )
    assert model is not None

    from server.services.file_operations import DataFrameFileService

    original_execute = DataFrameFileService.execute_duckdb_query_on_dataset
    calls: list[dict[str, str]] = []

    async def tracked_execute_duckdb_query_on_dataset(**kwargs):
        calls.append({"dataset_id": kwargs["dataset_id"], "query": kwargs["query"]})
        return await original_execute(**kwargs)

    monkeypatch.setattr(
        "server.services.semantic_model_service.DataFrameFileService.execute_duckdb_query_on_dataset",
        tracked_execute_duckdb_query_on_dataset,
    )
    monkeypatch.setattr(
        "server.services.semantic_model_service.AsyncRawQueryService.execute_raw_query",
        pytest.fail,
    )

    described = await test_client.get(
        f"/api/external/assets/semantic_model/{model.id}",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert described.status_code == 200
    asset_payload = described.json()["data"]
    assert asset_payload["publish_state"] == "published"
    assert asset_payload["capability_kind"] == "semantic_skill"
    package = asset_payload["capability_package"]
    assert package["package_type"] == "semantic_skill"
    assert package["runtime"]["query_url"] == f"/api/external/assets/semantic_model/{model.id}/query"
    assert package["mdl"]["schema"] == "byaan.mdl.v1"
    assert package["mdl"]["metrics"][0]["id"] == "revenue_revenue"
    assert package["governance"]["raw_sql_fallback"] is False
    assert package["governance"]["allowed_metrics"]
    assert "connection_obj_encrypted" not in str(package)
    assert "byaan_test_external_key" not in str(package)
    assert asset_payload["capabilities"]["metrics"]
    assert asset_payload["capabilities"]["dimensions"]
    assert asset_payload["sample_evidence"]

    response = await test_client.post(
        f"/api/external/assets/semantic_model/{model.id}/query",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"metric": "revenue_revenue", "dimension": "revenue_region", "limit": 10},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "completed"
    assert payload["policyDecision"] == "allowed"
    assert payload["metric"]["id"] == "revenue_revenue"
    assert payload["metric"]["definition"] == payload["metricDefinition"]
    assert payload["metric"]["version"] == payload["modelVersion"]
    assert payload["result"]
    assert sorted(payload["result"], key=lambda item: item["revenue_region"]) == [
        {"revenue_region": "East", "revenue_revenue": 120},
        {"revenue_region": "West", "revenue_revenue": 80},
    ]
    assert payload["sql"]
    assert payload["metricDefinition"]
    assert any(item["kind"] == "sql" for item in payload["evidence"])
    assert any(item["kind"] == "metric_definition" for item in payload["evidence"])
    assert any(item["kind"] == "permission_policy" for item in payload["evidence"])
    assert calls and calls[0]["dataset_id"] == projected_dataset_id
