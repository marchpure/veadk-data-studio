from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from server.models.connections import Connection
from server.models.datasets import Dataset
from server.models.semantic_models import SemanticModel, SemanticModelVersion
from server.models.tenant import Tenant

pytestmark = pytest.mark.asyncio


async def _create_connection_dataset(test_session, tenant_id, user_id):
    connection = Connection(
        tenant_id=tenant_id,
        created_by=user_id,
        type="sqlite",
        name="SQLite Sales",
        connection_obj_encrypted=json.dumps({"database_path": ":memory:"}),
        schema_cache=json.dumps(
            {
                "datasource_type": "sqlite",
                "datasource_name": "SQLite Sales",
                "schema": {
                    "orders": {
                        "columns": [
                            {"name": "order_id", "type": "INTEGER", "nullable": False},
                            {"name": "paid_at", "type": "TEXT", "nullable": True},
                            {"name": "net_amount", "type": "REAL", "nullable": False},
                            {"name": "order_status", "type": "TEXT", "nullable": False},
                        ],
                        "primary_key": ["order_id"],
                    }
                },
            }
        ),
        is_public=True,
    )
    test_session.add(connection)
    await test_session.flush()
    dataset = Dataset(
        tenant_id=tenant_id,
        created_by=user_id,
        type="connection",
        name="SQLite Sales",
        connection_id=connection.id,
        is_public=True,
    )
    test_session.add(dataset)
    await test_session.commit()
    await test_session.refresh(dataset)
    return connection, dataset


async def _create_semantic_model(test_session, tenant: Tenant, datasource_id: str) -> SemanticModel:
    model = SemanticModel(
        id=uuid4(),
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        slug="sales-semantic",
        name="Sales Semantic",
        domain="Sales",
        owner="Revenue Analytics",
        datasource_id=datasource_id,
        datasource_name="SQLite Sales",
        datasource_kind="sqlite",
        status="Draft",
        draft_revision="draft-1",
        published_version="v0",
        readiness=0,
        readiness_level="blocked",
        consumers_json=json.dumps({"agents": 0, "mcp": 1, "skills": 0, "dashboards": 0, "savedQueries": 0}),
        review_json=json.dumps({"sourceUnderstandingLineage": {"candidates": []}}),
        mcp_json=json.dumps({"rawSqlFallback": False}),
    )
    test_session.add(model)
    await test_session.flush()

    from server.models.semantic_models import (
        SemanticModelDimension,
        SemanticModelEntity,
        SemanticModelField,
        SemanticModelMetric,
    )

    entity = SemanticModelEntity(
        model_id=model.id,
        slug="orders",
        name="orders",
        business_name="Orders",
        table_name="orders",
        description="Order header grain.",
        primary_key="order_id",
        entity_type="fact",
        validation_status="valid",
        sort_order=0,
    )
    test_session.add(entity)
    await test_session.flush()
    test_session.add_all(
        [
            SemanticModelField(
                entity_id=entity.id,
                name="net_amount",
                source_field="net_amount",
                data_type="REAL",
                role="amount",
                nullable=False,
                sort_order=0,
            ),
            SemanticModelField(
                entity_id=entity.id,
                name="order_status",
                source_field="order_status",
                data_type="TEXT",
                role="status",
                nullable=False,
                sort_order=1,
            ),
            SemanticModelField(
                entity_id=entity.id,
                name="paid_at",
                source_field="paid_at",
                data_type="TEXT",
                role="time",
                nullable=True,
                sort_order=2,
            ),
        ]
    )
    test_session.add(
        SemanticModelMetric(
            model_id=model.id,
            slug="paid_revenue",
            name="paid_revenue",
            business_name="Paid Revenue",
            definition="Revenue from paid orders.",
            kind="measure",
            formula="SUM(orders.net_amount)",
            filter_expr="orders.order_status = 'PAID'",
            time_field="orders.paid_at",
            default_grain="month",
            dimensions_json=json.dumps(["order_status"]),
            unit="USD",
            owner="Revenue Analytics",
            certification="reviewed",
            lineage_json=json.dumps(["orders.net_amount", "orders.order_status"]),
            validation_status="valid",
            sort_order=0,
        )
    )
    test_session.add(
        SemanticModelDimension(
            model_id=model.id,
            slug="order_status",
            name="Order Status",
            entity_slug="orders",
            field="order_status",
            description="Order payment status.",
            sort_order=0,
        )
    )
    await test_session.commit()
    return model


