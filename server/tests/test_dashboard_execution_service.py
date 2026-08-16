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
from server.schemas.query import QueryFilter as SavedQueryFilter
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


def _semantic_metric_manifest_payload(access_policy: dict | None = None) -> dict:
    return {
        "schema_version": "dashboard.manifest.v1",
        "dashboard_id": "dash-semantic-metric",
        "title": "Semantic metric dashboard",
        "description": "Manifest-first semantic metric dashboard",
        "audience": ["finance"],
        "semantic_bindings": [
            {
                "id": "sales-model",
                "model_slug": "sales-semantic",
                "model_version": "v3",
                "source_snapshot_ids": ["snapshot-1"],
                "allowed_metrics": ["paid_revenue"],
                "allowed_dimensions": ["order_status"],
            }
        ],
        "data_views": [
            {
                "id": "dv-paid-revenue",
                "kind": "semantic_metric",
                "question": "What paid revenue is recognized by order status?",
                "output_schema": [
                    {"name": "order_status", "data_type": "string"},
                    {"name": "paid_revenue", "data_type": "number", "unit": "USD"},
                ],
                "filter_fields": ["region"],
                "row_limit": 2,
                "semantic_metric": {
                    "semantic_binding_id": "sales-model",
                    "metric": "paid_revenue",
                    "dimensions": ["order_status"],
                    "grain": "month",
                },
            }
        ],
        "filters": [
            {
                "id": "region",
                "label": "Region",
                "source": "semantic_field",
                "field": "region",
                "filter_type": "enum",
                "operators": ["eq"],
                "affected_data_view_ids": ["dv-paid-revenue"],
            }
        ],
        "layout": {"sections": [{"id": "main", "tile_ids": ["tile-paid-revenue"]}]},
        "tiles": [
            {
                "id": "tile-paid-revenue",
                "title": "Paid revenue",
                "tile_type": "bar",
                "business_question": "What paid revenue is recognized?",
                "data_view_id": "dv-paid-revenue",
            }
        ],
        "actions": [],
        "freshness_policy": {"mode": "live", "max_age_seconds": 3600, "allow_stale": True},
        "access_policy": access_policy or {"required_scopes": ["dashboard:read", "dashboard:query"]},
        "provenance": {"created_by_actor_type": "human", "created_by": "user-1", "source": "human"},
        "migration": {"state": "new_structured", "blockers": []},
    }


def _context_search_manifest_payload(source_binding_id: str, access_policy: dict | None = None) -> dict:
    return {
        "schema_version": "dashboard.manifest.v1",
        "dashboard_id": "dash-context-search",
        "title": "Context search dashboard",
        "description": "Evidence-backed context dashboard",
        "audience": ["finance"],
        "semantic_bindings": [
            {
                "id": "context-source",
                "model_slug": "policy-context",
                "model_version": "v1",
                "source_snapshot_ids": ["snapshot-ctx"],
                "allowed_metrics": [],
                "allowed_dimensions": [],
            }
        ],
        "data_views": [
            {
                "id": "dv-policy-evidence",
                "kind": "context_search",
                "question": "Which evidence defines paid revenue?",
                "output_schema": [
                    {"name": "evidence_id", "data_type": "string"},
                    {"name": "text", "data_type": "string"},
                    {"name": "snapshot_id", "data_type": "string"},
                ],
                "filter_fields": ["topic"],
                "row_limit": 5,
                "context_search": {
                    "source_binding_id": source_binding_id,
                    "query_template": "definition for {topic}",
                    "evidence_required": True,
                },
            }
        ],
        "filters": [
            {
                "id": "topic",
                "label": "Topic",
                "source": "semantic_field",
                "field": "topic",
                "filter_type": "string",
                "operators": ["eq"],
                "affected_data_view_ids": ["dv-policy-evidence"],
            }
        ],
        "layout": {"sections": [{"id": "main", "tile_ids": ["tile-policy-evidence"]}]},
        "tiles": [
            {
                "id": "tile-policy-evidence",
                "title": "Policy evidence",
                "tile_type": "evidence",
                "business_question": "Where is the definition evidenced?",
                "data_view_id": "dv-policy-evidence",
            }
        ],
        "actions": [],
        "freshness_policy": {"mode": "live", "max_age_seconds": 3600, "allow_stale": True},
        "access_policy": access_policy or {"required_scopes": ["dashboard:read", "dashboard:query"]},
        "provenance": {"created_by_actor_type": "human", "created_by": "user-1", "source": "human"},
        "migration": {"state": "new_structured", "blockers": []},
    }


