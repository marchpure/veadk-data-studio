from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.db.session import AsyncSessionFactory  # noqa: E402
from server.models.dashboard import DashboardAsset  # noqa: E402
from server.models.datasets import Dataset  # noqa: E402
from server.models.files import File  # noqa: E402
from server.models.notebooks import Notebook  # noqa: E402
from server.models.semantic_models import (  # noqa: E402
    SemanticModel,
    SemanticModelDimension,
    SemanticModelEntity,
    SemanticModelField,
    SemanticModelMetric,
    SemanticModelRelationship,
)
from server.models.source_resources import SourceResource  # noqa: E402
from server.models.source_snapshots import SourceSnapshot  # noqa: E402
from server.scripts.knowledge_center_live_seed import (  # noqa: E402
    _api,
    _ensure_external_key,
    _external,
    _jsonable,
    _login_team_owner,
    _team_database_identity,
)
from server.services.dashboard import DashboardService  # noqa: E402
from server.services.file_operations import DataFrameFileService  # noqa: E402
from server.services.semantic_model_service import SemanticModelService  # noqa: E402
from server.utils.config_loader import is_self_hosted  # noqa: E402


SNAPSHOT_ROOT = Path(
    os.getenv(
        "ORACLE_SNAPSHOT_DIR",
        "/Users/bytedance/oracle_sanitized_snapshots/"
        "oracle-local-extract-sanitized/20260818-knowledge-center-4-arkclaw",
    )
)
MANIFEST_PATH = SNAPSHOT_ROOT / "upload_manifest_v2.json"
DUCKDB_PATH = SNAPSHOT_ROOT / "local_oracle_sales_sanitized.duckdb"
DUCKDB_GZ_PATH = SNAPSHOT_ROOT / "local_oracle_sales_sanitized.duckdb.gz"
METADATA_TAR_PATH = SNAPSHOT_ROOT / "oracle_local_extract_sanitized_metadata_only.tar.gz"

EXPECTED_DUCKDB_GZ_SHA256 = "932500bb99ee9fd68d185e5e281f64004171cb34c4f90ddad355d53302531352"
EXPECTED_DUCKDB_SHA256 = "c67a52d9f8d2eaf92d6a7ca1b09aee321cf4da176499c618ef0e53214eb166eb"
EXPECTED_METADATA_TAR_SHA256 = "1d27d127c2c3e4fb76ac4199913aedeb799ec9a6a893c45761ff63e8a86cbf64"