async def test_data_models_validate_publish_and_query_metric_use_persisted_model(
    test_client,
    test_session,
    monkeypatch,
):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    _, dataset = await _create_connection_dataset(test_session, tenant.id, tenant.owner_id)
    await _create_semantic_model(test_session, tenant, str(dataset.id))

    list_response = await test_client.get("/api/data-models")
    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["id"] == "sales-semantic"

    validate_response = await test_client.post("/api/data-models/sales-semantic/validate")
    assert validate_response.status_code == 200
    validated = validate_response.json()["data"]
    assert validated["readiness"] >= 80
    assert validated["readinessDetail"]["blockers"] == []

    publish_response = await test_client.post("/api/data-models/sales-semantic/publish")
    assert publish_response.status_code == 200
    published = publish_response.json()["data"]
    assert published["status"] == "Published"
    assert published["publishedVersion"] == "v1"

    async def fake_execute_raw_query(**kwargs):
        assert kwargs["db_type"] == "sqlite"
        assert "SUM(orders.net_amount)" in kwargs["query"]
        assert "GROUP BY" in kwargs["query"]
        assert "order_status" in kwargs["query"]
        return {
            "success": True,
            "result": [{"order_status": "PAID", "paid_revenue": 120.5}],
            "returned_count": 1,
            "total_count": 1,
            "limited": False,
        }

    monkeypatch.setattr(
        "server.services.semantic_model_service.AsyncRawQueryService.execute_raw_query",
        fake_execute_raw_query,
    )
    query_response = await test_client.post(
        "/api/data-models/sales-semantic/mcp/query_metric",
        json={"metric": "paid_revenue", "dimension": "order_status", "grain": "month", "time_range": "90d"},
    )
    assert query_response.status_code == 200
    query_result = query_response.json()["data"]
    assert query_result["resolvedMetric"] == "Paid Revenue"
    assert query_result["modelVersion"] == "v1"
    assert query_result["policyDecision"] == "allowed"
    assert query_result["result"][0]["paid_revenue"] == 120.5
    assert "sql" in query_result


async def test_query_metric_requires_published_model(test_client, test_session):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    _, dataset = await _create_connection_dataset(test_session, tenant.id, tenant.owner_id)
    await _create_semantic_model(test_session, tenant, str(dataset.id))

    response = await test_client.post(
        "/api/data-models/sales-semantic/mcp/query_metric",
        json={"metric": "paid_revenue"},
    )

    assert response.status_code == 409
    assert "published" in response.json()["message"].lower()


