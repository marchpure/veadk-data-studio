from __future__ import annotations

from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.dashboard import Dashboard, DashboardAuditEvent
from server.models.notebooks import Notebook
from server.models.tenant import Tenant
from server.models.user import User
from server.services.dashboard import DashboardService


def _manifest_payload(dashboard_id: str = "dash-revenue") -> dict:
    return {
        "schema_version": "dashboard.manifest.v1",
        "dashboard_id": dashboard_id,
        "title": "Revenue operations",
        "description": "Revenue decision surface",
        "audience": ["finance"],
        "semantic_bindings": [
            {
                "id": "sales-model",
                "model_slug": "sales",
                "model_version": "v1",
                "source_snapshot_ids": ["source-snapshot-1"],
                "allowed_metrics": ["revenue"],
                "allowed_dimensions": ["region"],
            }
        ],
        "data_views": [
            {
                "id": "dv-revenue",
                "kind": "semantic_metric",
                "question": "How much revenue is recognized?",
                "output_schema": [{"name": "revenue", "data_type": "number", "unit": "USD"}],
                "semantic_metric": {"semantic_binding_id": "sales-model", "metric": "revenue"},
            }
        ],
        "filters": [],
        "layout": {"sections": [{"id": "main", "tile_ids": ["tile-revenue"]}]},
        "tiles": [
            {
                "id": "tile-revenue",
                "title": "Revenue",
                "tile_type": "kpi",
                "business_question": "What is recognized revenue?",
                "data_view_id": "dv-revenue",
            }
        ],
        "actions": [],
        "freshness_policy": {"mode": "live", "max_age_seconds": 3600, "allow_stale": True},
        "access_policy": {"required_scopes": ["dashboard:read", "dashboard:query"]},
        "provenance": {"created_by_actor_type": "human", "created_by": "user-1", "source": "human"},
        "migration": {"state": "new_structured", "blockers": []},
    }


async def _seed_owner_notebook(test_session: AsyncSession) -> dict[str, UUID]:
    user_id = uuid4()
    tenant_id = uuid4()
    notebook_id = uuid4()
    test_session.add(
        User(
            id=user_id,
            email=f"dashboard-{user_id}@example.test",
            hashed_password="hash",
            is_active=True,
            is_verified=True,
        )
    )
    await test_session.flush()
    test_session.add(Tenant(id=tenant_id, name="Dashboard Tenant", slug=f"dashboard-{tenant_id}", owner_id=user_id))
    await test_session.flush()
    test_session.add(
        Notebook(
            id=notebook_id,
            tenant_id=tenant_id,
            created_by=user_id,
            notebook_name="Dashboard notebook",
        )
    )
    await test_session.commit()
    return {"tenant_id": tenant_id, "user_id": user_id, "notebook_id": notebook_id}


@pytest.mark.asyncio
async def test_create_asset_draft_persists_manifest_etag_and_audit(test_session: AsyncSession) -> None:
    ids = await _seed_owner_notebook(test_session)
    service = DashboardService()

    asset = await service.create_asset_draft(
        session=test_session,
        tenant_id=ids["tenant_id"],
        actor_id=ids["user_id"],
        notebook_id=ids["notebook_id"],
        slug="revenue-ops",
        manifest_payload=_manifest_payload(),
    )

    assert asset.lifecycle == "draft"
    assert asset.etag.startswith("sha256:")
    assert asset.current_draft_version_id is not None
    draft = await test_session.scalar(select(Dashboard).where(Dashboard.asset_id == asset.id))
    assert draft is not None
    assert draft.status == "draft"
    assert draft.manifest_schema_version == "dashboard.manifest.v1"
    assert draft.content_hash.startswith("sha256:")
    assert draft.pinned_model_versions_json == {"sales": "v1"}
    assert draft.pinned_source_snapshots_json == ["source-snapshot-1"]
    assert draft.validation_result_json["valid"] is True

    audit_events = (
        await test_session.execute(select(DashboardAuditEvent).where(DashboardAuditEvent.asset_id == asset.id))
    ).scalars().all()
    assert [event.action for event in audit_events] == ["dashboard.draft.create"]


@pytest.mark.asyncio
async def test_patch_draft_rejects_stale_etag(test_session: AsyncSession) -> None:
    ids = await _seed_owner_notebook(test_session)
    service = DashboardService()
    asset = await service.create_asset_draft(
        session=test_session,
        tenant_id=ids["tenant_id"],
        actor_id=ids["user_id"],
        notebook_id=ids["notebook_id"],
        slug="revenue-conflict",
        manifest_payload=_manifest_payload("dash-conflict"),
    )

    with pytest.raises(HTTPException) as exc:
        await service.patch_draft(
            session=test_session,
            tenant_id=ids["tenant_id"],
            asset_id=asset.id,
            actor_id=ids["user_id"],
            base_etag="stale",
            manifest_payload=_manifest_payload("dash-conflict"),
            change_summary="stale patch",
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "etag_conflict"


@pytest.mark.asyncio
async def test_patch_draft_creates_new_version_and_publish_freezes_it(test_session: AsyncSession) -> None:
    ids = await _seed_owner_notebook(test_session)
    service = DashboardService()
    asset = await service.create_asset_draft(
        session=test_session,
        tenant_id=ids["tenant_id"],
        actor_id=ids["user_id"],
        notebook_id=ids["notebook_id"],
        slug="revenue-publish",
        manifest_payload=_manifest_payload("dash-publish"),
    )
    first_etag = asset.etag
    patched_manifest = deepcopy(_manifest_payload("dash-publish"))
    patched_manifest["title"] = "Revenue operations reviewed"

    draft = await service.patch_draft(
        session=test_session,
        tenant_id=ids["tenant_id"],
        asset_id=asset.id,
        actor_id=ids["user_id"],
        base_etag=first_etag,
        manifest_payload=patched_manifest,
        change_summary="review title",
    )
    await test_session.refresh(asset)

    assert draft.version_num == 2
    assert asset.current_draft_version_id == draft.id
    assert asset.etag != first_etag

    published = await service.publish(
        session=test_session,
        tenant_id=ids["tenant_id"],
        asset_id=asset.id,
        actor_id=ids["user_id"],
        base_etag=asset.etag,
        change_summary="publish reviewed dashboard",
    )
    await test_session.refresh(asset)

    assert published.status == "published"
    assert published.is_published_immutable is True
    assert asset.lifecycle == "published"
    assert asset.published_version_id == published.id

    audit_events = (
        await test_session.execute(
            select(DashboardAuditEvent.action).where(DashboardAuditEvent.asset_id == asset.id).order_by(DashboardAuditEvent.created_at)
        )
    ).scalars().all()
    assert audit_events == ["dashboard.draft.create", "dashboard.draft.patch", "dashboard.publish"]
