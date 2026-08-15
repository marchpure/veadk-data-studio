from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from server.models.connections import Connection
from server.models.datasets import Dataset
from server.models.knowledge_resources import EvidenceFragment
from server.models.semantic_models import SemanticModel
from server.models.source_resources import SourceResource
from server.models.source_snapshots import SourceSnapshot
from server.models.source_understanding import SourceSkillCandidate, SourceUnderstandingRun
from server.models.tenant import Tenant
from server.models.tenant_member import TenantMember, TenantRole
from server.models.user import User

pytestmark = pytest.mark.asyncio


SALES_SCHEMA = {
    "datasource_type": "oracle",
    "datasource_name": "Oracle SALES",
    "selected_schema": "SALES",
    "schema": {
        "ORDERS": {
            "schema": "SALES",
            "description": "Order header at submitted order grain.",
            "row_count": 1200,
            "columns": [
                {"name": "ORDER_ID", "type": "NUMBER(18)", "nullable": False},
                {"name": "CUSTOMER_ID", "type": "NUMBER(18)", "nullable": False},
                {"name": "ORDER_STATUS", "type": "VARCHAR2(32)", "nullable": False},
                {"name": "PAID_AT", "type": "TIMESTAMP", "nullable": True},
                {"name": "NET_AMOUNT", "type": "NUMBER(18,2)", "nullable": False},
            ],
            "primary_key": ["ORDER_ID"],
            "indexes": [{"name": "IDX_ORDERS_CUSTOMER", "columns": ["CUSTOMER_ID"], "unique": False}],
            "foreign_keys": [
                {
                    "constraint_name": "FK_ORDERS_CUSTOMERS",
                    "column": ["CUSTOMER_ID"],
                    "ref_table": "CUSTOMERS",
                    "ref_column": ["CUSTOMER_ID"],
                    "orphan_rate": 0.3,
                    "unique_rate": 100,
                }
            ],
            "sample_rows": [
                {
                    "ORDER_ID": 1001,
                    "CUSTOMER_ID": 501,
                    "ORDER_STATUS": "PAID",
                    "PAID_AT": "2026-08-01T10:30:00",
                    "NET_AMOUNT": 120.5,
                }
            ],
        },
        "CUSTOMERS": {
            "schema": "SALES",
            "description": "Customer dimension.",
            "row_count": 500,
            "columns": [
                {"name": "CUSTOMER_ID", "type": "NUMBER(18)", "nullable": False},
                {"name": "CUSTOMER_TIER", "type": "VARCHAR2(24)", "nullable": True},
                {"name": "EMAIL", "type": "VARCHAR2(255)", "nullable": True},
            ],
            "primary_key": ["CUSTOMER_ID"],
            "sample_rows": [{"CUSTOMER_ID": 501, "CUSTOMER_TIER": "Gold", "EMAIL": "masked@example.com"}],
        },
    },
}


SQLITE_SALES_SCHEMA = {
    "datasource_type": "sqlite",
    "datasource_name": "Sales Demo SQLite",
    "database_name": "sales_demo.sqlite",
    "selected_schema": "main",
    "schema": {
        "orders": {
            "schema": "main",
            "description": "Order header at submitted order grain.",
            "row_count": 12,
            "columns": [
                {"name": "order_id", "type": "INTEGER", "nullable": False},
                {"name": "customer_id", "type": "INTEGER", "nullable": False},
                {"name": "order_status", "type": "TEXT", "nullable": False},
                {"name": "paid_at", "type": "TEXT", "nullable": True},
                {"name": "net_amount", "type": "REAL", "nullable": False},
            ],
            "primary_key": ["order_id"],
            "indexes": [{"name": "idx_orders_customer", "columns": ["customer_id"], "unique": False}],
            "foreign_keys": [
                {
                    "constraint_name": "fk_orders_customers",
                    "column": ["customer_id"],
                    "ref_table": "customers",
                    "ref_column": ["customer_id"],
                    "orphan_rate": 0,
                    "unique_rate": 100,
                }
            ],
            "sample_rows": [
                {
                    "order_id": 1001,
                    "customer_id": 501,
                    "order_status": "PAID",
                    "paid_at": "2026-08-01T10:30:00",
                    "net_amount": 120.5,
                }
            ],
        },
        "customers": {
            "schema": "main",
            "description": "Customer dimension.",
            "row_count": 5,
            "columns": [
                {"name": "customer_id", "type": "INTEGER", "nullable": False},
                {"name": "customer_tier", "type": "TEXT", "nullable": True},
                {"name": "email", "type": "TEXT", "nullable": True},
            ],
            "primary_key": ["customer_id"],
            "sample_rows": [{"customer_id": 501, "customer_tier": "Gold", "email": "masked@example.com"}],
        },
    },
}