async def test_data_model_patch_persists_with_revision_conflict(test_client, test_session):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    _, dataset = await _create_connection_dataset(test_session, tenant.id, tenant.owner_id)
    await _create_semantic_model(test_session, tenant, str(dataset.id))

    get_response = await test_client.get("/api/data-models/sales-semantic")
    assert get_response.status_code == 200
    current = get_response.json()["data"]
    assert current["revision"] == 1

    patch_response = await test_client.patch(
        "/api/data-models/sales-semantic",
        json={
            "expected_revision": current["revision"],
            "metrics": [
                {
                    "id": "paid_revenue",
                    "businessName": "Recognized Revenue",
                    "definition": "Recognized paid order revenue.",
                    "kind": "measure",
                    "formula": "SUM(orders.net_amount)",
                    "filter": "orders.order_status = 'PAID'",
                    "timeField": "orders.paid_at",
                    "defaultGrain": "month",
                    "dimensions": ["order_status"],
                    "unit": "USD",
                    "owner": "Finance Analytics",
                    "certification": "certified",
                    "lineage": ["orders.net_amount"],
                }
            ],
        },
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()["data"]
    assert updated["revision"] == 2
    assert updated["status"] == "Draft"
    assert updated["metrics"][0]["businessName"] == "Recognized Revenue"
    assert updated["metrics"][0]["certification"] == "certified"

    conflict_response = await test_client.patch(
        "/api/data-models/sales-semantic",
        json={"expected_revision": current["revision"], "name": "Stale Write"},
    )
    assert conflict_response.status_code == 409
    assert "revision" in conflict_response.json()["message"].lower()

    reloaded = await test_client.get("/api/data-models/sales-semantic")
    assert reloaded.json()["data"]["metrics"][0]["businessName"] == "Recognized Revenue"


async def test_calculated_fields_patch_persists_and_publishes_snapshot(test_client, test_session):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    _, dataset = await _create_connection_dataset(test_session, tenant.id, tenant.owner_id)
    await _create_semantic_model(test_session, tenant, str(dataset.id))

    patch_response = await test_client.patch(
        "/api/data-models/sales-semantic",
        json={
            "expected_revision": 1,
            "calculatedFields": [
                {
                    "id": "paid_flag",
                    "name": "Paid Flag",
                    "entityId": "orders",
                    "expression": "orders.order_status = 'PAID'",
                    "description": "True when the order is paid.",
                }
            ],
        },
    )

    assert patch_response.status_code == 200
    patched = patch_response.json()["data"]
    assert patched["status"] == "Draft"
    assert patched["calculatedFields"][0]["id"] == "paid_flag"

    reloaded = await test_client.get("/api/data-models/sales-semantic")
    assert reloaded.status_code == 200
    current = reloaded.json()["data"]
    assert current["calculatedFields"][0]["expression"] == "orders.order_status = 'PAID'"

    validate_response = await test_client.post("/api/data-models/sales-semantic/validate")
    assert validate_response.status_code == 200
    publish_response = await test_client.post("/api/data-models/sales-semantic/publish")
    assert publish_response.status_code == 200

    version = (await test_session.execute(select(SemanticModelVersion))).scalars().one()
    snapshot = json.loads(version.snapshot_json)
    assert snapshot["calculatedFields"][0]["name"] == "Paid Flag"


async def test_metric_definition_patch_invalidates_stale_preview(test_client, test_session):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    _, dataset = await _create_connection_dataset(test_session, tenant.id, tenant.owner_id)
    model = await _create_semantic_model(test_session, tenant, str(dataset.id))
    model_id = model.id

    from server.models.semantic_models import SemanticModelMetric

    metric = await test_session.scalar(
        select(SemanticModelMetric).where(
            SemanticModelMetric.model_id == model.id,
            SemanticModelMetric.slug == "paid_revenue",
        )
    )
    assert metric is not None
    metric.preview_json = json.dumps(
        {
            "currentValue": "$123",
            "trend": "+1%",
            "breakdown": [{"label": "PAID", "value": "$123", "delta": "+1%"}],
            "explanation": "Old validated preview.",
            "sql": "SELECT SUM(orders.net_amount) FROM orders",
            "validation": "Old validation passed.",
        }
    )
    metric.compiled_sql = "SELECT SUM(orders.net_amount) FROM orders"
    await test_session.commit()

    patch_response = await test_client.patch(
        "/api/data-models/sales-semantic",
        json={
            "expected_revision": 1,
            "metrics": [
                {
                    "id": "paid_revenue",
                    "businessName": "Paid Revenue",
                    "definition": "Revenue from paid orders with changed expression.",
                    "kind": "measure",
                    "formula": "SUM(orders.net_amount * 1.01)",
                    "filter": "orders.order_status = 'PAID'",
                    "timeField": "orders.paid_at",
                    "defaultGrain": "month",
                    "dimensions": ["order_status"],
                    "unit": "USD",
                    "owner": "Revenue Analytics",
                    "certification": "reviewed",
                    "lineage": ["orders.net_amount", "orders.order_status"],
                    "preview": {
                        "currentValue": "$999",
                        "sql": "SELECT fake_success",
                        "validation": "Client-side fake success.",
                    },
                }
            ],
        },
    )

    assert patch_response.status_code == 200
    updated_metric = patch_response.json()["data"]["metrics"][0]
    assert updated_metric["preview"]["currentValue"] == "Run query"
    assert updated_metric["preview"]["sql"] == ""
    assert "Run Validate" in updated_metric["preview"]["validation"]

    test_session.expire_all()
    persisted_metric = await test_session.scalar(
        select(SemanticModelMetric).where(
            SemanticModelMetric.model_id == model_id,
            SemanticModelMetric.slug == "paid_revenue",
        )
    )
    assert persisted_metric is not None
    assert persisted_metric.compiled_sql == ""
    assert persisted_metric.validation_status == "warning"


async def test_workspace_state_patch_persists_without_demoting_ready_model(test_client, test_session):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    _, dataset = await _create_connection_dataset(test_session, tenant.id, tenant.owner_id)
    await _create_semantic_model(test_session, tenant, str(dataset.id))

    validate_response = await test_client.post("/api/data-models/sales-semantic/validate")
    assert validate_response.status_code == 200
    current = validate_response.json()["data"]
    assert current["status"] == "Ready for Review"

    patch_response = await test_client.patch(
        "/api/data-models/sales-semantic",
        json={
            "expected_revision": current["revision"],
            "explore": {
                "metricId": "paid_revenue",
                "dimensionId": "order_status",
                "grain": "month",
                "timeRange": "90d",
                "filter": "",
                "viewMode": "table",
                "savedQueryCount": 1,
                "dashboardAdds": 1,
                "skillDrafts": 1,
                "confirmedExamples": 1,
            },
            "consumers": {"agents": 0, "mcp": 1, "skills": 1, "dashboards": 1, "savedQueries": 1},
            "review": {"opened": True, "reviewed": True, "publishNotes": "Reviewed for v1."},
            "mcp": {"rawSqlFallback": True},
        },
    )

    assert patch_response.status_code == 200
    updated = patch_response.json()["data"]
    assert updated["revision"] == current["revision"] + 1
    assert updated["status"] == "Ready for Review"
    assert updated["explore"]["savedQueryCount"] == 1
    assert updated["consumers"]["skills"] == 1
    assert updated["review"]["publishNotes"] == "Reviewed for v1."
    assert updated["mcp"]["rawSqlFallback"] is False

    reloaded = await test_client.get("/api/data-models/sales-semantic")
    assert reloaded.status_code == 200
    reloaded_payload = reloaded.json()["data"]
    assert reloaded_payload["status"] == "Ready for Review"
    assert reloaded_payload["review"]["reviewed"] is True


async def test_publish_creates_immutable_version_and_query_uses_published_snapshot(
    test_client,
    test_session,
    monkeypatch,
):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    _, dataset = await _create_connection_dataset(test_session, tenant.id, tenant.owner_id)
    await _create_semantic_model(test_session, tenant, str(dataset.id))

    await test_client.patch(
        "/api/data-models/sales-semantic",
        json={
            "expected_revision": 1,
            "metrics": [
                {
                    "id": "paid_revenue",
                    "businessName": "Paid Revenue",
                    "definition": "Revenue from paid orders.",
                    "kind": "measure",
                    "formula": "SUM(orders.net_amount)",
                    "filter": "orders.order_status = 'PAID'",
                    "timeField": "orders.paid_at",
                    "defaultGrain": "month",
                    "dimensions": ["order_status"],
                    "unit": "USD",
                    "owner": "Revenue Analytics",
                    "certification": "certified",
                    "lineage": ["orders.net_amount", "orders.order_status"],
                }
            ],
        },
    )
    validate_response = await test_client.post("/api/data-models/sales-semantic/validate")
    assert validate_response.status_code == 200
    assert validate_response.json()["data"]["status"] == "Ready for Review"

    publish_response = await test_client.post("/api/data-models/sales-semantic/publish")
    assert publish_response.status_code == 200
    published = publish_response.json()["data"]
    assert published["status"] == "Published"
    assert published["publishedVersion"] == "v1"

    versions = (await test_session.execute(select(SemanticModelVersion))).scalars().all()
    assert len(versions) == 1
    assert versions[0].version_label == "v1"
    assert "source_snapshot" in versions[0].review_json

    patch_response = await test_client.patch(
        "/api/data-models/sales-semantic",
        json={
            "expected_revision": published["revision"],
            "metrics": [
                {
                    "id": "paid_revenue",
                    "businessName": "Draft Changed Revenue",
                    "definition": "Draft-only changed metric.",
                    "kind": "measure",
                    "formula": "SUM(orders.net_amount * 1000)",
                    "filter": "orders.order_status = 'PAID'",
                    "timeField": "orders.paid_at",
                    "defaultGrain": "month",
                    "dimensions": ["order_status"],
                    "unit": "USD",
                    "owner": "Revenue Analytics",
                    "certification": "certified",
                    "lineage": ["orders.net_amount"],
                }
            ],
        },
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["data"]["status"] == "Draft"

    async def fake_execute_raw_query(**kwargs):
        assert "SUM(orders.net_amount)" in kwargs["query"]
        assert "* 1000" not in kwargs["query"]
        return {
            "success": True,
            "result": [{"order_status": "PAID", "paid_revenue": 120.5}],
            "returned_count": 1,
            "total_count": 1,
            "limited": False,
        }

    monkeypatch.setattr(
        "server.services.semantic_model_service.AsyncRawQueryService.execute_raw_query",
        fake_execute_raw_query,
    )
    query_response = await test_client.post(
        "/api/data-models/sales-semantic/mcp/query_metric",
        json={"metric": "paid_revenue", "dimension": "order_status"},
    )
    assert query_response.status_code == 200
    assert query_response.json()["data"]["resolvedMetric"] == "Paid Revenue"
    assert query_response.json()["data"]["modelVersion"] == "v1"


async def test_publish_failure_does_not_create_version(test_client, test_session):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    _, dataset = await _create_connection_dataset(test_session, tenant.id, tenant.owner_id)
    await _create_semantic_model(test_session, tenant, str(dataset.id))

    patch_response = await test_client.patch(
        "/api/data-models/sales-semantic",
        json={
            "expected_revision": 1,
            "relationships": [
                {
                    "id": "bad_join",
                    "fromEntity": "orders",
                    "toEntity": "orders",
                    "label": "Bad fanout",
                    "joinFields": [],
                    "cardinality": "many-to-many",
                    "fkEvidence": "none",
                    "uniqueRate": 10,
                    "orphanRate": 90,
                    "fanoutRisk": "high",
                    "validationStatus": "blocked",
                    "status": "candidate",
                    "validationMessage": "Fanout risk",
                }
            ],
        },
    )
    assert patch_response.status_code == 200
    validate_response = await test_client.post("/api/data-models/sales-semantic/validate")
    assert validate_response.status_code == 200
    assert validate_response.json()["data"]["status"] == "Validation Failed"

    publish_response = await test_client.post("/api/data-models/sales-semantic/publish")
    assert publish_response.status_code == 409
    assert (await test_session.execute(select(SemanticModelVersion))).scalars().all() == []


async def test_published_metric_query_uses_physical_schema_and_relationship_join(
    test_client,
    test_session,
    monkeypatch,
):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    _, dataset = await _create_connection_dataset(test_session, tenant.id, tenant.owner_id)
    model = await _create_semantic_model(test_session, tenant, str(dataset.id))

    from server.models.semantic_models import (
        SemanticModelDimension,
        SemanticModelEntity,
        SemanticModelField,
        SemanticModelMetric,
        SemanticModelRelationship,
    )

    entities = (
        (await test_session.execute(select(SemanticModelEntity).where(SemanticModelEntity.model_id == model.id)))
        .scalars()
        .all()
    )
    orders = next(entity for entity in entities if entity.slug == "orders")
    orders.profile_json = json.dumps({"schema": "sales_reporting"})
    customers = SemanticModelEntity(
        model_id=model.id,
        slug="customers",
        name="customers",
        business_name="Customers",
        table_name="customers",
        description="Customer dimension.",
        primary_key="customer_id",
        entity_type="dimension",
        validation_status="valid",
        profile_json=json.dumps({"schema": "sales_reporting"}),
        sort_order=1,
    )
    test_session.add(customers)
    await test_session.flush()
    test_session.add(
        SemanticModelField(
            entity_id=customers.id,
            name="segment",
            source_field="segment",
            data_type="TEXT",
            role="attribute",
            nullable=False,
            sort_order=0,
        )
    )
    test_session.add(
        SemanticModelDimension(
            model_id=model.id,
            slug="customer_segment",
            name="Customer Segment",
            entity_slug="customers",
            field="segment",
            description="Customer segment.",
            sort_order=1,
        )
    )
    test_session.add(
        SemanticModelRelationship(
            model_id=model.id,
            slug="orders_customers",
            from_entity="orders",
            to_entity="customers",
            label="Orders -> Customers",
            join_fields_json=json.dumps([{"from": "orders.customer_id", "to": "customers.customer_id"}]),
            cardinality="many-to-one",
            fk_evidence="test",
            unique_rate=100,
            orphan_rate=0,
            fanout_risk="low",
            validation_status="valid",
            status="confirmed",
            validation_message="ok",
            evidence_json="[]",
            sort_order=0,
        )
    )
    metric = await test_session.scalar(
        select(SemanticModelMetric).where(
            SemanticModelMetric.model_id == model.id,
            SemanticModelMetric.slug == "paid_revenue",
        )
    )
    assert metric is not None
    metric.dimensions_json = json.dumps(["order_status", "customer_segment"])
    await test_session.commit()

    validate_response = await test_client.post("/api/data-models/sales-semantic/validate")
    assert validate_response.status_code == 200
    publish_response = await test_client.post("/api/data-models/sales-semantic/publish")
    assert publish_response.status_code == 200

    async def fake_execute_raw_query(**kwargs):
        query = kwargs["query"]
        assert 'FROM "sales_reporting"."orders" AS "orders"' in query
        assert 'LEFT JOIN "sales_reporting"."customers" AS "customers"' in query
        assert '"orders"."customer_id" = "customers"."customer_id"' in query
        assert 'GROUP BY "customers"."segment"' in query
        return {
            "success": True,
            "result": [{"customer_segment": "Enterprise", "paid_revenue": 120.5}],
            "returned_count": 1,
            "total_count": 1,
            "limited": False,
        }

    monkeypatch.setattr(
        "server.services.semantic_model_service.AsyncRawQueryService.execute_raw_query",
        fake_execute_raw_query,
    )

    query_response = await test_client.post(
        "/api/data-models/sales-semantic/mcp/query_metric",
        json={"metric": "paid_revenue", "dimension": "customer_segment"},
    )
    assert query_response.status_code == 200
    assert query_response.json()["data"]["status"] == "completed"


async def test_published_sqlite_metric_query_omits_synthetic_schema(
    test_client,
    test_session,
    monkeypatch,
):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    _, dataset = await _create_connection_dataset(test_session, tenant.id, tenant.owner_id)
    model = await _create_semantic_model(test_session, tenant, str(dataset.id))

    from server.models.semantic_models import SemanticModelEntity

    orders = await test_session.scalar(
        select(SemanticModelEntity).where(
            SemanticModelEntity.model_id == model.id,
            SemanticModelEntity.slug == "orders",
        )
    )
    assert orders is not None
    orders.profile_json = json.dumps({"schema": "sqlite"})
    await test_session.commit()

    validate_response = await test_client.post("/api/data-models/sales-semantic/validate")
    assert validate_response.status_code == 200
    publish_response = await test_client.post("/api/data-models/sales-semantic/publish")
    assert publish_response.status_code == 200

    async def fake_execute_raw_query(**kwargs):
        query = kwargs["query"]
        assert kwargs["db_type"] == "sqlite"
        assert 'FROM "orders" AS "orders"' in query
        assert '"sqlite"."orders"' not in query
        return {
            "success": True,
            "result": [{"order_status": "PAID", "paid_revenue": 120.5}],
            "returned_count": 1,
            "total_count": 1,
            "limited": False,
        }

    monkeypatch.setattr(
        "server.services.semantic_model_service.AsyncRawQueryService.execute_raw_query",
        fake_execute_raw_query,
    )

    query_response = await test_client.post(
        "/api/data-models/sales-semantic/mcp/query_metric",
        json={"metric": "paid_revenue", "dimension": "order_status"},
    )
    assert query_response.status_code == 200
    assert query_response.json()["data"]["status"] == "completed"
    assert query_response.json()["data"]["result"][0]["paid_revenue"] == 120.5


@pytest.mark.parametrize(
    ("filename", "content", "content_type", "model_slug"),
    [
        (
            "revenue.csv",
            b"order_id,region,revenue,paid_at\n1,East,120,2026-08-01\n2,West,80,2026-08-02\n",
            "text/csv",
            "projected-revenue-csv-mcp",
        ),
        (
            "revenue.jsonl",
            b'{"order_id":1,"region":"East","revenue":120,"paid_at":"2026-08-01"}\n'
            b'{"order_id":2,"region":"West","revenue":80,"paid_at":"2026-08-02"}\n',
            "application/x-ndjson",
            "projected-revenue-jsonl-mcp",
        ),
    ],
)
async def test_projected_dataset_semantic_model_publish_and_mcp_query(
    test_client, monkeypatch, filename, content, content_type, model_slug
):
    uploaded = await test_client.post(
        "/api/source-resources/files",
        files={
            "file": (
                filename,
                content,
                content_type,
            )
        },
        data={"name": "projected revenue"},
    )
    assert uploaded.status_code == 201
    projected_dataset_id = uploaded.json()["data"]["projected_dataset_id"]
    assert projected_dataset_id

    analyzed = await test_client.post(
        f"/api/datasources/{projected_dataset_id}/understanding/analyze",
        json={},
    )
    assert analyzed.status_code == 200
    understanding = analyzed.json()["data"]
    selected = [
        candidate
        for candidate in understanding["candidates"]
        if candidate["candidate_type"] in {"schema_map", "data_truth", "relationship"}
    ]
    assert {candidate["candidate_type"] for candidate in selected} >= {"schema_map", "data_truth"}
    for candidate in selected:
        reviewed = await test_client.post(
            f"/api/datasources/{projected_dataset_id}/understanding/candidates/{candidate['id']}/review",
            json={"action": "accept"},
        )
        assert reviewed.status_code == 200

    drafted = await test_client.post(
        f"/api/datasources/{projected_dataset_id}/understanding/semantic-model-draft",
        json={
            "model_id": model_slug,
            "name": "Projected Revenue MCP",
            "domain": "Sales / Orders",
            "owner": "Revenue Analytics",
            "candidate_ids": [candidate["id"] for candidate in selected],
        },
    )
    assert drafted.status_code == 200
    draft = drafted.json()["data"]["model"]
    assert draft["datasourceId"] == projected_dataset_id
    assert draft["datasourceKind"] == "duckdb"

    validated = await test_client.post(f"/api/data-models/{model_slug}/validate")
    assert validated.status_code == 200
    assert validated.json()["data"]["readinessDetail"]["blockers"] == []

    published = await test_client.post(f"/api/data-models/{model_slug}/publish")
    assert published.status_code == 200
    assert published.json()["data"]["status"] == "Published"

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

    query_response = await test_client.post(
        f"/api/data-models/{model_slug}/mcp/query_metric",
        json={"metric": "revenue_revenue", "dimension": "revenue_region", "limit": 10},
    )
    assert query_response.status_code == 200
    payload = query_response.json()["data"]
    assert payload["status"] == "completed"
    assert payload["modelVersion"] == "v1"
    assert payload["resolvedMetric"] == "Revenue Revenue"
    assert sorted(payload["result"], key=lambda item: item["revenue_region"]) == [
        {"revenue_region": "East", "revenue_revenue": 120},
        {"revenue_region": "West", "revenue_revenue": 80},
    ]
    assert calls and calls[0]["dataset_id"] == projected_dataset_id
    assert 'FROM "revenue" AS "revenue"' in calls[0]["query"]
    assert '"projection"."revenue"' not in calls[0]["query"]
