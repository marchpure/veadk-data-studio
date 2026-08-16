from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.dashboard import DashboardAuditEvent, DashboardRun
from server.models.notebooks import Notebook
from server.models.tenant import Tenant
from server.models.user import User
from server.services.dashboard import DashboardService


def _manifest_payload(query_id: str, access_policy: dict | None = None) -> dict:
    return {
        "schema_version": "dashboard.manifest.v1",
        "dashboard_id": "dash-saved-query",
        "title": "Saved query dashboard",
        "description": "Compatibility dashboard",
        "audience": ["finance"],
        "semantic_bindings": [
            {
                "id": "sales-model",
                "model_slug": "sales",
                "model_version": "v1",
                "source_snapshot_ids": ["snapshot-1"],
                "allowed_metrics": ["revenue"],
            }
        ],
        "data_views": [
            {
                "id": "dv-saved-revenue",
                "kind": "saved_query",
                "question": "What revenue did the saved query return?",
                "output_schema": [{"name": "revenue", "data_type": "number", "unit": "USD"}],
                "filter_fields": ["region"],
                "saved_query": {
                    "query_id": query_id,
                    "compatibility_reason": "legacy reviewed dashboard query",
                    "filter_contract": {},
                    "lineage": [
                        {
                            "id": "query-lineage",
                            "kind": "saved_query",
                            "name": "Revenue query",
                            "ref": query_id,
                        }
                    ],
                },
            }
        ],
        "filters": [
            {
                "id": "region",
                "label": "Region",
                "source": "saved_query_contract",
                "field": "region",
                "filter_type": "enum",
                "operators": ["eq"],
                "affected_data_view_ids": ["dv-saved-revenue"],
            }
        ],
        "layout": {"sections": [{"id": "main", "tile_ids": ["tile-revenue"]}]},
        "tiles": [
            {
                "id": "tile-revenue",
                "title": "Revenue",
                "tile_type": "kpi",
                "business_question": "What is revenue?",
                "data_view_id": "dv-saved-revenue",
            }
        ],
        "actions": [],
        "freshness_policy": {"mode": "live", "max_age_seconds": 3600, "allow_stale": True},
        "access_policy": access_policy or {"required_scopes": ["dashboard:read", "dashboard:query"]},
        "provenance": {"created_by_actor_type": "human", "created_by": "user-1", "source": "human"},
        "migration": {"state": "new_structured", "blockers": []},
    }


async def _seed_published_saved_query_dashboard(
    test_session: AsyncSession,
    query_id: str,
    access_policy: dict | None = None,
) -> dict[str, UUID]:
    user_id = uuid4()
    tenant_id = uuid4()
    notebook_id = uuid4()
    test_session.add(
        User(
            id=user_id,
            email=f"dashboard-exec-{user_id}@example.test",
            hashed_password="hash",
            is_active=True,
            is_verified=True,
        )
    )
    await test_session.flush()
    test_session.add(Tenant(id=tenant_id, name="Dashboard Exec Tenant", slug=f"dashboard-exec-{tenant_id}", owner_id=user_id))
    await test_session.flush()
    test_session.add(
        Notebook(
            id=notebook_id,
            tenant_id=tenant_id,
            created_by=user_id,
            notebook_name="Dashboard execution notebook",
        )
    )
    await test_session.commit()

    service = DashboardService()
    asset = await service.create_asset_draft(
        session=test_session,
        tenant_id=tenant_id,
        actor_id=user_id,
        notebook_id=notebook_id,
        slug=f"exec-{query_id}",
        manifest_payload=_manifest_payload(query_id, access_policy=access_policy),
    )
    published = await service.publish(
        session=test_session,
        tenant_id=tenant_id,
        asset_id=asset.id,
        actor_id=user_id,
        base_etag=asset.etag,
        change_summary="publish saved query dashboard",
    )
    return {"tenant_id": tenant_id, "user_id": user_id, "asset_id": asset.id, "version_id": published.id}