async def _create_connection_dataset(
    test_session,
    tenant_id,
    user_id,
    schema=SALES_SCHEMA,
    connection_type: str = "oracle",
    name: str = "Oracle SALES",
    connection_obj: dict | None = None,
):
    connection = Connection(
        tenant_id=tenant_id,
        created_by=user_id,
        type=connection_type,
        name=name,
        connection_obj_encrypted=json.dumps(connection_obj or {"host": "oracle.local", "user": "sales"}),
        schema_cache=json.dumps(schema),
        is_public=True,
    )
    test_session.add(connection)
    await test_session.flush()
    dataset = Dataset(
        tenant_id=tenant_id,
        created_by=user_id,
        type="connection",
        name=name,
        connection_id=connection.id,
        is_public=True,
    )
    test_session.add(dataset)
    await test_session.commit()
    await test_session.refresh(dataset)
    return connection, dataset


async def test_database_source_understanding_generates_profile_relationship_evidence_and_review(
    test_client,
    test_session,
):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    _, dataset = await _create_connection_dataset(test_session, tenant.id, tenant.owner_id)

    response = await test_client.post(f"/api/datasources/{dataset.id}/understanding/analyze", json={})

    assert response.status_code == 200
    understanding = response.json()["data"]
    assert understanding["datasource_type"] == "oracle"
    assert understanding["latest_run"]["status"] == "completed"
    assert understanding["overview"]["resource_count"] == 4
    assert understanding["profile"]["table_count"] == 2
    assert understanding["profile"]["relationship_count"] == 1
    assert {candidate["candidate_type"] for candidate in understanding["candidates"]} >= {
        "schema_map",
        "data_profile",
        "relationship",
        "data_truth",
        "quality_gotcha",
    }

    relationship = next(item for item in understanding["candidates"] if item["candidate_type"] == "relationship")
    assert relationship["source_id"] == str(dataset.id)
    assert relationship["generator"] == "database-source-analyzer-v1:metadata-profile"
    assert relationship["version"] == 1
    assert relationship["validation_status"] == "passed"
    assert relationship["structured_payload_json"]["join_fields"] == [
        {"from": "ORDERS.CUSTOMER_ID", "to": "CUSTOMERS.CUSTOMER_ID"}
    ]
    assert relationship["structured_payload_json"]["source_id"] == str(dataset.id)
    assert relationship["structured_payload_json"]["validation_sql"]["status"] == "not_executed"
    assert "LEFT JOIN CUSTOMERS" in relationship["structured_payload_json"]["validation_sql"]["sql"]
    assert relationship["validation_json"]["validation_sql"]["method"] == "left_join_orphan_check"
    assert relationship["validation_json"]["sample_status"] == "passed"
    assert relationship["validation_json"]["sampled_matches"] == 1
    assert relationship["evidence"]
    assert relationship["evidence"][0]["locator_json"]["kind"].startswith("database_")
    assert any(item["locator_json"].get("constraint") == "index" for item in relationship["evidence"])

    profile = next(
        item
        for item in understanding["candidates"]
        if item["candidate_type"] == "data_profile" and item["structured_payload_json"]["table"] == "ORDERS"
    )
    net_amount = next(field for field in profile["structured_payload_json"]["columns"] if field["source_field"] == "NET_AMOUNT")
    assert net_amount["profile"]["sample_size"] == 1
    assert net_amount["profile"]["distinct_count"] == 1
    assert net_amount["profile"]["min"] == 120.5

    metric = next(item for item in understanding["candidates"] if item["candidate_type"] == "data_truth")
    review_response = await test_client.post(
        f"/api/datasources/{dataset.id}/understanding/candidates/{metric['id']}/review",
        json={
            "action": "edit",
            "statement": "Paid revenue candidate from ORDERS.NET_AMOUNT after finance review.",
            "structured_payload": {"business_name": "Paid Revenue"},
            "note": "Reviewed with finance owner.",
        },
    )

    assert review_response.status_code == 200
    reviewed_metric = next(
        item for item in review_response.json()["data"]["candidates"] if item["id"] == metric["id"]
    )
    assert reviewed_metric["review_status"] == "verified"
    assert reviewed_metric["structured_payload_json"]["business_name"] == "Paid Revenue"
    assert reviewed_metric["review_note"] == "Reviewed with finance owner."

    runs = (await test_session.execute(select(SourceUnderstandingRun))).scalars().all()
    resources = (await test_session.execute(select(SourceResource))).scalars().all()
    snapshots = (await test_session.execute(select(SourceSnapshot))).scalars().all()
    evidence = (await test_session.execute(select(EvidenceFragment))).scalars().all()
    candidates = (await test_session.execute(select(SourceSkillCandidate))).scalars().all()
    assert len(runs) == 1
    assert len(resources) == 4
    assert len(snapshots) == 4
    assert len(evidence) >= 8
    assert any(item.review_status == "verified" for item in candidates)