ORACLE_SCHEMA = "dnyxlstest"
SELL_FILTER = (
    "hd.CANCELSIGN = 'N' AND hd.STATUS = '002' AND "
    "hd.SELLSTATEID IN ('01','02') AND "
    "hd.SELLDATE >= DATE '2026-07-17' AND hd.SELLDATE <= DATE '2026-08-15'"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_snapshot_manifest() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "oracle.sales.snapshot.manifest.v2":
        raise RuntimeError(f"Unexpected Oracle manifest schema: {manifest.get('schema_version')}")
    checks = {
        DUCKDB_GZ_PATH: EXPECTED_DUCKDB_GZ_SHA256,
        DUCKDB_PATH: EXPECTED_DUCKDB_SHA256,
        METADATA_TAR_PATH: EXPECTED_METADATA_TAR_SHA256,
    }
    for path, expected in checks.items():
        actual = _sha256(path)
        if actual != expected:
            raise RuntimeError(f"Hash mismatch for {path}: expected {expected}, got {actual}")
    if manifest.get("uncompressed_duckdb", {}).get("sha256") != EXPECTED_DUCKDB_SHA256:
        raise RuntimeError("Manifest uncompressed DuckDB hash does not match the release gate contract")
    return manifest


def _snapshot_contract(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": manifest["prefix"],
        "snapshot_id": manifest["prefix"],
        "hash": EXPECTED_DUCKDB_SHA256,
        "sha256": EXPECTED_DUCKDB_SHA256,
        "data_through": manifest["data_through"],
        "manifest_schema": manifest["schema_version"],
        "provenance": manifest["provenance"],
    }


def _dashboard_manifest(*, dashboard_id: str, model: SemanticModel, manifest: dict[str, Any]) -> dict[str, Any]:
    snapshot_id = manifest["prefix"]
    return {
        "schema_version": "dashboard.manifest.v1",
        "dashboard_id": dashboard_id,
        "title": "Oracle Dashboard",
        "description": "Governed Oracle sanitized DuckDB dashboard.",
        "audience": ["Knowledge Center", "AgentKit Studio"],
        "semantic_bindings": [
            {
                "id": "oracle-sales-model",
                "model_slug": model.slug,
                "model_version": model.published_version,
                "source_snapshot_ids": [snapshot_id],
                "allowed_metrics": ["ticket_count"],
                "allowed_dimensions": ["store", "sell_date"],
                "readiness": "published",
            }
        ],
        "data_views": [
            {
                "id": "oracle-store-top-3",
                "kind": "semantic_metric",
                "question": "Oracle Store Top 3 by ticket count through 2026-08-15.",
                "output_schema": [
                    {"name": "store", "data_type": "string", "sensitivity": "internal"},
                    {"name": "ticket_count", "data_type": "integer", "unit": "ticket", "sensitivity": "internal"},
                ],
                "row_limit": 3,
                "semantic_metric": {
                    "semantic_binding_id": "oracle-sales-model",
                    "metric": "ticket_count",
                    "dimensions": ["store"],
                    "sort": [{"field": "ticket_count", "direction": "desc"}],
                },
                "lineage": [
                    {
                        "id": "oracle-snapshot",
                        "kind": "source_snapshot",
                        "name": "Oracle sanitized DuckDB snapshot",
                        "ref": snapshot_id,
                        "version": "v2",
                    }
                ],
            },
            {
                "id": "oracle-ticket-count",
                "kind": "semantic_metric",
                "question": "Current ticket count for the snapshot window.",
                "output_schema": [{"name": "ticket_count", "data_type": "integer", "unit": "ticket"}],
                "semantic_metric": {"semantic_binding_id": "oracle-sales-model", "metric": "ticket_count"},
            },
            {
                "id": "oracle-snapshot-freshness",
                "kind": "semantic_metric",
                "question": "Snapshot freshness / max SELLDATE.",
                "output_schema": [{"name": "sell_date", "data_type": "date"}],
                "semantic_metric": {"semantic_binding_id": "oracle-sales-model", "metric": "ticket_count", "dimensions": ["sell_date"]},
            },
            {
                "id": "oracle-policy-notice",
                "kind": "semantic_metric",
                "question": "Policy notice: customer contact denied.",
                "output_schema": [{"name": "policy_decision", "data_type": "string"}],
                "semantic_metric": {"semantic_binding_id": "oracle-sales-model", "metric": "ticket_count"},
            },
        ],
        "filters": [
            {
                "id": "sell_date",
                "label": "SELLDATE",
                "source": "semantic_field",
                "field": "sell_date",
                "filter_type": "date_range",
                "operators": ["between"],
                "affected_data_view_ids": [
                    "oracle-store-top-3",
                    "oracle-ticket-count",
                    "oracle-snapshot-freshness",
                ],
                "default_value": ["2026-07-17", "2026-08-15"],
            }
        ],
        "layout": {
            "sections": [
                {
                    "id": "oracle-overview",
                    "title": "Oracle Snapshot",
                    "tile_ids": [
                        "tile-top-3",
                        "tile-ticket-count",
                        "tile-freshness",
                        "tile-policy",
                    ],
                }
            ]
        },
        "tiles": [
            {
                "id": "tile-top-3",
                "title": "Oracle Store Top 3",
                "tile_type": "bar",
                "business_question": "Which stores have the highest ticket count?",
                "data_view_id": "oracle-store-top-3",
            },
            {
                "id": "tile-ticket-count",
                "title": "Ticket Count",
                "tile_type": "kpi",
                "business_question": "What is the current ticket count?",
                "data_view_id": "oracle-ticket-count",
            },
            {
                "id": "tile-freshness",
                "title": "Snapshot Freshness / max SELLDATE",
                "tile_type": "status",
                "business_question": "What is the max SELLDATE?",
                "data_view_id": "oracle-snapshot-freshness",
            },
            {
                "id": "tile-policy",
                "title": "Policy Notice / customer contact denied",
                "tile_type": "evidence",
                "business_question": "Can customer contact details be exposed?",
                "data_view_id": "oracle-policy-notice",
            },
        ],
        "actions": [],
        "freshness_policy": {"mode": "pinned_snapshot", "max_age_seconds": 0, "allow_stale": True, "require_as_of": True},
        "access_policy": {
            "required_scopes": ["dashboard:read", "dashboard:query"],
            "column_policy_refs": ["oracle.sales.privacy.v1"],
            "redaction_policy_refs": ["direct_customer_identifiers", "contact_fields", "document_numbers"],
        },
        "provenance": {
            "created_by_actor_type": "service",
            "created_by": "knowledge-center-oracle-live-seed",
            "source": "import",
            "evidence_refs": [snapshot_id, "metadata/privacy_report.json", "metadata/validation_report.json"],
        },
        "migration": {"state": "new_structured", "blockers": []},
    }


async def _create_oracle_workspace_assets(
    *,
    tenant_id: str,
    user_id: str,
    run_id: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    tenant_uuid = UUID(tenant_id)
    user_uuid = UUID(user_id)
    snapshot = _snapshot_contract(manifest)
    now = datetime.utcnow()
    async with AsyncSessionFactory() as session:
        notebook = Notebook(
            id=uuid4(),
            tenant_id=tenant_uuid,
            created_by=user_uuid,
            notebook_name=f"Oracle Knowledge Center {run_id}",
        )
        dataset = Dataset(
            id=uuid4(),
            tenant_id=tenant_uuid,
            created_by=user_uuid,
            type="file",
            name=f"Oracle Sanitized DuckDB {run_id}",
            description="Oracle sanitized DuckDB snapshot for Knowledge Center release gate.",
            storage_path=str(SNAPSHOT_ROOT),
            duckdb_path=str(DUCKDB_PATH),
            is_public=True,
            schema_cache=json.dumps(
                {
                    "datasource_type": "duckdb",
                    "datasource_name": "Oracle Sanitized DuckDB",
                    "schema": json.loads((SNAPSHOT_ROOT / "metadata/schema_catalog.json").read_text(encoding="utf-8")),
                    "snapshot": snapshot,
                },
                ensure_ascii=False,
            ),
            schema_updated_at=now,
        )
        session.add_all([notebook, dataset])
        await session.flush()

        file_record = File(
            tenant_id=tenant_uuid,
            name="local_oracle_sales_sanitized.duckdb",
            type="duckdb",
            size=DUCKDB_PATH.stat().st_size,
            dataset_id=dataset.id,
            storage_path=str(DUCKDB_PATH),
            checksum=EXPECTED_DUCKDB_SHA256,
        )
        source = SourceResource(
            tenant_id=tenant_uuid,
            resource_type="file",
            name=f"Oracle sanitized DuckDB {run_id}",
            external_id=manifest["prefix"],
            source_url=str(DUCKDB_PATH),
            owner_id=user_uuid,
            visibility="workspace",
            sync_mode="manual",
            sync_config_json={
                "projected_dataset_id": str(dataset.id),
                "projected_dataset": {
                    "dataset_id": str(dataset.id),
                    "status": "ready",
                    "file_types": ["duckdb"],
                    "source_snapshot_id": manifest["prefix"],
                },
                "manifest": {
                    "prefix": manifest["prefix"],
                    "schema_version": manifest["schema_version"],
                    "duckdb_sha256": EXPECTED_DUCKDB_SHA256,
                },
            },
            status="ready",
        )
        session.add_all([file_record, source])
        await session.flush()

        source_snapshot = SourceSnapshot(
            tenant_id=tenant_uuid,
            resource_id=source.id,
            external_revision="sha256:" + EXPECTED_DUCKDB_SHA256,
            content_hash=EXPECTED_DUCKDB_SHA256,
            raw_storage_uri=str(DUCKDB_PATH),
            captured_at=now,
            parser_version="oracle.sales.snapshot.manifest.v2",
            metadata_json={
                "projected_dataset_id": str(dataset.id),
                "manifest": manifest,
                "snapshot": snapshot,
                "privacy_report": "metadata/privacy_report.json",
                "validation_report": "metadata/validation_report.json",
            },
            status="parsed",
        )
        session.add(source_snapshot)
        await session.flush()
        source.latest_snapshot_id = source_snapshot.id

        model_slug = f"oracle-sales-{run_id}-{uuid4().hex[:8]}"
        model = SemanticModel(
            tenant_id=tenant_uuid,
            created_by=user_uuid,
            slug=model_slug,
            name=f"Oracle Sales Semantic Model {run_id}",
            domain="Oracle Sales / Tickets",
            owner="Knowledge Center Release Gate",
            datasource_id=str(dataset.id),
            datasource_name=dataset.name or "Oracle Sanitized DuckDB",
            datasource_kind="duckdb",
            description="Governed Oracle semantic model over sanitized DuckDB snapshot.",
            status="Draft",
            draft_revision="draft-oracle-1",
            readiness=95,
            readiness_level="ready",
            consumers_json=json.dumps({"agents": 1, "mcp": 1, "dashboards": 1}, ensure_ascii=False),
            review_json=json.dumps(
                {
                    "sourceUnderstandingLineage": [
                        {
                            "source_snapshot_id": manifest["prefix"],
                            "source_resource_id": str(source.id),
                            "dataset_id": str(dataset.id),
                            "sha256": EXPECTED_DUCKDB_SHA256,
                            "data_through": manifest["data_through"],
                            "provenance": manifest["provenance"],
                        }
                    ],
                    "snapshot": snapshot,
                    "validationSummary": {"status": "passed", "validatedAt": now.isoformat(), "blockers": []},
                },
                ensure_ascii=False,
            ),
            mcp_json=json.dumps(
                {
                    "rawSqlFallback": False,
                    "allowedMetrics": ["ticket_count"],
                    "allowedDimensions": ["store", "sell_date", "sell_state", "sell_type"],
                    "policy": {
                        "deniedFields": ["direct_customer_identifiers", "contact_fields", "document_numbers"],
                        "customerContactRequests": "denied",
                        "crossCountrySalesAmount": "blocked_pending_currency_confirmation",
                    },
                    "snapshot": snapshot,
                },
                ensure_ascii=False,
            ),
            validation_log_json=json.dumps(["Oracle sanitized snapshot gate validated."], ensure_ascii=False),
        )
        session.add(model)
        await session.flush()

        hd_entity = SemanticModelEntity(
            model_id=model.id,
            slug="hd",
            name="P_BL_SELL_HD",
            business_name="Sales Header",
            table_name="P_BL_SELL_HD",
            primary_key="BILLID",
            entity_type="fact",
            profile_json=json.dumps({"schema": ORACLE_SCHEMA}, ensure_ascii=False),
            lineage_json=json.dumps([snapshot], ensure_ascii=False),
            permission_json=json.dumps({"read_only": True}, ensure_ascii=False),
            sort_order=0,
        )
        store_entity = SemanticModelEntity(
            model_id=model.id,
            slug="store",
            name="P_ARC_STORE",
            business_name="Store",
            table_name="P_ARC_STORE",
            primary_key="STOREID",
            entity_type="dimension",
            profile_json=json.dumps({"schema": ORACLE_SCHEMA}, ensure_ascii=False),
            lineage_json=json.dumps([snapshot], ensure_ascii=False),
            permission_json=json.dumps({"read_only": True}, ensure_ascii=False),
            sort_order=1,
        )
        session.add_all([hd_entity, store_entity])
        await session.flush()
        for entity, fields in (
            (
                hd_entity,
                [
                    ("BILLID", "BILLID", "varchar", "primary_key"),
                    ("STOREID", "STOREID", "varchar", "foreign_key"),
                    ("SELLDATE", "SELLDATE", "timestamp", "time"),
                    ("SELLSTATEID", "SELLSTATEID", "varchar", "attribute"),
                    ("SELLTYPECODE", "SELLTYPECODE", "varchar", "attribute"),
                    ("CANCELSIGN", "CANCELSIGN", "varchar", "policy_filter"),
                    ("STATUS", "STATUS", "varchar", "policy_filter"),
                    ("ACCOUNT_SALES", "ACCOUNT_SALES", "decimal", "blocked_metric"),
                ],
            ),
            (
                store_entity,
                [
                    ("STOREID", "STOREID", "varchar", "primary_key"),
                    ("STORENAME", "STORENAME", "varchar", "attribute"),
                    ("COUNTRY", "COUNTRY", "varchar", "blocked_currency_dimension"),
                ],
            ),
        ):
            for index, (name, source_field, data_type, role) in enumerate(fields):
                session.add(
                    SemanticModelField(
                        entity_id=entity.id,
                        name=name,
                        source_field=source_field,
                        data_type=data_type,
                        role=role,
                        nullable=True,
                        sort_order=index,
                    )
                )

        session.add(
            SemanticModelRelationship(
                model_id=model.id,
                slug="hd_store",
                from_entity="hd",
                to_entity="store",
                label="Sales header store",
                join_fields_json=json.dumps([{"from": "hd.STOREID", "to": "store.STOREID"}]),
                cardinality="many_to_one",
                fk_evidence="Oracle sanitized snapshot header to store join.",
                unique_rate=1.0,
                orphan_rate=0.0,
                fanout_risk="low",
                validation_status="valid",
                status="confirmed",
                evidence_json=json.dumps([snapshot], ensure_ascii=False),
                sort_order=0,
            )
        )
        session.add_all(
            [
                SemanticModelDimension(
                    model_id=model.id,
                    slug="store",
                    name="Store",
                    entity_slug="store",
                    field="STORENAME",
                    description="Sanitized store display name.",
                    sort_order=0,
                ),
                SemanticModelDimension(
                    model_id=model.id,
                    slug="sell_date",
                    name="SELLDATE",
                    entity_slug="hd",
                    field="SELLDATE",
                    description="Ticket sell date; max SELLDATE anchors snapshot freshness.",
                    sort_order=1,
                ),
                SemanticModelDimension(
                    model_id=model.id,
                    slug="sell_state",
                    name="Sell State",
                    entity_slug="hd",
                    field="SELLSTATEID",
                    description="Allowed states for posted tickets.",
                    sort_order=2,
                ),
                SemanticModelDimension(
                    model_id=model.id,
                    slug="sell_type",
                    name="Sell Type",
                    entity_slug="hd",
                    field="SELLTYPECODE",
                    description="Oracle sell type code.",
                    sort_order=3,
                ),
            ]
        )
        metric_lineage = [
            snapshot,
            {
                "policy": "oracle.sales.privacy.v1",
                "filters": {
                    "CANCELSIGN": "N",
                    "STATUS": "002",
                    "SELLSTATEID": ["01", "02"],
                    "SELLDATE": ["2026-07-17", "2026-08-15"],
                },
                "golden_results": manifest["golden_results"],
            },
        ]
        session.add(
            SemanticModelMetric(
                model_id=model.id,
                slug="ticket_count",
                name="ticket_count",
                business_name="Ticket Count",
                definition="Count of distinct sales bill IDs for posted, non-cancelled tickets in the 2026-07-17 through 2026-08-15 snapshot window.",
                kind="measure",
                formula="count(distinct hd.BILLID)",
                filter_expr=SELL_FILTER,
                time_field="hd.SELLDATE",
                default_grain="day",
                dimensions_json=json.dumps(["store", "sell_date", "sell_state", "sell_type"], ensure_ascii=False),
                unit="ticket",
                owner="Knowledge Center Release Gate",
                certification="approved",
                lineage_json=json.dumps(metric_lineage, ensure_ascii=False),
                preview_json=json.dumps({"expected": manifest["golden_results"]}, ensure_ascii=False),
                compiled_sql="",
                validation_status="valid",
                sort_order=0,
            )
        )
        await session.flush()
        await SemanticModelService.validate_model(session, tenant_uuid, model.slug, user_uuid)
        published_payload = await SemanticModelService.publish_model(session, tenant_uuid, model.slug, user_uuid)
        model = await session.scalar(select(SemanticModel).where(SemanticModel.id == model.id))
        if model is None:
            raise RuntimeError("Oracle semantic model disappeared during publish")

        dashboard_slug = f"oracle-dashboard-{run_id}-{uuid4().hex[:8]}"
        dashboard = await DashboardService().create_asset_draft(
            session=session,
            tenant_id=tenant_uuid,
            actor_id=user_uuid,
            notebook_id=notebook.id,
            slug=dashboard_slug,
            manifest_payload=_dashboard_manifest(dashboard_id=dashboard_slug, model=model, manifest=manifest),
            description="Oracle Dashboard for sanitized DuckDB release gate.",
            tags=["oracle", "knowledge-center", "sanitized"],
            change_summary="Create Oracle release gate dashboard",
            actor_type="service",
        )
        await DashboardService().publish(
            session=session,
            tenant_id=tenant_uuid,
            asset_id=dashboard.id,
            actor_id=user_uuid,
            base_etag=dashboard.etag,
            change_summary="Publish Oracle release gate dashboard",
            actor_type="service",
        )
        await session.refresh(dashboard)
        return {
            "notebookId": str(notebook.id),
            "datasetId": str(dataset.id),
            "sourceResourceId": str(source.id),
            "sourceSnapshotId": str(source_snapshot.id),
            "semanticModelSlug": model.slug,
            "semanticModelExternalAssetId": str(model.id),
            "semanticModelPublishedVersion": model.published_version,
            "dashboardAssetId": str(dashboard.id),
            "dashboardSlug": dashboard.slug,
            "dashboardUrl": f"/dashboard-assets/{dashboard.id}",
            "publishedPayload": _jsonable(published_payload),
        }


def _assert_gold(name: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise RuntimeError(f"{name} mismatch: expected {expected!r}, got {actual!r}")


async def main() -> None:
    base_url = os.getenv("BYAAN_BASE_URL", "http://127.0.0.1:18000").rstrip("/")
    out_dir = Path(
        os.getenv(
            "REPORT_DIR",
            ROOT / "artifacts/data-modeling/knowledge-center/session-reports/live",
        )
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = os.getenv("RUN_ID") or f"oracle-{int(time.time())}"
    secret_env_path = Path(os.getenv("SECRET_ENV_PATH", f"/tmp/{run_id}.byaan-live-env.sh"))
    manifest = _load_snapshot_manifest()

    async with httpx.AsyncClient(base_url=base_url, timeout=120.0) as client:
        config = await _api(client, "GET", "/api/app/config", headers={})
        app_features = config.get("features") or {}
        if not is_self_hosted():
            raise RuntimeError("Oracle Knowledge Center gate requires self-hosted Team mode")
        master_email = os.getenv("MASTER_USER_EMAIL", "")
        master_password = os.getenv("MASTER_USER_PASSWORD", "")
        if not master_email or not master_password:
            raise RuntimeError("MASTER_USER_EMAIL and MASTER_USER_PASSWORD are required for Team Oracle live seed")
        if not app_features.get("enterprise_licensed") or not app_features.get("team_sharing_enabled"):
            raise RuntimeError(f"Team app config flags are disabled: {config}")
        if config.get("local_bootstrap") or config.get("community_bootstrap"):
            raise RuntimeError(f"Team app config exposed local/community bootstrap: {config}")
        login = await _login_team_owner(
            client,
            email=master_email,
            password=master_password,
            preferred_tenant_name=config.get("org_name"),
        )
        db_identity = await _team_database_identity(master_email)
        tenant_id = login["tenantId"]
        user_id = login["userId"]
        api_key = await _ensure_external_key(tenant_id, user_id, run_id)
        assets = await _create_oracle_workspace_assets(
            tenant_id=tenant_id,
            user_id=user_id,
            run_id=run_id,
            manifest=manifest,
        )
        semantic_asset = await _external(
            client,
            "GET",
            f"/api/external/assets/semantic_model/{assets['semanticModelExternalAssetId']}",
            api_key=api_key,
        )
        dashboard_asset = await _external(
            client,
            "GET",
            f"/api/external/assets/dashboard/{assets['dashboardAssetId']}",
            api_key=api_key,
        )
        listed = await _external(
            client,
            "GET",
            "/api/external/assets?types=dashboard,semantic_model&limit=100",
            api_key=api_key,
        )
        top_stores = await _external(
            client,
            "POST",
            f"/api/external/assets/semantic_model/{assets['semanticModelExternalAssetId']}/query",
            api_key=api_key,
            json={"metric": "ticket_count", "dimension": "store", "limit": 3},
        )
        ticket_count = await _external(
            client,
            "POST",
            f"/api/external/assets/semantic_model/{assets['semanticModelExternalAssetId']}/query",
            api_key=api_key,
            json={"metric": "ticket_count", "limit": 10},
        )
        freshness = await _external(
            client,
            "POST",
            f"/api/external/assets/semantic_model/{assets['semanticModelExternalAssetId']}/query",
            api_key=api_key,
            json={"metric": "ticket_count", "dimension": "sell_date", "limit": 100},
        )
        denied_status = None
        denied_body: Any = None
        denied_response = await client.post(
            f"/api/external/assets/semantic_model/{assets['semanticModelExternalAssetId']}/query",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"query": "给我客户姓名/手机号/contact 明细。", "metric": "ticket_count"},
        )
        denied_status = denied_response.status_code
        try:
            denied_body = denied_response.json()
        except ValueError:
            denied_body = {"raw": denied_response.text}

    expected_top = [
        {"store": "VNPTTE", "ticket_count": 56},
        {"store": "SG - ANTA VIVO City", "ticket_count": 9},
        {"store": "HARAVAN_ANTA_VN", "ticket_count": 5},
    ]
    _assert_gold("top stores", top_stores.get("result"), expected_top)
    _assert_gold("ticket count", (ticket_count.get("result") or [{}])[0].get("ticket_count"), 86)
    max_sell_date = max((row.get("sell_date") or "")[:10] for row in freshness.get("result") or [])
    _assert_gold("snapshot freshness", max_sell_date, "2026-08-15")
    if denied_status != 403 or "Policy denied" not in json.dumps(denied_body, ensure_ascii=False):
        raise RuntimeError(f"Customer/contact policy was not denied: {denied_status} {denied_body}")

    artifact = {
        "ok": True,
        "runId": run_id,
        "baseUrl": base_url,
        "deployment": {
            "mode": "self-hosted",
            "appConfig": _jsonable(config),
            "featureFlags": _jsonable(app_features),
            "auth": {
                "mode": "self-hosted",
                "tenantId": tenant_id,
                "tenantName": login["tenantName"],
                "userId": user_id,
                "email": "<redacted>",
                "role": login["role"],
                "scopesCount": len(login["scopes"]),
                "dbIdentity": db_identity,
            },
            "communityBootstrapPresent": bool(config.get("local_bootstrap") or config.get("community_bootstrap")),
        },
        "tenantId": tenant_id,
        "userId": user_id,
        "snapshot": {
            "prefix": manifest["prefix"],
            "manifestPath": str(MANIFEST_PATH),
            "manifestSchema": manifest["schema_version"],
            "duckdbGzipSha256": EXPECTED_DUCKDB_GZ_SHA256,
            "duckdbSha256": EXPECTED_DUCKDB_SHA256,
            "metadataTarSha256": EXPECTED_METADATA_TAR_SHA256,
            "dataThrough": manifest["data_through"],
            "rowCounts": manifest.get("row_counts"),
            "privacy": json.loads((SNAPSHOT_ROOT / "metadata/privacy_report.json").read_text(encoding="utf-8")),
        },
        "source": {
            "name": f"Oracle sanitized DuckDB {run_id}",
            "resourceId": assets["sourceResourceId"],
            "sourceSnapshotId": assets["sourceSnapshotId"],
            "projectedDatasetId": assets["datasetId"],
            "duckdbPath": str(DUCKDB_PATH),
        },
        "model": {
            "slug": assets["semanticModelSlug"],
            "name": semantic_asset["name"],
            "externalAssetId": assets["semanticModelExternalAssetId"],
            "publishedVersion": assets["semanticModelPublishedVersion"],
        },
        "dashboard": {
            "assetId": assets["dashboardAssetId"],
            "slug": assets["dashboardSlug"],
            "url": f"{base_url}{assets['dashboardUrl']}",
            "queryUrl": dashboard_asset.get("query_url"),
            "name": dashboard_asset.get("name"),
        },
        "externalApi": {
            "apiKeyEnv": "BYAAN_MCP_API_KEY",
            "apiKey": "<redacted>",
            "asset": _jsonable(semantic_asset),
            "dashboardAsset": _jsonable(dashboard_asset),
            "listCount": len(listed.get("items") or listed.get("assets") or []),
            "queries": {
                "topStores": _jsonable(top_stores),
                "ticketCount": _jsonable(ticket_count),
                "freshness": _jsonable(freshness),
                "customerContactDenied": {"status": denied_status, "body": _jsonable(denied_body)},
                "crossCountrySalesAmount": {
                    "status": "blocked_pending_currency_confirmation",
                    "reason": manifest["golden_results"]["cross_country_sales_amount"],
                },
            },
        },
        "gold": {
            "topStores": expected_top,
            "ticketCount": 86,
            "snapshotFreshness": "2026-08-15",
            "customerContactPolicy": "denied",
            "crossCountrySalesAmount": "blocked_pending_currency_confirmation",
        },
        "secretEnvPath": str(secret_env_path),
    }
    result_path = out_dir / "byaan-oracle-live-seed-result.json"
    result_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    legacy_result_path = out_dir / "byaan-live-seed-result.json"
    shutil.copyfile(result_path, legacy_result_path)
    secret_env_path.parent.mkdir(parents=True, exist_ok=True)
    secret_env_path.write_text(
        "\n".join(
            [
                f"export BYAAN_BASE_URL={json.dumps(base_url)}",
                f"export DATASTUDIO_BASE_URL={json.dumps(base_url)}",
                f"export BYAAN_MCP_API_KEY={json.dumps(api_key)}",
                f"export DATASTUDIO_API_KEY={json.dumps(api_key)}",
                f"export DATASTUDIO_ASSET_ID={json.dumps(assets['semanticModelExternalAssetId'])}",
                'export DATASTUDIO_ASSET_TYPE="semantic_model"',
                f"export DATASTUDIO_QUERY_URL={json.dumps(semantic_asset['query_url'])}",
                f"export ORACLE_DASHBOARD_URL={json.dumps(artifact['dashboard']['url'])}",
                f"export ORACLE_DASHBOARD_ASSET_ID={json.dumps(assets['dashboardAssetId'])}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    secret_env_path.chmod(0o600)
    print(json.dumps(artifact, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
