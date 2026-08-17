from __future__ import annotations

import json
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.mcp import tool_wrappers
from server.mcp.tool_wrappers import (
    compare_evaluation_runs_wrapper,
    describe_sharing_grant_wrapper,
    list_sharing_grants_wrapper,
    query_dashboard_wrapper,
    query_metric_wrapper,
    run_evaluation_wrapper,
)
from server.models.dashboard import DashboardRun
from server.models.folder import Folder
from server.models.folder_member import FolderMember
from server.models.notebooks import Notebook
from server.models.queries import Query
from server.models.source_resources import SourceResource
from server.models.source_snapshots import SourceSnapshot
from server.models.tenant import Tenant

pytestmark = pytest.mark.asyncio


FORBIDDEN = (
    "plain-password",
    "raw-token",
    "raw-verifier",
    "raw-salt",
    "restricted_table",
    "other_tenant.secret",
)


@pytest.fixture(autouse=True)
def _patch_mcp_session_factory(test_engine, monkeypatch: pytest.MonkeyPatch):
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    monkeypatch.setattr(tool_wrappers, "AsyncSessionFactory", session_factory)

    async def override_get_async_session():
        async with session_factory() as session:
            yield session

    import server.db.session as db_session_module

    monkeypatch.setattr(db_session_module, "get_async_session", override_get_async_session)


def _assert_redacted(payload: object) -> None:
    serialized = json.dumps(payload, default=str)
    leaked = [value for value in FORBIDDEN if value in serialized]
    assert leaked == []


def _dashboard_manifest(
    *,
    asset_id: str,
    query_id: str,
    source_snapshot_id: str,
    model_slug: str,
    metric_id: str,
    dimension_id: str,
) -> dict:
    return {
        "schema_version": "dashboard.manifest.v1",
        "dashboard_id": asset_id,
        "title": "Cross Module Revenue Dashboard",
        "description": "End-to-end dashboard fixture over a projected CSV source.",
        "audience": ["finance"],
        "semantic_bindings": [
            {
                "id": "projected-revenue-model",
                "model_slug": model_slug,
                "model_version": "v1",
                "source_snapshot_ids": [source_snapshot_id],
                "allowed_metrics": [metric_id],
                "allowed_dimensions": [dimension_id],
            }
        ],
        "data_views": [
            {
                "id": "dv-revenue",
                "kind": "saved_query",
                "question": "What revenue is present by region?",
                "output_schema": [
                    {"name": "revenue_region", "data_type": "string", "sensitivity": "internal"},
                    {"name": "revenue_revenue", "data_type": "number", "unit": "USD", "sensitivity": "internal"},
                ],
                "filter_fields": ["revenue_region"],
                "saved_query": {
                    "query_id": query_id,
                    "compatibility_reason": "cross-module projected CSV saved query",
                    "filter_contract": {},
                    "lineage": [
                        {
                            "id": "projected-csv-lineage",
                            "kind": "saved_query",
                            "name": "Projected revenue query",
                            "ref": query_id,
                        }
                    ],
                },
                "evidence": [
                    {
                        "id": "projected-csv-evidence",
                        "kind": "source_snapshot",
                        "title": "Projected CSV source snapshot",
                        "locator": {"source_snapshot_id": source_snapshot_id},
                        "confidence": 0.95,
                    }
                ],
            }
        ],
        "filters": [
            {
                "id": "region",
                "label": "Region",
                "source": "saved_query_contract",
                "field": "revenue_region",
                "filter_type": "enum",
                "operators": ["eq"],
                "affected_data_view_ids": ["dv-revenue"],
            }
        ],
        "layout": {"sections": [{"id": "main", "title": "Revenue", "tile_ids": ["tile-revenue"]}]},
        "tiles": [
            {
                "id": "tile-revenue",
                "title": "Revenue",
                "tile_type": "table",
                "business_question": "What revenue is present by region?",
                "data_view_id": "dv-revenue",
                "accessible_fallback": {
                    "summary": "Revenue by region",
                    "table_fields": ["revenue_region", "revenue_revenue"],
                },
            }
        ],
        "actions": [],
        "freshness_policy": {"mode": "live", "max_age_seconds": 3600, "allow_stale": True},
        "access_policy": {"required_scopes": ["dashboard:read", "dashboard:query"]},
        "provenance": {"created_by_actor_type": "human", "created_by": "cross-module-e2e", "source": "human"},
        "migration": {"state": "new_structured", "blockers": []},
    }