@pytest.mark.asyncio
async def test_query_dashboard_executes_manifest_bound_saved_query(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_id = str(uuid4())
    ids = await _seed_published_saved_query_dashboard(test_session, query_id)
    captured: dict[str, object] = {}

    async def fake_execute_saved_query(session, query_id_arg, filters=None, viewer_user_id=None):
        captured["query_id"] = query_id_arg
        captured["filters"] = filters
        captured["viewer_user_id"] = viewer_user_id
        return {
            "success": True,
            "data": [{"revenue": 42}],
            "query_name": "Revenue query",
            "query_id": query_id_arg,
            "cached": True,
            "stale": False,
        }

    monkeypatch.setattr("server.services.dashboard.QueryService.execute_saved_query", fake_execute_saved_query)

    run = await DashboardService().query_dashboard(
        session=test_session,
        tenant_id=ids["tenant_id"],
        asset_id=ids["asset_id"],
        actor_id=str(ids["user_id"]),
        actor_type="human",
        filters={"region": "AMER"},
        data_view_ids=["dv-saved-revenue"],
        correlation_id="corr-1",
    )

    assert captured["query_id"] == query_id
    assert captured["viewer_user_id"] is None
    assert run["dashboard_id"] == str(ids["asset_id"])
    assert run["dashboard_version_id"] == str(ids["version_id"])
    assert run["filter_digest"].startswith("sha256:")
    assert run["views"][0]["data_view_id"] == "dv-saved-revenue"
    assert run["views"][0]["result"] == [{"revenue": 42}]
    assert run["views"][0]["cached"] is True
    assert run["views"][0]["stale"] is False
    assert run["views"][0]["as_of"]
    assert run["pinned_versions"]["semantic_models"] == {"sales": "v1"}
    assert run["pinned_versions"]["source_snapshots"] == ["snapshot-1"]

    saved_run = await test_session.get(DashboardRun, UUID(run["run_id"]))
    assert saved_run is not None
    assert saved_run.result_manifest_json["filter_digest"] == run["filter_digest"]
    audit_actions = (
        await test_session.execute(
            select(DashboardAuditEvent.action).where(DashboardAuditEvent.asset_id == ids["asset_id"])
        )
    ).scalars().all()
    assert "dashboard.query" in audit_actions


@pytest.mark.asyncio
async def test_query_dashboard_rejects_unknown_data_view_before_execution(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_id = str(uuid4())
    ids = await _seed_published_saved_query_dashboard(test_session, query_id)
    executed = False

    async def fake_execute_saved_query(*_args, **_kwargs):
        nonlocal executed
        executed = True
        return {"success": True, "data": []}

    monkeypatch.setattr("server.services.dashboard.QueryService.execute_saved_query", fake_execute_saved_query)

    with pytest.raises(HTTPException) as exc:
        await DashboardService().query_dashboard(
            session=test_session,
            tenant_id=ids["tenant_id"],
            asset_id=ids["asset_id"],
            actor_id=str(ids["user_id"]),
            actor_type="agent",
            data_view_ids=["missing-view"],
        )

    assert exc.value.status_code == 403
    assert executed is False


@pytest.mark.asyncio
async def test_query_dashboard_blocks_pinned_snapshot_without_artifacts(test_session: AsyncSession) -> None:
    query_id = str(uuid4())
    ids = await _seed_published_saved_query_dashboard(test_session, query_id)

    with pytest.raises(HTTPException) as exc:
        await DashboardService().query_dashboard(
            session=test_session,
            tenant_id=ids["tenant_id"],
            asset_id=ids["asset_id"],
            actor_id=str(ids["user_id"]),
            actor_type="agent",
            mode="pinned_snapshot",
        )

    assert exc.value.status_code == 409
    assert "pinned_snapshot" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_query_dashboard_blocks_unresolved_access_policy_refs_before_execution(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_id = str(uuid4())
    ids = await _seed_published_saved_query_dashboard(
        test_session,
        query_id,
        access_policy={
            "required_scopes": ["dashboard:read", "dashboard:query"],
            "row_policy_refs": ["tenant_rls"],
            "column_policy_refs": ["finance_columns"],
            "redaction_policy_refs": ["pii_redaction"],
        },
    )
    executed = False

    async def fake_execute_saved_query(*_args, **_kwargs):
        nonlocal executed
        executed = True
        return {"success": True, "data": [{"revenue": 42}]}

    monkeypatch.setattr("server.services.dashboard.QueryService.execute_saved_query", fake_execute_saved_query)

    run = await DashboardService().query_dashboard(
        session=test_session,
        tenant_id=ids["tenant_id"],
        asset_id=ids["asset_id"],
        actor_id=str(ids["user_id"]),
        actor_type="human",
        filters={"region": "AMER"},
        data_view_ids=["dv-saved-revenue"],
        correlation_id="policy-guard",
    )

    assert executed is False
    assert run["overall_freshness"] == "blocked"
    assert run["warnings"] == ["Dashboard access policy refs are not resolved for this execution context"]
    assert run["errors"] == [
        {
            "code": "policy_not_enforced",
            "message": "Dashboard data view execution is blocked by unresolved access policy refs",
            "retryable": False,
            "policy_reason": "row_policy_refs=tenant_rls; column_policy_refs=finance_columns; redaction_policy_refs=pii_redaction",
        }
    ]
    assert run["views"][0]["data_view_id"] == "dv-saved-revenue"
    assert run["views"][0]["status"] == "permission_denied"
    assert run["views"][0]["result"] is None
    assert run["views"][0]["row_count"] == 0
    assert run["views"][0]["error"]["code"] == "policy_not_enforced"

    saved_run = await test_session.get(DashboardRun, UUID(run["run_id"]))
    assert saved_run is not None
    assert saved_run.overall_freshness == "blocked"
    assert saved_run.errors_json == run["errors"]
    audit_outcomes = (
        await test_session.execute(
            select(DashboardAuditEvent.outcome).where(
                DashboardAuditEvent.asset_id == ids["asset_id"],
                DashboardAuditEvent.action == "dashboard.query",
            )
        )
    ).scalars().all()
    assert "blocked" in audit_outcomes