async def test_verified_source_candidates_create_semantic_model_draft_with_lineage(test_client, test_session):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    _, dataset = await _create_connection_dataset(test_session, tenant.id, tenant.owner_id)
    analyze_response = await test_client.post(f"/api/datasources/{dataset.id}/understanding/analyze", json={})
    assert analyze_response.status_code == 200
    candidates = analyze_response.json()["data"]["candidates"]
    selected = [
        item
        for item in candidates
        if item["candidate_type"] in {"schema_map", "relationship", "data_truth"}
    ][:4]
    assert selected

    for candidate in selected:
        review_response = await test_client.post(
            f"/api/datasources/{dataset.id}/understanding/candidates/{candidate['id']}/review",
            json={"action": "accept"},
        )
        assert review_response.status_code == 200

    apply_response = await test_client.post(
        f"/api/datasources/{dataset.id}/understanding/semantic-model-draft",
        json={
            "model_id": "sales-source-draft",
            "name": "Sales Source Draft",
            "domain": "Sales / Orders",
            "owner": "Revenue Analytics",
            "candidate_ids": [item["id"] for item in selected],
        },
    )

    assert apply_response.status_code == 200
    payload = apply_response.json()["data"]
    model = payload["model"]
    assert model["id"] == "sales-source-draft"
    assert model["status"] == "Draft"
    assert model["datasourceId"] == str(dataset.id)
    assert payload["applied_candidate_ids"]
    assert payload["lineage"]["candidates"][0]["source_snapshot_id"]
    assert any(entity["table"] == "ORDERS" for entity in model["entities"])
    assert any(metric["businessName"] for metric in model["metrics"])
    paid_revenue = next(metric for metric in model["metrics"] if metric["id"] == "orders_net_amount")
    assert set(paid_revenue["dimensions"]) >= {"orders_order_status", "orders_paid_at", "customers_customer_tier"}

    row = await test_session.scalar(select(SemanticModel).where(SemanticModel.slug == "sales-source-draft"))
    assert row is not None
    review = json.loads(row.review_json)
    assert review["sourceUnderstandingLineage"]


async def test_sqlite_source_understanding_creates_semantic_model_draft(test_client, test_session):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    _, dataset = await _create_connection_dataset(
        test_session,
        tenant.id,
        tenant.owner_id,
        schema=SQLITE_SALES_SCHEMA,
        connection_type="sqlite",
        name="Sales Demo SQLite",
        connection_obj={"database_path": "/tmp/sales_demo.sqlite"},
    )

    analyze_response = await test_client.post(f"/api/datasources/{dataset.id}/understanding/analyze", json={})

    assert analyze_response.status_code == 200
    understanding = analyze_response.json()["data"]
    assert understanding["datasource_type"] == "sqlite"
    assert understanding["latest_run"]["status"] == "completed"
    assert understanding["profile"]["table_count"] == 2
    assert understanding["profile"]["relationship_count"] == 1

    candidates = understanding["candidates"]
    selected = [
        item
        for item in candidates
        if item["candidate_type"] in {"schema_map", "relationship", "data_truth"}
    ]
    assert {item["candidate_type"] for item in selected} >= {"schema_map", "relationship", "data_truth"}

    for candidate in selected:
        review_response = await test_client.post(
            f"/api/datasources/{dataset.id}/understanding/candidates/{candidate['id']}/review",
            json={"action": "accept"},
        )
        assert review_response.status_code == 200

    apply_response = await test_client.post(
        f"/api/datasources/{dataset.id}/understanding/semantic-model-draft",
        json={
            "model_id": "sqlite-sales-source-draft",
            "name": "SQLite Sales Source Draft",
            "domain": "Sales / Orders",
            "owner": "Revenue Analytics",
            "candidate_ids": [item["id"] for item in selected],
        },
    )

    assert apply_response.status_code == 200
    payload = apply_response.json()["data"]
    model = payload["model"]
    assert model["datasourceKind"] == "sqlite"
    assert model["datasourceId"] == str(dataset.id)
    assert any(entity["table"] == "orders" for entity in model["entities"])
    assert any(metric["id"] == "orders_net_amount" for metric in model["metrics"])
    assert any(relationship["fromEntity"] == "orders" for relationship in model["relationships"])


