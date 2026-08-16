from __future__ import annotations

import json
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.models.dashboard import DashboardRun
from server.models.notebooks import Notebook
from server.models.tenant import Tenant
from server.models.user import User

pytestmark = pytest.mark.asyncio


def _manifest_payload(query_id: str | None = None, dashboard_id: str = "dash-rest") -> dict:
    query_id = query_id or str(uuid4())
    return {
        "schema_version": "dashboard.manifest.v1",
        "dashboard_id": dashboard_id,
        "title": "REST governed dashboard",
        "description": "Dashboard exposed through the governed REST contract",
        "audience": ["finance"],
        "semantic_bindings": [
            {
                "id": "sales-model",
                "model_slug": "sales",
                "model_version": "v1",
                "source_snapshot_ids": ["snapshot-1"],
                "allowed_metrics": ["revenue"],
                "allowed_dimensions": ["region"],
            }
        ],
        "data_views": [
            {
                "id": "dv-saved-revenue",
                "kind": "saved_query",
                "question": "What revenue did the reviewed query return?",
                "output_schema": [{"name": "revenue", "data_type": "number", "unit": "USD"}],
                "filter_fields": ["region"],
                "saved_query": {
                    "query_id": query_id,
                    "compatibility_reason": "reviewed legacy dashboard query",
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
        "access_policy": {"required_scopes": ["dashboard:read", "dashboard:query"]},
        "provenance": {"created_by_actor_type": "human", "created_by": "user-1", "source": "human"},
        "migration": {"state": "new_structured", "blockers": []},
    }


def _manifest_with_policy_refs(query_id: str) -> dict:
    manifest = _manifest_payload(query_id=query_id, dashboard_id="dash-rest-policy")
    manifest["access_policy"] = {
        "required_scopes": ["dashboard:read", "dashboard:query"],
        "row_policy_refs": ["tenant_rls"],
        "column_policy_refs": ["finance_columns"],
        "redaction_policy_refs": ["pii_redaction"],
    }
    return manifest


async def _seed_notebook(test_session) -> Notebook:
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    notebook = Notebook(
        id=uuid4(),
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        notebook_name="Dashboard REST notebook",
    )
    test_session.add(notebook)
    await test_session.commit()
    await test_session.refresh(notebook)
    return notebook


async def _seed_owned_notebook(test_session) -> tuple[Tenant, User, Notebook]:
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    owner = await test_session.get(User, tenant.owner_id)
    assert owner is not None
    notebook = Notebook(
        id=uuid4(),
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        notebook_name="Dashboard REST parity notebook",
    )
    test_session.add(notebook)
    await test_session.commit()
    await test_session.refresh(notebook)
    return tenant, owner, notebook


async def test_dashboard_asset_rest_lifecycle_query_state_lineage_and_audit(
    test_client,
    test_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notebook = await _seed_notebook(test_session)
    query_id = str(uuid4())
    manifest = _manifest_payload(query_id)

    create_response = await test_client.post(
        "/api/dashboard-assets",
        json={
            "slug": "rest-governed-dashboard",
            "notebook_id": str(notebook.id),
            "manifest": manifest,
            "tags": ["finance"],
            "change_summary": "create from API",
        },
    )
    assert create_response.status_code == 201
    asset = create_response.json()["data"]
    assert asset["slug"] == "rest-governed-dashboard"
    assert asset["lifecycle"] == "draft"
    assert asset["etag"].startswith("sha256:")

    list_response = await test_client.get("/api/dashboard-assets")
    assert list_response.status_code == 200
    assert list_response.json()["data"]["total"] == 1

    get_response = await test_client.get(f"/api/dashboard-assets/{asset['id']}")
    assert get_response.status_code == 200
    current = get_response.json()["data"]
    assert current["versions"][0]["version_num"] == 1
    assert current["versions"][0]["status"] == "draft"

    version_response = await test_client.get(f"/api/dashboard-assets/{asset['id']}/versions/1")
    assert version_response.status_code == 200
    assert version_response.json()["data"]["manifest"]["data_views"][0]["id"] == "dv-saved-revenue"

    validate_response = await test_client.post(f"/api/dashboard-assets/{asset['id']}/validate", json={})
    assert validate_response.status_code == 200
    assert validate_response.json()["data"]["validation"]["valid"] is True

    patched_manifest = deepcopy(manifest)
    patched_manifest["title"] = "REST governed dashboard reviewed"
    patch_response = await test_client.patch(
        f"/api/dashboard-assets/{asset['id']}/draft",
        json={
            "base_etag": asset["etag"],
            "manifest": patched_manifest,
            "change_summary": "review title",
        },
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()["data"]
    assert patched["version_num"] == 2
    assert patched["manifest"]["title"] == "REST governed dashboard reviewed"

    stale_patch_response = await test_client.patch(
        f"/api/dashboard-assets/{asset['id']}/draft",
        json={
            "base_etag": asset["etag"],
            "manifest": patched_manifest,
            "change_summary": "stale retry",
        },
    )
    assert stale_patch_response.status_code == 409
    assert stale_patch_response.json()["data"]["code"] == "etag_conflict"

    refreshed_response = await test_client.get(f"/api/dashboard-assets/{asset['id']}")
    assert refreshed_response.status_code == 200
    refreshed = refreshed_response.json()["data"]
    publish_response = await test_client.post(
        f"/api/dashboard-assets/{asset['id']}/publish",
        json={"base_etag": refreshed["etag"], "change_summary": "publish from API"},
    )
    assert publish_response.status_code == 200
    published = publish_response.json()["data"]
    assert published["status"] == "published"
    assert published["is_published_immutable"] is True

    captured: dict[str, object] = {}

    async def fake_execute_saved_query(session, query_id_arg, filters=None, viewer_user_id=None):
        captured["query_id"] = query_id_arg
        captured["filters"] = filters
        captured["viewer_user_id"] = viewer_user_id
        return {
            "success": True,
            "data": [{"revenue": 42}],
            "query_id": query_id_arg,
            "cached": True,
            "stale": False,
            "as_of": "2026-08-16T00:00:00",
        }

    monkeypatch.setattr("server.services.dashboard.QueryService.execute_saved_query", fake_execute_saved_query)

    preview_response = await test_client.post(
        f"/api/dashboard-assets/{asset['id']}/preview",
        json={"data_view_ids": ["dv-saved-revenue"], "correlation_id": "corr-preview"},
    )
    assert preview_response.status_code == 200
    preview_run = preview_response.json()["data"]
    assert preview_run["preview"] is True
    assert preview_run["dashboard_version_id"] == published["id"]

    published_asset_response = await test_client.get(f"/api/dashboard-assets/{asset['id']}")
    assert published_asset_response.status_code == 200
    published_asset = published_asset_response.json()["data"]
    reload_response = await test_client.post(
        f"/api/dashboard-assets/{asset['id']}/reload",
        json={
            "base_etag": published_asset["etag"],
            "semantic_model_versions": {"sales": "v2"},
            "source_snapshot_ids": ["snapshot-2"],
            "change_summary": "reload model pins",
        },
    )
    assert reload_response.status_code == 200
    reload_payload = reload_response.json()["data"]
    reload_draft = reload_payload["draft"]
    assert reload_draft["status"] == "draft"
    assert reload_draft["version_num"] == 3
    assert reload_draft["manifest"]["migration"]["state"] == "needs_review"
    assert reload_draft["pinned_model_versions"] == {"sales": "v2"}
    assert reload_draft["pinned_source_snapshots"] == ["snapshot-2"]
    assert reload_payload["semantic_diff"]["model_version_changes"][0]["from"] == "v1"
    assert reload_payload["semantic_diff"]["model_version_changes"][0]["to"] == "v2"
    assert reload_payload["semantic_diff"]["source_snapshot_changes"][0]["from"] == ["snapshot-1"]
    assert reload_payload["semantic_diff"]["source_snapshot_changes"][0]["to"] == ["snapshot-2"]

    state_after_reload_response = await test_client.get(f"/api/dashboard-assets/{asset['id']}/state")
    assert state_after_reload_response.status_code == 200
    state_after_reload = state_after_reload_response.json()["data"]
    assert state_after_reload["asset"]["lifecycle"] == "in_review"
    assert state_after_reload["published_version_id"] == published["id"]
    assert state_after_reload["draft_version_id"] == reload_draft["id"]

    query_response = await test_client.post(
        f"/api/dashboard-assets/{asset['id']}/query",
        json={
            "filters": {"region": "AMER"},
            "data_view_ids": ["dv-saved-revenue"],
            "correlation_id": "corr-rest",
        },
    )
    assert query_response.status_code == 200
    run = query_response.json()["data"]
    assert captured["query_id"] == query_id
    assert captured["viewer_user_id"] is None
    assert run["dashboard_id"] == asset["id"]
    assert run["views"][0]["result"] == [{"revenue": 42}]
    assert run["views"][0]["cached"] is True
    assert run["views"][0]["as_of"] == "2026-08-16T00:00:00"

    saved_run = await test_session.get(DashboardRun, run["run_id"])
    assert saved_run is not None
    assert saved_run.correlation_id == "corr-rest"

    unknown_view_response = await test_client.post(
        f"/api/dashboard-assets/{asset['id']}/query",
        json={"data_view_ids": ["missing-view"]},
    )
    assert unknown_view_response.status_code == 403

    unknown_filter_response = await test_client.post(
        f"/api/dashboard-assets/{asset['id']}/query",
        json={
            "filters": {"region": "AMER", "raw_sql": "select * from other_tenant.secret"},
            "data_view_ids": ["dv-saved-revenue"],
        },
    )
    assert unknown_filter_response.status_code == 403
    assert "filters are not available" in unknown_filter_response.json()["message"]

    export_response = await test_client.get(f"/api/dashboard-assets/{asset['id']}/export/html")
    assert export_response.status_code == 200
    assert "text/html" in export_response.headers["content-type"]
    assert 'attachment; filename="rest-governed-dashboard-v2.html"' == export_response.headers["content-disposition"]
    assert "dashboard.manifest.v1" in export_response.text
    assert "REST governed dashboard reviewed" in export_response.text
    assert "dv-saved-revenue" in export_response.text

    state_response = await test_client.get(f"/api/dashboard-assets/{asset['id']}/state")
    assert state_response.status_code == 200
    state_payload = state_response.json()["data"]
    assert state_payload["asset"]["lifecycle"] == "in_review"
    assert state_payload["published_version_id"] == published["id"]
    assert state_payload["draft_version_id"] == reload_draft["id"]
    assert len(state_payload["versions"]) == 3

    lineage_response = await test_client.get(f"/api/dashboard-assets/{asset['id']}/lineage")
    assert lineage_response.status_code == 200
    lineage_payload = lineage_response.json()["data"]
    assert lineage_payload["lineage"]["semantic_bindings"][0]["model_slug"] == "sales"
    assert lineage_payload["lineage"]["data_views"][0]["lineage"][0]["ref"] == query_id

    audit_response = await test_client.get(f"/api/dashboard-assets/{asset['id']}/audit")
    assert audit_response.status_code == 200
    audit_actions = [item["action"] for item in audit_response.json()["data"]["items"]]
    assert "dashboard.draft.create" in audit_actions
    assert "dashboard.draft.patch" in audit_actions
    assert "dashboard.publish" in audit_actions
    assert "dashboard.preview" in audit_actions
    assert "dashboard.reload" in audit_actions
    assert "dashboard.query" in audit_actions
    assert "dashboard.export" in audit_actions


async def test_dashboard_full_manifest_patch_rejects_non_allowlisted_top_level_change(
    test_client,
    test_session,
) -> None:
    notebook = await _seed_notebook(test_session)
    manifest = _manifest_payload()
    create_response = await test_client.post(
        "/api/dashboard-assets",
        json={
            "slug": "rest-governed-dashboard-full-manifest-guard",
            "notebook_id": str(notebook.id),
            "manifest": manifest,
            "change_summary": "create guard fixture",
        },
    )
    assert create_response.status_code == 201
    asset = create_response.json()["data"]

    blocked_manifest = deepcopy(manifest)
    blocked_manifest["dashboard_id"] = "blocked-dashboard-id-rewrite"
    patch_response = await test_client.patch(
        f"/api/dashboard-assets/{asset['id']}/draft",
        json={
            "base_etag": asset["etag"],
            "manifest": blocked_manifest,
            "change_summary": "attempt non-allowlisted full manifest change",
        },
    )

    assert patch_response.status_code == 403
    data = patch_response.json()["data"]
    assert data["code"] == "dashboard_manifest_patch_forbidden"
    assert data["blocked_keys"] == ["dashboard_id"]


async def test_dashboard_json_patch_returns_structured_etag_conflict(
    test_client,
    test_session,
) -> None:
    notebook = await _seed_notebook(test_session)
    manifest = _manifest_payload()
    create_response = await test_client.post(
        "/api/dashboard-assets",
        json={
            "slug": "rest-governed-dashboard-json-patch-conflict",
            "notebook_id": str(notebook.id),
            "manifest": manifest,
            "change_summary": "create conflict fixture",
        },
    )
    assert create_response.status_code == 201
    asset = create_response.json()["data"]

    first_patch = await test_client.patch(
        f"/api/dashboard-assets/{asset['id']}/draft",
        json={
            "base_etag": asset["etag"],
            "json_patch": [{"op": "replace", "path": "/title", "value": "Conflict fixture updated"}],
            "change_summary": "first patch",
        },
    )
    assert first_patch.status_code == 200

    stale_patch = await test_client.patch(
        f"/api/dashboard-assets/{asset['id']}/draft",
        json={
            "base_etag": asset["etag"],
            "json_patch": [{"op": "replace", "path": "/description", "value": "stale description"}],
            "change_summary": "stale patch",
        },
    )

    assert stale_patch.status_code == 409
    data = stale_patch.json()["data"]
    assert data["code"] == "etag_conflict"
    assert data["current_etag"].startswith("sha256:")
    assert data["current_etag"] != asset["etag"]


async def test_dashboard_asset_rest_enforces_tenant_and_notebook_boundaries(test_client, test_session) -> None:
    missing_notebook_response = await test_client.post(
        "/api/dashboard-assets",
        json={
            "slug": "missing-notebook-dashboard",
            "notebook_id": str(uuid4()),
            "manifest": _manifest_payload(dashboard_id="dash-missing-notebook"),
        },
    )
    assert missing_notebook_response.status_code == 404
    assert missing_notebook_response.json()["message"] == "Notebook not found"

    response = await test_client.get(f"/api/dashboard-assets/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["message"] == "Dashboard asset not found"


async def test_dashboard_rest_query_matches_mcp_contract_for_same_principal(
    test_client,
    test_session,
    test_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from server.mcp import tool_wrappers
    from server.mcp.tool_wrappers import query_dashboard_wrapper

    tenant, owner, notebook = await _seed_owned_notebook(test_session)
    query_id = str(uuid4())
    manifest = _manifest_payload(query_id, dashboard_id="dash-rest-mcp-parity")
    create_response = await test_client.post(
        "/api/dashboard-assets",
        json={
            "slug": "rest-mcp-parity-dashboard",
            "notebook_id": str(notebook.id),
            "manifest": manifest,
            "change_summary": "create parity dashboard",
        },
    )
    assert create_response.status_code == 201
    asset = create_response.json()["data"]
    publish_response = await test_client.post(
        f"/api/dashboard-assets/{asset['id']}/publish",
        json={"base_etag": asset["etag"], "change_summary": "publish parity dashboard"},
    )
    assert publish_response.status_code == 200

    async def fake_execute_saved_query(session, query_id_arg, filters=None, viewer_user_id=None):
        return {
            "success": True,
            "data": [{"revenue": 42, "region": "AMER"}],
            "query_name": "Parity query",
            "query_id": query_id_arg,
            "cached": True,
            "stale": False,
            "as_of": "2026-08-16T12:34:56",
        }

    monkeypatch.setattr("server.services.dashboard.QueryService.execute_saved_query", fake_execute_saved_query)

    rest_response = await test_client.post(
        f"/api/dashboard-assets/{asset['id']}/query",
        json={
            "filters": {"region": "AMER"},
            "data_view_ids": ["dv-saved-revenue"],
            "correlation_id": "parity",
            "idempotency_key": "rest-parity",
        },
    )
    assert rest_response.status_code == 200
    rest_run = rest_response.json()["data"]

    monkeypatch.setattr(
        tool_wrappers,
        "AsyncSessionFactory",
        async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False),
    )
    mcp_payload = json.loads(
        await query_dashboard_wrapper(
            asset["id"],
            ["dv-saved-revenue"],
            {"region": "AMER"},
            "",
            20,
            tenant.id,
            owner.id,
        )
    )
    assert mcp_payload["success"] is True
    mcp_run = mcp_payload["run"]

    assert mcp_run["dashboard_id"] == rest_run["dashboard_id"]
    assert mcp_run["dashboard_version_id"] == rest_run["dashboard_version_id"]
    assert mcp_run["mode"] == rest_run["mode"] == "live"
    assert mcp_run["normalized_filters"] == rest_run["normalized_filters"] == {"region": "AMER"}
    assert mcp_run["filter_digest"] == rest_run["filter_digest"]
    assert mcp_run["execution_plan_digest"] == rest_run["execution_plan_digest"]
    assert mcp_run["pinned_versions"] == rest_run["pinned_versions"]
    assert mcp_run["overall_freshness"] == rest_run["overall_freshness"]
    assert mcp_run["warnings"] == rest_run["warnings"]
    assert mcp_run["views"][0]["data_view_id"] == rest_run["views"][0]["data_view_id"]
    assert mcp_run["views"][0]["result"] == rest_run["views"][0]["result"]
    assert mcp_run["views"][0]["schema"] == rest_run["views"][0]["schema"]
    assert mcp_run["views"][0]["cached"] == rest_run["views"][0]["cached"] is True
    assert mcp_run["views"][0]["stale"] == rest_run["views"][0]["stale"] is False
    assert mcp_run["views"][0]["as_of"] == rest_run["views"][0]["as_of"] == "2026-08-16T12:34:56"


async def test_dashboard_rest_query_blocks_unresolved_policy_refs_before_saved_query_execution(
    test_client,
    test_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notebook = await _seed_notebook(test_session)
    query_id = str(uuid4())
    create_response = await test_client.post(
        "/api/dashboard-assets",
        json={
            "slug": "rest-policy-guard-dashboard",
            "notebook_id": str(notebook.id),
            "manifest": _manifest_with_policy_refs(query_id),
            "change_summary": "create policy guard dashboard",
        },
    )
    assert create_response.status_code == 201
    asset = create_response.json()["data"]
    publish_response = await test_client.post(
        f"/api/dashboard-assets/{asset['id']}/publish",
        json={"base_etag": asset["etag"], "change_summary": "publish policy guard dashboard"},
    )
    assert publish_response.status_code == 200

    executed = False

    async def fake_execute_saved_query(*_args, **_kwargs):
        nonlocal executed
        executed = True
        return {"success": True, "data": [{"revenue": 42}]}

    monkeypatch.setattr("server.services.dashboard.QueryService.execute_saved_query", fake_execute_saved_query)

    query_response = await test_client.post(
        f"/api/dashboard-assets/{asset['id']}/query",
        json={"filters": {"region": "AMER"}, "data_view_ids": ["dv-saved-revenue"], "correlation_id": "policy-guard"},
    )
    assert query_response.status_code == 200
    run = query_response.json()["data"]
    assert executed is False
    assert run["overall_freshness"] == "blocked"
    assert run["views"][0]["status"] == "permission_denied"
    assert run["views"][0]["result"] is None
    assert run["views"][0]["error"]["code"] == "policy_not_enforced"
    assert run["views"][0]["error"]["policy_reason"] == (
        "row_policy_refs=tenant_rls; column_policy_refs=finance_columns; redaction_policy_refs=pii_redaction"
    )
    assert run["warnings"] == ["Dashboard access policy refs are not resolved for this execution context"]

    saved_run = await test_session.get(DashboardRun, run["run_id"])
    assert saved_run is not None
    assert saved_run.overall_freshness == "blocked"
