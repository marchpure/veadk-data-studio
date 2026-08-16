from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from server.models.connections import Connection
from server.models.datasets import Dataset
from server.models.semantic_models import SemanticModel
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