async def test_source_understanding_detects_drift_and_marks_previous_verified_candidates_stale(
    test_client,
    test_session,
):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    connection, dataset = await _create_connection_dataset(test_session, tenant.id, tenant.owner_id)

    first = await test_client.post(f"/api/datasources/{dataset.id}/understanding/analyze", json={})
    assert first.status_code == 200
    schema_candidate = next(item for item in first.json()["data"]["candidates"] if item["candidate_type"] == "schema_map")
    accepted = await test_client.post(
        f"/api/datasources/{dataset.id}/understanding/candidates/{schema_candidate['id']}/review",
        json={"action": "accept"},
    )
    assert accepted.status_code == 200

    refreshed_connection = await test_session.get(Connection, connection.id)
    assert refreshed_connection is not None
    changed = json.loads(refreshed_connection.schema_cache)
    changed["schema"]["ORDERS"]["columns"].append({"name": "CHANNEL_ID", "type": "NUMBER(10)", "nullable": True})
    refreshed_connection.schema_cache = json.dumps(changed)
    await test_session.commit()

    second = await test_client.post(f"/api/datasources/{dataset.id}/understanding/analyze", json={})
    assert second.status_code == 200
    drift = second.json()["data"]["sync_drift"]
    assert drift["status"] == "drift_detected"
    assert drift["events"]

    stale = await test_session.get(SourceSkillCandidate, schema_candidate["id"])
    assert stale is not None
    assert stale.review_status == "stale"


async def test_source_understanding_enforces_tenant_and_own_resource_rbac(test_client, test_session, monkeypatch):
    monkeypatch.setenv("BYAAN_LOCAL_AUTH_IMPERSONATION_ENABLED", "true")
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    _, dataset = await _create_connection_dataset(test_session, tenant.id, tenant.owner_id)

    viewer = User(
        id=uuid4(),
        email="viewer-source@test.com",
        hashed_password="fakehash",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    member = User(
        id=uuid4(),
        email="member-source@test.com",
        hashed_password="fakehash",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    test_session.add_all([viewer, member])
    await test_session.flush()
    test_session.add_all(
        [
            TenantMember(user_id=viewer.id, tenant_id=tenant.id, role=TenantRole.VIEWER.value),
            TenantMember(user_id=member.id, tenant_id=tenant.id, role=TenantRole.MEMBER.value),
        ]
    )
    await test_session.commit()

    viewer_read = await test_client.get(
        f"/api/datasources/{dataset.id}/understanding",
        headers={"x-local-user-id": str(viewer.id), "x-tenant-id": str(tenant.id)},
    )
    assert viewer_read.status_code == 403

    member_read = await test_client.get(
        f"/api/datasources/{dataset.id}/understanding",
        headers={"x-local-user-id": str(member.id), "x-tenant-id": str(tenant.id)},
    )
    assert member_read.status_code == 200

    viewer_analyze = await test_client.post(
        f"/api/datasources/{dataset.id}/understanding/analyze",
        json={},
        headers={"x-local-user-id": str(viewer.id), "x-tenant-id": str(tenant.id)},
    )
    assert viewer_analyze.status_code == 403

    member_analyze = await test_client.post(
        f"/api/datasources/{dataset.id}/understanding/analyze",
        json={},
        headers={"x-local-user-id": str(member.id), "x-tenant-id": str(tenant.id)},
    )
    assert member_analyze.status_code == 403

    other_user = User(
        id=uuid4(),
        email="other-tenant-source@test.com",
        hashed_password="fakehash",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    test_session.add(other_user)
    await test_session.flush()
    other_tenant = Tenant(
        id=uuid4(),
        name="Other Source Tenant",
        slug="other-source-tenant",
        owner_id=other_user.id,
        is_personal=True,
    )
    test_session.add(other_tenant)
    await test_session.flush()
    test_session.add(TenantMember(user_id=other_user.id, tenant_id=other_tenant.id, role=TenantRole.OWNER.value))
    await test_session.commit()

    cross_tenant = await test_client.get(
        f"/api/datasources/{dataset.id}/understanding",
        headers={"x-tenant-id": str(other_tenant.id)},
    )
    assert cross_tenant.status_code == 404