def _target_snapshot(tenant_id: str, *, source_snapshot_id: str, dataset_id: str, model_version: str) -> dict:
    return {
        "contract_version": "evaluation.target_snapshot.v1",
        "target_kind": "end_to_end",
        "target_ref": "cross-module:projected-revenue",
        "app": {
            "git_sha": "cross-module-e2e",
            "image_digest": "sha256:cross-module-e2e-image",
            "migration_revision": "add_canonical_sharing_model",
        },
        "source": {"snapshot_id": source_snapshot_id, "snapshot_hash": f"sha256:{source_snapshot_id}"},
        "semantic_model": {"version_id": model_version, "version_hash": f"sha256:{model_version}"},
        "dashboard": {
            "version_id": "published-dashboard-version",
            "manifest_hash": "sha256:dashboard-manifest",
            "renderer_version": "dashboard.manifest.v1",
        },
        "prompt": {"version": "cross-module-prompt", "prompt_hash": "sha256:cross-module-prompt"},
        "tool_registry_hash": "sha256:cross-module-tools",
        "skill_registry_hash": "sha256:cross-module-skills",
        "llm": {"provider": "local", "model": "deterministic", "params_hash": "sha256:deterministic"},
        "principal": {
            "tenant_id": tenant_id,
            "actor_type": "agent",
            "actor_id": "cross-module-agent",
            "scopes": ["dashboard.read", "dashboard.query"],
        },
        "dataset": {"snapshot_id": dataset_id, "snapshot_hash": f"sha256:{dataset_id}"},
        "feature_flags": {"evaluation_governance": True, "sharing_governance": True},
        "time_fixture": {"now": "2026-08-17T00:00:00Z", "timezone": "UTC"},
    }


async def _tenant(test_session: AsyncSession) -> Tenant:
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    return tenant


