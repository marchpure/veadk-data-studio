from __future__ import annotations

import hashlib
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.mcp_api_key import MCPAPIKey
from server.models.tenant import Tenant
from server.models.user import User
from server.services.dashboard import DashboardService
from server.tests.asset_helpers import current_tenant, seed_dashboard_asset, seed_semantic_model

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
