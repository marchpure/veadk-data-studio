from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.connections import Connection
from server.models.dashboard import DashboardAsset
from server.models.datasets import Dataset
from server.models.notebooks import Notebook
from server.models.semantic_models import (
    SemanticModel,
    SemanticModelDimension,
    SemanticModelEntity,
    SemanticModelField,
    SemanticModelMetric,
)
from server.models.tenant import Tenant
from server.services.dashboard import DashboardService


def dashboard_manifest(query_id: str | None = None, *, title: str = "Published Sales Dashboard") -> dict:
    query_id = query_id or str(uuid4())
    return {
        "schema_version": "dashboard.manifest.v1",
        "dashboard_id": "sales-dashboard",
        "title": title,
        "description": "Curated dashboard for sales performance.",
        "audience": ["finance"],
        "semantic_bindings": [
            {
                "id": "sales-model",
                "model_slug": "sales-semantic",
                "model_version": "v1",
                "source_snapshot_ids": ["snapshot-1"],
                "allowed_metrics": ["paid_revenue"],
                "allowed_dimensions": ["order_status"],
            }
        ],
        "data_views": [
            {
                "id": "dv-paid-revenue",
                "kind": "saved_query",
                "question": "What paid revenue did the reviewed query return?",
                "output_schema": [
                    {"name": "paid_revenue", "data_type": "number", "unit": "USD"},
                    {"name": "order_status", "data_type": "string"},
                ],
                "filter_fields": ["order_status", "paid_at"],
                "evidence": [
                    {
                        "id": "evidence-revenue-definition",
                        "kind": "doc_section",
                        "title": "Paid revenue definition",
                        "locator": {"document": "policy.md", "section": "Revenue"},
                        "confidence": 0.92,
                    }
                ],
                "saved_query": {
                    "query_id": query_id,
                    "compatibility_reason": "reviewed legacy dashboard query",
                    "filter_contract": {},
                    "lineage": [
                        {
                            "id": "query-lineage",
                            "kind": "saved_query",
                            "name": "Paid revenue query",
                            "ref": query_id,
                        }
                    ],
                },
            }
        ],
        "filters": [
            {
                "id": "paid_at",
                "label": "Paid date",
                "source": "saved_query_contract",
                "field": "paid_at",
                "filter_type": "date_range",
                "operators": ["between"],
                "affected_data_view_ids": ["dv-paid-revenue"],
            },
            {
                "id": "order_status",
                "label": "Order status",
                "source": "saved_query_contract",
                "field": "order_status",
                "filter_type": "enum",
                "operators": ["eq"],
                "affected_data_view_ids": ["dv-paid-revenue"],
            },
        ],
        "layout": {"sections": [{"id": "main", "tile_ids": ["tile-paid-revenue"]}]},
        "tiles": [
            {
                "id": "tile-paid-revenue",
                "title": "Paid revenue",
                "tile_type": "kpi",
                "business_question": "What is paid revenue?",
                "data_view_id": "dv-paid-revenue",
            }
        ],
        "actions": [],
        "freshness_policy": {"mode": "live", "max_age_seconds": 3600, "allow_stale": True},
        "access_policy": {"required_scopes": ["dashboard:read", "dashboard:query"]},
        "provenance": {"created_by_actor_type": "human", "created_by": "user-1", "source": "human"},
        "migration": {"state": "new_structured", "blockers": []},
    }


async def current_tenant(session: AsyncSession) -> Tenant:
    tenant = (await session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    return tenant


async def seed_notebook(session: AsyncSession, tenant: Tenant, *, name: str = "Asset test notebook") -> Notebook:
    notebook = Notebook(id=uuid4(), tenant_id=tenant.id, created_by=tenant.owner_id, notebook_name=name)
    session.add(notebook)
    await session.commit()
    await session.refresh(notebook)
    return notebook


async def seed_dashboard_asset(
    session: AsyncSession,
    tenant: Tenant,
    *,
    slug: str,
    publish: bool,
    title: str = "Published Sales Dashboard",
) -> DashboardAsset:
    notebook = await seed_notebook(session, tenant)
    service = DashboardService()
    asset = await service.create_asset_draft(
        session=session,
        tenant_id=tenant.id,
        actor_id=tenant.owner_id,
        notebook_id=notebook.id,
        slug=slug,
        manifest_payload=dashboard_manifest(title=title),
        description="Sales dashboard description",
        tags=["finance"],
    )
    if publish:
        await service.publish(
            session=session,
            tenant_id=tenant.id,
            asset_id=asset.id,
            actor_id=tenant.owner_id,
            base_etag=asset.etag,
            change_summary="publish dashboard for tests",
        )
        await session.refresh(asset)
    return asset


async def seed_connection_dataset(session: AsyncSession, tenant: Tenant) -> Dataset:
    connection = Connection(
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        type="sqlite",
        name="SQLite Sales",
        connection_obj_encrypted=json.dumps({"database_path": ":memory:"}),
        schema_cache=json.dumps({"tables": {"orders": {"columns": []}}}),
        is_public=True,
    )
    session.add(connection)
    await session.flush()
    dataset = Dataset(
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        type="connection",
        name="SQLite Sales",
        connection_id=connection.id,
        is_public=True,
    )
    session.add(dataset)
    await session.commit()
    await session.refresh(dataset)
    return dataset


async def seed_semantic_model(session: AsyncSession, tenant: Tenant, *, published: bool = True) -> SemanticModel:
    dataset = await seed_connection_dataset(session, tenant)
    model = SemanticModel(
        id=uuid4(),
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        slug=f"sales-semantic-{uuid4().hex[:8]}",
        name="Sales Semantic",
        domain="Sales",
        owner="Revenue Analytics",
        datasource_id=str(dataset.id),
        datasource_name="SQLite Sales",
        datasource_kind="sqlite",
        description="Sales semantic model",
        status="Published" if published else "Draft",
        draft_revision="draft-1",
        published_version="v1" if published else "v0",
        readiness=95 if published else 10,
        readiness_level="ready" if published else "blocked",
        consumers_json=json.dumps({"consumers": ["agent", "mcp"]}),
        review_json=json.dumps({"sourceUnderstandingLineage": {"candidates": []}}),
        mcp_json=json.dumps({"allowedMetrics": ["paid_revenue"], "allowedDimensions": ["order_status"]}),
        validation_log_json=json.dumps([] if published else ["semantic model is not published"]),
    )
    session.add(model)
    await session.flush()

    entity = SemanticModelEntity(
        model_id=model.id,
        slug="orders",
        name="orders",
        business_name="Orders",
        table_name="orders",
        primary_key="order_id",
        entity_type="fact",
        validation_status="valid",
        sort_order=0,
    )
    session.add(entity)
    await session.flush()
    session.add_all(
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
        ]
    )
    session.add(
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
            lineage_json=json.dumps(["orders.net_amount"]),
            validation_status="valid",
            sort_order=0,
        )
    )
    session.add(
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
    await session.commit()
    await session.refresh(model)
    return model