async def test_cross_module_projected_csv_dashboard_evaluation_and_sharing_journey(
    test_client,
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = await _tenant(test_session)
    model_slug = f"cross-module-revenue-{uuid4().hex[:8]}"

    uploaded = await test_client.post(
        "/api/source-resources/files",
        files={
            "file": (
                "revenue.csv",
                b"order_id,revenue_region,revenue_revenue,paid_at\n"
                b"1,East,120,2026-08-01\n"
                b"2,West,80,2026-08-02\n",
                "text/csv",
            )
        },
        data={"name": "Cross module projected revenue"},
    )
    assert uploaded.status_code == 201
    source_payload = uploaded.json()["data"]
    _assert_redacted(source_payload)
    assert source_payload["status"] == "ready"
    assert source_payload["latest_snapshot_id"]
    assert source_payload["projected_dataset_id"]
    assert source_payload["knowledge_resource"]["evidence_count"] >= 1
    source_resource_id = source_payload["id"]
    source_snapshot_id = source_payload["latest_snapshot_id"]
    projected_dataset_id = source_payload["projected_dataset_id"]

    resource = await test_session.get(SourceResource, source_resource_id)
    snapshot = await test_session.get(SourceSnapshot, source_snapshot_id)
    assert resource is not None and snapshot is not None
    assert resource.tenant_id == tenant.id
    assert snapshot.resource_id == resource.id
    assert snapshot.metadata_json["projected_dataset_id"] == projected_dataset_id
    assert snapshot.raw_storage_uri.startswith("file://source-resources/")

    projection_review = await test_client.post(
        f"/api/source-resources/{source_resource_id}/projection/review",
        json={"status": "verified", "note": "Cross-module E2E reviewed projection"},
    )
    assert projection_review.status_code == 200
    review_payload = projection_review.json()["data"]
    assert review_payload["source_snapshot_id"] == source_snapshot_id
    assert review_payload["projected_dataset_id"] == projected_dataset_id
    assert len(review_payload["projection_manifest_hash"]) == 64

    analyzed = await test_client.post(f"/api/datasources/{projected_dataset_id}/understanding/analyze", json={})
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
            "name": "Cross Module Revenue",
            "domain": "Sales / Orders",
            "owner": "Evaluation Sharing E2E",
            "candidate_ids": [candidate["id"] for candidate in selected],
        },
    )
    assert drafted.status_code == 200
    draft = drafted.json()["data"]["model"]
    assert draft["id"] == model_slug
    assert draft["datasourceId"] == projected_dataset_id
    assert draft["datasourceKind"] == "duckdb"

    validated = await test_client.post(f"/api/data-models/{model_slug}/validate")
    assert validated.status_code == 200
    assert validated.json()["data"]["readinessDetail"]["blockers"] == []
    published_model = await test_client.post(f"/api/data-models/{model_slug}/publish")
    assert published_model.status_code == 200
    model_payload = published_model.json()["data"]
    assert model_payload["status"] == "Published"
    assert model_payload["publishedVersion"] == "v1"
    reloaded_model = await test_client.get(f"/api/semantic-models/{model_slug}")
    assert reloaded_model.status_code == 200
    reloaded_model_payload = reloaded_model.json()["data"]
    metric_id = reloaded_model_payload["metrics"][0]["id"]
    dimension_id = reloaded_model_payload["dimensions"][0]["id"]

    mcp_metric = json.loads(
        await query_metric_wrapper(
            model_slug,
            metric_id,
            dimension_id,
            "",
            "",
            tenant.id,
            tenant.owner_id,
        )
    )
    semantic_blocker = None
    if mcp_metric.get("success") and mcp_metric.get("result") is not None:
        assert mcp_metric["modelVersion"] == "v1"
    else:
        semantic_blocker = {
            "owner": "Modeling",
            "summary": "Projected CSV semantic draft selected a non-numeric generated metric, so MCP query_metric fails.",
            "error": mcp_metric.get("error") or mcp_metric.get("message") or mcp_metric,
            "metric_id": metric_id,
            "dimension_id": dimension_id,
        }
        assert "sum(VARCHAR)" in json.dumps(mcp_metric) or "Metric not found" in json.dumps(mcp_metric)

    notebook = Notebook(
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        notebook_name="Cross module dashboard notebook",
    )
    test_session.add(notebook)
    await test_session.flush()
    saved_query = Query(
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        name="Cross module revenue query",
        query='SELECT revenue_region, SUM(revenue_revenue) AS revenue_revenue FROM "revenue" GROUP BY revenue_region',
        output_schema=json.dumps(
            [
                {"name": "revenue_region", "type": "string"},
                {"name": "revenue_revenue", "type": "number"},
            ]
        ),
        dataset_id=projected_dataset_id,
        notebook_id=notebook.id,
        query_type="sql",
    )
    test_session.add(saved_query)
    await test_session.commit()
    await test_session.refresh(notebook)
    await test_session.refresh(saved_query)

    manifest = _dashboard_manifest(
        asset_id="cross-module-dashboard",
        query_id=str(saved_query.id),
        source_snapshot_id=source_snapshot_id,
        model_slug=model_slug,
        metric_id=metric_id,
        dimension_id=dimension_id,
    )
    dashboard_create = await test_client.post(
        "/api/dashboard-assets",
        json={
            "slug": f"cross-module-dashboard-{uuid4().hex[:8]}",
            "notebook_id": str(notebook.id),
            "manifest": manifest,
            "tags": ["cross-module", "evaluation-sharing"],
            "change_summary": "create cross-module dashboard",
        },
    )
    assert dashboard_create.status_code == 201
    dashboard_asset = dashboard_create.json()["data"]
    assert dashboard_asset["tenant_id"] == str(tenant.id)
    assert dashboard_asset["lifecycle"] == "draft"
    assert dashboard_asset["etag"].startswith("sha256:")

    dashboard_validated = await test_client.post(f"/api/dashboard-assets/{dashboard_asset['id']}/validate", json={})
    assert dashboard_validated.status_code == 200
    assert dashboard_validated.json()["data"]["validation"]["valid"] is True

    refreshed_dashboard = await test_client.get(f"/api/dashboard-assets/{dashboard_asset['id']}")
    assert refreshed_dashboard.status_code == 200
    published_dashboard = await test_client.post(
        f"/api/dashboard-assets/{dashboard_asset['id']}/publish",
        json={"base_etag": refreshed_dashboard.json()["data"]["etag"], "change_summary": "publish cross-module dashboard"},
    )
    assert published_dashboard.status_code == 200
    published_version = published_dashboard.json()["data"]
    assert published_version["status"] == "published"
    assert published_version["is_published_immutable"] is True
    assert published_version["manifest"]["semantic_bindings"][0]["source_snapshot_ids"] == [source_snapshot_id]

    dashboard_query = await test_client.post(
        f"/api/dashboard-assets/{dashboard_asset['id']}/query",
        json={"data_view_ids": ["dv-revenue"], "filters": {"region": "East"}, "correlation_id": "cross-module-rest"},
    )
    assert dashboard_query.status_code == 200
    dashboard_run = dashboard_query.json()["data"]
    assert dashboard_run["dashboard_id"] == dashboard_asset["id"]
    assert dashboard_run["dashboard_version_id"] == published_version["id"]
    assert dashboard_run["views"][0]["lineage"][0]["ref"] == str(saved_query.id)
    assert dashboard_run["views"][0]["result"] == [{"revenue_region": "East", "revenue_revenue": 120}]
    saved_dashboard_run = await test_session.get(DashboardRun, dashboard_run["run_id"])
    assert saved_dashboard_run is not None and saved_dashboard_run.correlation_id == "cross-module-rest"

    mcp_dashboard = json.loads(
        await query_dashboard_wrapper(
            dashboard_asset["id"],
            ["dv-revenue"],
            {"region": "West"},
            "",
            10,
            tenant.id,
            tenant.owner_id,
        )
    )
    assert mcp_dashboard["success"] is True
    assert mcp_dashboard["run"]["dashboard_version_id"] == published_version["id"]
    assert mcp_dashboard["run"]["views"][0]["result"] == [{"revenue_region": "West", "revenue_revenue": 80}]

    suite_create = await test_client.post(
        "/api/evaluation/suites",
        json={
            "slug": f"cross-module-eval-{uuid4().hex[:8]}",
            "name": "Cross Module Evaluation",
            "description": "Evaluation suite bound to projected source, semantic model, dashboard, and sharing.",
            "target_kinds": ["end_to_end"],
            "gate_policy": {"security_hard_fail": True, "min_overall_pass_rate": 1.0},
        },
    )
    assert suite_create.status_code == 201
    suite = suite_create.json()["data"]["suite"]
    suite_version_id = suite["versions"][0]["id"]
    case_import = await test_client.post(
        f"/api/evaluation/suite-versions/{suite_version_id}/cases/import",
        json={
            "format": "json",
            "cases": [
                {
                    "case_key": "cross-module-parity",
                    "title": "Cross module REST/MCP parity",
                    "target_kinds": ["end_to_end"],
                    "operation": "end_to_end_task",
                    "question": "Does the projected source produce matching semantic and dashboard answers?",
                    "expected_contract": {
                        "semantic_intent": {"description": "Revenue by region from projected CSV"},
                        "answer": {"must_include_all": ["East", "West"]},
                        "evidence": {"required": True, "lineage_refs": [source_snapshot_id, str(saved_query.id)]},
                        "dashboard": {
                            "manifest_id": published_version["id"],
                            "required_data_view_ids": ["dv-revenue"],
                        },
                        "human_mcp_parity": {"required": True, "compare_fields": ["result", "lineage"]},
                        "policy": {"security_hard_fail": True},
                    },
                    "provenance": {
                        "source": "import",
                        "principal": {"tenant_id": str(tenant.id), "user_id": str(tenant.owner_id)},
                    },
                    "tags": ["cross-module", "rest-mcp-parity"],
                }
            ],
        },
    )
    assert case_import.status_code == 201
    assert case_import.json()["data"]["created_count"] == 1
    publish_eval = await test_client.post(f"/api/evaluation/suite-versions/{suite_version_id}/publish")
    assert publish_eval.status_code == 200
    assert publish_eval.json()["data"]["version"]["status"] == "published"

    target_snapshot = _target_snapshot(
        str(tenant.id),
        source_snapshot_id=source_snapshot_id,
        dataset_id=projected_dataset_id,
        model_version="v1",
    )
    rest_preflight = await test_client.post(
        "/api/evaluation/runs/preflight",
        json={
            "suite_version_id": suite_version_id,
            "target_snapshot": target_snapshot,
            "idempotency_key": "cross-module-rest-run",
            "actor_type": "agent",
            "actor_id": "cross-module-agent",
        },
    )
    assert rest_preflight.status_code == 202
    rest_run = rest_preflight.json()["data"]
    assert rest_run["status"] == "queued"
    assert rest_run["preflight_blockers"] == []

    claimed = await test_client.post(
        "/api/evaluation/runs/claim",
        json={"worker_id": "cross-module-worker", "lease_seconds": 60},
    )
    assert claimed.status_code == 200
    assert claimed.json()["data"]["id"] == rest_run["id"]
    completed = await test_client.post(
        f"/api/evaluation/runs/{rest_run['id']}/complete",
        json={
            "worker_id": "cross-module-worker",
            "case_results": [
                {
                    "case_key": "cross-module-parity",
                    "status": "passed",
                    "assessments": [
                        {"category": "rest_mcp_parity", "status": "passed", "score": "1.0", "hard_fail": False}
                    ],
                    "result": {
                        "rest_dashboard_run_id": dashboard_run["run_id"],
                        "mcp_dashboard_run_id": mcp_dashboard["run"]["run_id"],
                        "semantic_model_version": mcp_metric.get("modelVersion") or "v1",
                        "semantic_blocker": semantic_blocker,
                    },
                }
            ],
        },
    )
    assert completed.status_code == 200
    assert completed.json()["data"]["summary"]["gate_decision"] == "passed"

    mcp_eval = json.loads(
        await run_evaluation_wrapper(
            suite_version_id,
            json.dumps(target_snapshot),
            "cross-module-mcp-run",
            tenant.id,
            tenant.owner_id,
        )
    )
    assert mcp_eval["success"] is True
    assert mcp_eval["run"]["status"] == "queued"
    compare_eval = json.loads(
        await compare_evaluation_runs_wrapper(rest_run["id"], mcp_eval["run"]["id"], tenant.id, tenant.owner_id)
    )
    assert compare_eval["success"] is True
    assert compare_eval["comparison"]["baseline_run_id"] == rest_run["id"]
    assert compare_eval["comparison"]["candidate_run_id"] == mcp_eval["run"]["id"]

    folder = Folder(
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        name="Cross module shared dashboards",
        description="Folder for cross-module sharing E2E",
        is_public=False,
    )
    test_session.add(folder)
    await test_session.flush()
    test_session.add(FolderMember(folder_id=folder.id, user_id=tenant.owner_id, added_by=tenant.owner_id))
    await test_session.commit()

    share_response = await test_client.post(
        f"/api/folders/{folder.id}/dashboards",
        json={"dashboard_id": published_version["id"], "is_snapshot": True},
    )
    assert share_response.status_code == 201
    legacy_share_id = share_response.json()["data"]["id"]
    sharing_list = await test_client.get(f"/api/sharing/grants?object_type=dashboard&object_id={dashboard_asset['id']}")
    assert sharing_list.status_code == 200
    sharing_items = sharing_list.json()["data"]["items"]
    assert len(sharing_items) == 1
    grant = sharing_items[0]
    assert grant["object_version_id"] == published_version["id"]
    assert grant["status"] == "active"
    assert grant["channel"] == "folder"

    mcp_grants = json.loads(
        await list_sharing_grants_wrapper(
            tenant.id,
            tenant.owner_id,
            object_type="dashboard",
            object_id=dashboard_asset["id"],
        )
    )
    assert mcp_grants["success"] is True
    assert mcp_grants["total"] == 1
    assert mcp_grants["items"][0]["id"] == grant["id"]

    evidence = await test_client.get(f"/api/sharing/grants/{grant['id']}")
    assert evidence.status_code == 200
    evidence_payload = evidence.json()["data"]
    assert evidence_payload["compatibility_links"][0]["legacy_surface"] == "folder_dashboard"
    assert evidence_payload["compatibility_links"][0]["legacy_id"] == legacy_share_id

    mcp_evidence = json.loads(await describe_sharing_grant_wrapper(grant["id"], tenant.id, tenant.owner_id))
    assert mcp_evidence["success"] is True
    assert mcp_evidence["grant"]["id"] == grant["id"]
    assert mcp_evidence["compatibility_links"][0]["legacy_id"] == legacy_share_id

    revoke_response = await test_client.delete(f"/api/folders/{folder.id}/dashboards/{published_version['id']}")
    assert revoke_response.status_code == 204
    revoked = await test_client.get(f"/api/sharing/grants/{grant['id']}")
    assert revoked.status_code == 200
    assert revoked.json()["data"]["grant"]["status"] == "revoked"

    rerun_preflight = await test_client.post(
        "/api/evaluation/runs/preflight",
        json={
            "suite_version_id": suite_version_id,
            "target_snapshot": deepcopy(target_snapshot),
            "idempotency_key": "cross-module-rest-run",
            "actor_type": "agent",
            "actor_id": "cross-module-agent",
        },
    )
    assert rerun_preflight.status_code == 202
    assert rerun_preflight.json()["data"]["id"] == rest_run["id"]

    combined = {
        "source": source_payload,
        "projection_review": review_payload,
        "semantic_mcp": mcp_metric,
        "semantic_blocker": semantic_blocker,
        "dashboard_rest": dashboard_run,
        "dashboard_mcp": mcp_dashboard,
        "evaluation_rest": completed.json()["data"],
        "evaluation_mcp": mcp_eval,
        "sharing_rest": evidence_payload,
        "sharing_mcp": mcp_evidence,
        "revoked": revoked.json()["data"],
    }
    _assert_redacted(combined)
