from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select

from server.models.semantic_models import (
    SemanticModel,
    SemanticModelAuditEvent,
    SemanticModelGenerationJob,
    SemanticModelVersion,
)
from server.models.tenant import Tenant
from server.models.tenant_member import TenantMember, TenantRole
from server.models.user import User


pytestmark = pytest.mark.asyncio


async def test_semantic_model_generation_metric_publish_and_mcp_contract(test_client, test_session):
    response = await test_client.get("/api/data-models")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total"] >= 1
    assert payload["items"][0]["id"] == "sales-growth"

    response = await test_client.get("/api/datasources/oracle-sales/profile")
    assert response.status_code == 200
    profile = response.json()["data"]
    assert profile["name"] == "Oracle SALES"
    assert len(profile["tables"]) == 8

    response = await test_client.post(
        "/api/data-models/generation-jobs",
        json={
            "datasource_id": "oracle-sales",
            "domain": "Sales / Orders",
            "selected_tables": ["ORDERS", "ORDER_ITEMS", "CUSTOMERS"],
            "business_questions": "How is paid revenue changing by region?",
        },
    )
    assert response.status_code == 200
    job = response.json()["data"]
    assert job["status"] == "running"
    assert job["progress"] > 0

    for _ in range(8):
        response = await test_client.post(f"/api/data-models/generation-jobs/{job['id']}/advance")
        assert response.status_code == 200
        job = response.json()["data"]
    assert job["status"] == "completed"
    assert job["result_model_id"] == "sales-growth"

    response = await test_client.post("/api/data-models/sales-growth/relationships/rel-orders-refunds-risk/fix-fanout")
    assert response.status_code == 200
    model = response.json()["data"]
    relationship = next(item for item in model["relationships"] if item["id"] == "rel-orders-refunds-risk")
    assert relationship["validationStatus"] == "valid"
    assert model["readinessDetail"]["blockers"] == []

    response = await test_client.patch(
        "/api/data-models/sales-growth/metrics/paid_revenue",
        json={"formula": "SUM(orders.net_amount) * 1.01", "certification": "certified"},
    )
    assert response.status_code == 200
    model = response.json()["data"]
    metric = next(item for item in model["metrics"] if item["id"] == "paid_revenue")
    assert metric["certification"] == "certified"
    assert "Team Version semantic service" in metric["preview"]["validation"]

    response = await test_client.post("/api/data-models/sales-growth/explore/artifacts", json={"kind": "query"})
    assert response.status_code == 200
    assert response.json()["data"]["consumers"]["savedQueries"] == 9

    response = await test_client.post("/api/data-models/sales-growth/validate")
    assert response.status_code == 200

    response = await test_client.post("/api/data-models/sales-growth/review/mark")
    assert response.status_code == 200
    response = await test_client.post("/api/data-models/sales-growth/publish")
    assert response.status_code == 200
    model = response.json()["data"]
    assert model["status"] == "Published"
    assert model["publishedVersion"] == "v3"
    assert model["mcp"]["exposedVersion"] == "v3"

    response = await test_client.post("/api/data-models/sales-growth/mcp/query_metric", json={"metric": "paid_revenue"})
    assert response.status_code == 200
    result = response.json()["data"]["mcp"]["lastResult"]
    assert result["resolvedMetric"] == "Paid Revenue"
    assert result["modelVersion"] == "v3"
    assert "policy" not in result["result"].lower()

    versions = (await test_session.execute(select(SemanticModelVersion))).scalars().all()
    jobs = (await test_session.execute(select(SemanticModelGenerationJob))).scalars().all()
    audits = (await test_session.execute(select(SemanticModelAuditEvent))).scalars().all()
    assert len(versions) == 1
    assert len(jobs) == 1
    assert len(audits) >= 6


async def test_semantic_model_seed_is_idempotent_under_parallel_home_load(test_client, test_session):
    models_response, profiles_response = await asyncio.gather(
        test_client.get("/api/data-models"),
        test_client.get("/api/data-models/profiles"),
    )

    assert models_response.status_code == 200
    assert profiles_response.status_code == 200
    rows = (
        await test_session.execute(select(SemanticModel).where(SemanticModel.slug == "sales-growth"))
    ).scalars().all()
    assert len(rows) == 1


async def test_semantic_model_tenant_isolation(test_client, test_session):
    response = await test_client.get("/api/data-models")
    assert response.status_code == 200
    first_tenant_model_count = len(response.json()["data"]["items"])

    other_user = User(
        id=uuid4(),
        email="other@test.com",
        hashed_password="fakehash",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    test_session.add(other_user)
    await test_session.flush()
    other_tenant = Tenant(
        id=uuid4(),
        name="Other Tenant",
        slug="other-tenant",
        owner_id=other_user.id,
        is_personal=True,
    )
    test_session.add(other_tenant)
    await test_session.flush()
    test_session.add(TenantMember(user_id=other_user.id, tenant_id=other_tenant.id, role=TenantRole.OWNER.value))
    await test_session.commit()

    response = await test_client.get("/api/data-models", headers={"x-tenant-id": str(other_tenant.id)})
    assert response.status_code == 200
    other_items = response.json()["data"]["items"]
    assert len(other_items) == first_tenant_model_count
    assert other_items[0]["id"] == "sales-growth"

    rows = (await test_session.execute(select(SemanticModel))).scalars().all()
    assert len({row.tenant_id for row in rows}) == 2


async def test_viewer_cannot_publish_semantic_model(test_client, test_session, monkeypatch):
    monkeypatch.setenv("BYAAN_LOCAL_AUTH_IMPERSONATION_ENABLED", "true")
    viewer = User(
        id=uuid4(),
        email="viewer@test.com",
        hashed_password="fakehash",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    test_session.add(viewer)
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    test_session.add(TenantMember(user_id=viewer.id, tenant_id=tenant.id, role=TenantRole.VIEWER.value))
    await test_session.commit()

    response = await test_client.post(
        "/api/data-models/sales-growth/publish",
        headers={"x-tenant-id": str(tenant.id), "x-local-user-id": str(viewer.id)},
    )
    assert response.status_code == 403