async def _seed_published_dashboard(
    test_session: AsyncSession,
    manifest_payload: dict,
    *,
    slug_suffix: str,
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
        slug=f"exec-{slug_suffix}",
        manifest_payload=manifest_payload,
    )
    published = await service.publish(
        session=test_session,
        tenant_id=tenant_id,
        asset_id=asset.id,
        actor_id=user_id,
        base_etag=asset.etag,
        change_summary="publish dashboard",
    )
    return {"tenant_id": tenant_id, "user_id": user_id, "asset_id": asset.id, "version_id": published.id}


async def _seed_published_saved_query_dashboard(
    test_session: AsyncSession,
    query_id: str,
    access_policy: dict | None = None,
) -> dict[str, UUID]:
    return await _seed_published_dashboard(
        test_session,
        _manifest_payload(query_id, access_policy=access_policy),
        slug_suffix=query_id,
    )


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
async def test_query_dashboard_marks_saved_query_view_stale_from_view_freshness_policy(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_id = str(uuid4())
    payload = _manifest_payload(query_id)
    payload["data_views"][0]["freshness_policy"] = {
        "mode": "live",
        "max_age_seconds": 1,
        "allow_stale": True,
        "require_as_of": True,
    }
    ids = await _seed_published_dashboard(test_session, payload, slug_suffix=f"stale-{query_id}")

    async def fake_execute_saved_query(session, query_id_arg, filters=None, viewer_user_id=None):
        return {
            "success": True,
            "data": [{"revenue": 42}],
            "query_name": "Revenue query",
            "query_id": query_id_arg,
            "cached": True,
            "stale": False,
            "as_of": "2020-01-01T00:00:00",
        }

    monkeypatch.setattr("server.services.dashboard.QueryService.execute_saved_query", fake_execute_saved_query)

    run = await DashboardService().query_dashboard(
        session=test_session,
        tenant_id=ids["tenant_id"],
        asset_id=ids["asset_id"],
        actor_id=str(ids["user_id"]),
        actor_type="human",
        data_view_ids=["dv-saved-revenue"],
    )

    assert run["overall_freshness"] == "stale"
    assert run["views"][0]["status"] == "stale"
    assert run["views"][0]["stale"] is True
    assert run["views"][0]["as_of"] == "2020-01-01T00:00:00"


@pytest.mark.asyncio
async def test_query_dashboard_executes_manifest_bound_semantic_metric(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = await _seed_published_dashboard(
        test_session,
        _semantic_metric_manifest_payload(),
        slug_suffix=f"semantic-{uuid4()}",
    )
    captured: dict[str, object] = {}

    async def fake_run_query_metric(session, tenant_id, slug, request, user_id):
        captured["tenant_id"] = tenant_id
        captured["slug"] = slug
        captured["request"] = request
        captured["user_id"] = user_id
        return {
            "resolvedMetric": "Paid Revenue",
            "modelVersion": "v3",
            "status": "completed",
            "result": [
                {"order_status": "PAID", "paid_revenue": 120},
                {"order_status": "REFUNDED", "paid_revenue": 5},
                {"order_status": "PENDING", "paid_revenue": 3},
            ],
            "returnedCount": 3,
            "totalCount": 3,
            "limited": False,
            "lineage": [{"id": "paid_revenue", "kind": "metric", "name": "Paid Revenue", "ref": "sales.paid_revenue"}],
            "freshness": "2026-08-16T12:00:00",
            "policyDecision": "allowed",
            "warnings": [],
        }

    monkeypatch.setattr("server.services.dashboard.SemanticModelService.run_query_metric", fake_run_query_metric)

    run = await DashboardService().query_dashboard(
        session=test_session,
        tenant_id=ids["tenant_id"],
        asset_id=ids["asset_id"],
        actor_id=str(ids["user_id"]),
        actor_type="agent",
        filters={"region": "AMER"},
        data_view_ids=["dv-paid-revenue"],
        correlation_id="semantic-metric",
    )

    assert captured["tenant_id"] == ids["tenant_id"]
    assert captured["slug"] == "sales-semantic"
    assert captured["user_id"] == ids["user_id"]
    assert captured["request"] == {
        "metric": "paid_revenue",
        "dimension": "order_status",
        "grain": "month",
        "limit": 2,
        "timeout": 30,
        "filters": {"region": "AMER"},
    }
    assert run["overall_freshness"] == "fresh"
    assert run["views"][0]["data_view_id"] == "dv-paid-revenue"
    assert run["views"][0]["status"] == "success"
    assert run["views"][0]["result"] == [
        {"order_status": "PAID", "paid_revenue": 120},
        {"order_status": "REFUNDED", "paid_revenue": 5},
    ]
    assert run["views"][0]["pagination"]["has_more"] is True
    assert "row limit" in run["views"][0]["warnings"][0]
    assert run["views"][0]["evidence"][0]["locator"]["model_version"] == "v3"
    assert any(item["kind"] == "semantic_model" for item in run["views"][0]["lineage"])
    assert any(item["kind"] == "source_snapshot" and item["ref"] == "snapshot-1" for item in run["views"][0]["lineage"])


@pytest.mark.asyncio
async def test_query_dashboard_blocks_semantic_metric_outside_manifest_allowlist(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _semantic_metric_manifest_payload()
    payload["data_views"][0]["semantic_metric"]["metric"] = "gross_margin"
    ids = await _seed_published_dashboard(test_session, payload, slug_suffix=f"semantic-denied-{uuid4()}")
    executed = False

    async def fake_run_query_metric(*_args, **_kwargs):
        nonlocal executed
        executed = True
        return {"status": "completed", "result": []}

    monkeypatch.setattr("server.services.dashboard.SemanticModelService.run_query_metric", fake_run_query_metric)

    run = await DashboardService().query_dashboard(
        session=test_session,
        tenant_id=ids["tenant_id"],
        asset_id=ids["asset_id"],
        actor_id=str(ids["user_id"]),
        actor_type="agent",
        data_view_ids=["dv-paid-revenue"],
    )

    assert executed is False
    assert run["overall_freshness"] == "blocked"
    assert run["views"][0]["status"] == "permission_denied"
    assert run["views"][0]["error"]["code"] == "semantic_binding_not_allowed"
    assert "metric_not_allowlisted" in run["views"][0]["error"]["policy_reason"]


@pytest.mark.asyncio
async def test_query_dashboard_executes_context_search_with_evidence(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_id = uuid4()
    evidence_id = uuid4()
    snapshot_id = uuid4()
    ids = await _seed_published_dashboard(
        test_session,
        _context_search_manifest_payload(str(resource_id)),
        slug_suffix=f"context-{uuid4()}",
    )
    captured: dict[str, object] = {}

    async def fake_search_knowledge(self, *, session, tenant_id, query, resource_ids, limit):
        captured["tenant_id"] = tenant_id
        captured["query"] = query
        captured["resource_ids"] = resource_ids
        captured["limit"] = limit
        return [
            {
                "id": evidence_id,
                "knowledge_resource_id": uuid4(),
                "snapshot_id": snapshot_id,
                "fragment_type": "document_section",
                "title_path": ["Finance", "Revenue"],
                "text": "Paid revenue is net paid order amount.",
                "locator_json": {"document_token": "docx_1", "block_id": "blk_paid_revenue"},
                "confidence": "0.91",
                "content_hash": "hash",
            }
        ]

    monkeypatch.setattr("server.services.dashboard.SourceResourceService.search_knowledge", fake_search_knowledge)

    run = await DashboardService().query_dashboard(
        session=test_session,
        tenant_id=ids["tenant_id"],
        asset_id=ids["asset_id"],
        actor_id=str(ids["user_id"]),
        actor_type="human",
        filters={"topic": "paid revenue"},
        data_view_ids=["dv-policy-evidence"],
        correlation_id="context-search",
    )

    assert captured["tenant_id"] == ids["tenant_id"]
    assert captured["query"] == "definition for paid revenue"
    assert captured["resource_ids"] == [resource_id]
    assert captured["limit"] == 5
    assert run["overall_freshness"] == "fresh"
    assert run["views"][0]["status"] == "success"
    assert run["views"][0]["result"] == [
        {
            "evidence_id": str(evidence_id),
            "text": "Paid revenue is net paid order amount.",
            "title_path": ["Finance", "Revenue"],
            "locator": {"document_token": "docx_1", "block_id": "blk_paid_revenue"},
            "snapshot_id": str(snapshot_id),
            "confidence": "0.91",
        }
    ]
    assert run["views"][0]["evidence"][0]["id"] == str(evidence_id)
    assert run["views"][0]["evidence"][0]["confidence"] == 0.91


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
async def test_query_dashboard_rejects_unknown_manifest_filter_before_execution(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_id = str(uuid4())
    ids = await _seed_published_saved_query_dashboard(test_session, query_id)
    executed = False

    async def fake_execute_saved_query(*_args, **_kwargs):
        nonlocal executed
        executed = True
        return {"success": True, "data": [{"revenue": 42}]}

    monkeypatch.setattr("server.services.dashboard.QueryService.execute_saved_query", fake_execute_saved_query)

    with pytest.raises(HTTPException) as exc:
        await DashboardService().query_dashboard(
            session=test_session,
            tenant_id=ids["tenant_id"],
            asset_id=ids["asset_id"],
            actor_id=str(ids["user_id"]),
            actor_type="agent",
            filters={"region": "AMER", "raw_sql": "select * from other_tenant.secret"},
            data_view_ids=["dv-saved-revenue"],
        )

    assert exc.value.status_code == 403
    assert "filters are not available" in str(exc.value.detail)
    assert executed is False


@pytest.mark.asyncio
async def test_query_dashboard_rejects_filter_outside_selected_data_view_before_execution(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_id = str(uuid4())
    payload = _manifest_payload(query_id)
    payload["data_views"].append(
        {
            "id": "dv-margin",
            "kind": "saved_query",
            "question": "What margin did the saved query return?",
            "output_schema": [{"name": "margin", "data_type": "number"}],
            "filter_fields": ["segment"],
            "saved_query": {
                "query_id": query_id,
                "compatibility_reason": "legacy reviewed dashboard query",
                "filter_contract": {},
            },
        }
    )
    payload["filters"].append(
        {
            "id": "segment",
            "label": "Segment",
            "source": "saved_query_contract",
            "field": "segment",
            "filter_type": "enum",
            "operators": ["eq"],
            "affected_data_view_ids": ["dv-margin"],
        }
    )
    ids = await _seed_published_dashboard(test_session, payload, slug_suffix=f"filter-scope-{uuid4()}")
    executed = False

    async def fake_execute_saved_query(*_args, **_kwargs):
        nonlocal executed
        executed = True
        return {"success": True, "data": [{"revenue": 42}]}

    monkeypatch.setattr("server.services.dashboard.QueryService.execute_saved_query", fake_execute_saved_query)

    with pytest.raises(HTTPException) as exc:
        await DashboardService().query_dashboard(
            session=test_session,
            tenant_id=ids["tenant_id"],
            asset_id=ids["asset_id"],
            actor_id=str(ids["user_id"]),
            actor_type="agent",
            filters={"segment": "enterprise"},
            data_view_ids=["dv-saved-revenue"],
        )

    assert exc.value.status_code == 403
    assert executed is False


@pytest.mark.asyncio
async def test_query_dashboard_rejects_filter_not_declared_by_data_view_before_execution(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_id = str(uuid4())
    payload = _manifest_payload(query_id)
    payload["filters"].append(
        {
            "id": "country",
            "label": "Country",
            "source": "saved_query_contract",
            "field": "country",
            "filter_type": "enum",
            "operators": ["eq"],
            "affected_data_view_ids": ["dv-saved-revenue"],
        }
    )
    ids = await _seed_published_dashboard(test_session, payload, slug_suffix=f"filter-field-scope-{uuid4()}")
    executed = False

    async def fake_execute_saved_query(*_args, **_kwargs):
        nonlocal executed
        executed = True
        return {"success": True, "data": [{"revenue": 42}]}

    monkeypatch.setattr("server.services.dashboard.QueryService.execute_saved_query", fake_execute_saved_query)

    with pytest.raises(HTTPException) as exc:
        await DashboardService().query_dashboard(
            session=test_session,
            tenant_id=ids["tenant_id"],
            asset_id=ids["asset_id"],
            actor_id=str(ids["user_id"]),
            actor_type="agent",
            filters={"country": "US"},
            data_view_ids=["dv-saved-revenue"],
        )

    assert exc.value.status_code == 403
    assert "filters are not available" in str(exc.value.detail)
    assert executed is False


@pytest.mark.asyncio
async def test_query_dashboard_normalizes_filter_id_to_manifest_field(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_id = str(uuid4())
    payload = _manifest_payload(query_id)
    payload["filters"][0]["id"] = "region-filter"
    ids = await _seed_published_dashboard(test_session, payload, slug_suffix=f"filter-id-field-{uuid4()}")
    captured: dict[str, object] = {}

    async def fake_execute_saved_query(session, query_id_arg, filters=None, viewer_user_id=None):
        captured["filters"] = filters
        return {
            "success": True,
            "data": [{"revenue": 42}],
            "query_name": "Revenue query",
            "query_id": query_id_arg,
        }

    monkeypatch.setattr("server.services.dashboard.QueryService.execute_saved_query", fake_execute_saved_query)

    run = await DashboardService().query_dashboard(
        session=test_session,
        tenant_id=ids["tenant_id"],
        asset_id=ids["asset_id"],
        actor_id=str(ids["user_id"]),
        actor_type="agent",
        filters={"region-filter": "AMER"},
        data_view_ids=["dv-saved-revenue"],
    )

    assert run["normalized_filters"] == {"region": "AMER"}
    assert captured["filters"] == [SavedQueryFilter(field="region", operator="eq", value="AMER")]


@pytest.mark.asyncio
async def test_query_dashboard_rejects_required_filter_missing_before_execution(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_id = str(uuid4())
    payload = _manifest_payload(query_id)
    payload["filters"][0]["required"] = True
    ids = await _seed_published_dashboard(test_session, payload, slug_suffix=f"filter-required-{uuid4()}")
    executed = False

    async def fake_execute_saved_query(*_args, **_kwargs):
        nonlocal executed
        executed = True
        return {"success": True, "data": [{"revenue": 42}]}

    monkeypatch.setattr("server.services.dashboard.QueryService.execute_saved_query", fake_execute_saved_query)

    with pytest.raises(HTTPException) as exc:
        await DashboardService().query_dashboard(
            session=test_session,
            tenant_id=ids["tenant_id"],
            asset_id=ids["asset_id"],
            actor_id=str(ids["user_id"]),
            actor_type="agent",
            filters={},
            data_view_ids=["dv-saved-revenue"],
        )

    assert exc.value.status_code == 403
    assert "required dashboard filters" in str(exc.value.detail)
    assert executed is False


@pytest.mark.asyncio
async def test_query_dashboard_rejects_filter_value_outside_manifest_domain_before_execution(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_id = str(uuid4())
    payload = _manifest_payload(query_id)
    payload["filters"][0]["domain"] = ["AMER", "EMEA"]
    ids = await _seed_published_dashboard(test_session, payload, slug_suffix=f"filter-domain-{uuid4()}")
    executed = False

    async def fake_execute_saved_query(*_args, **_kwargs):
        nonlocal executed
        executed = True
        return {"success": True, "data": [{"revenue": 42}]}

    monkeypatch.setattr("server.services.dashboard.QueryService.execute_saved_query", fake_execute_saved_query)

    with pytest.raises(HTTPException) as exc:
        await DashboardService().query_dashboard(
            session=test_session,
            tenant_id=ids["tenant_id"],
            asset_id=ids["asset_id"],
            actor_id=str(ids["user_id"]),
            actor_type="agent",
            filters={"region": "APAC"},
            data_view_ids=["dv-saved-revenue"],
        )

    assert exc.value.status_code == 403
    assert "invalid values" in str(exc.value.detail)
    assert executed is False


@pytest.mark.asyncio
async def test_query_dashboard_rejects_conflicting_filter_id_and_field_values_before_execution(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query_id = str(uuid4())
    payload = _manifest_payload(query_id)
    payload["filters"][0]["id"] = "region-filter"
    ids = await _seed_published_dashboard(test_session, payload, slug_suffix=f"filter-conflict-{uuid4()}")
    executed = False

    async def fake_execute_saved_query(*_args, **_kwargs):
        nonlocal executed
        executed = True
        return {"success": True, "data": [{"revenue": 42}]}

    monkeypatch.setattr("server.services.dashboard.QueryService.execute_saved_query", fake_execute_saved_query)

    with pytest.raises(HTTPException) as exc:
        await DashboardService().query_dashboard(
            session=test_session,
            tenant_id=ids["tenant_id"],
            asset_id=ids["asset_id"],
            actor_id=str(ids["user_id"]),
            actor_type="agent",
            filters={"region-filter": "AMER", "region": "EMEA"},
            data_view_ids=["dv-saved-revenue"],
        )

    assert exc.value.status_code == 403
    assert "invalid values" in str(exc.value.detail)
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
