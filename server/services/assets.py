from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from server.models.dashboard import Dashboard, DashboardAsset, DashboardAuditEvent
from server.models.datasets import Dataset
from server.models.knowledge_resources import EvidenceFragment, KnowledgeResource
from server.models.notebook_assets import NotebookAsset
from server.models.semantic_models import SemanticModel
from server.models.source_resources import SourceResource
from server.models.source_snapshots import SourceSnapshot


class AssetService:
    async def search_assets(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        notebook_id: UUID | None,
        query: str = "",
        asset_types: list[str] | None = None,
        publish_states: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        allowed_types = set(asset_types or ("dataset", "semantic_model", "knowledge_resource", "dashboard"))
        usage_by_key: dict[tuple[str, str], dict[str, Any]] = {}

        if notebook_id is not None:
            result = await session.execute(
                select(NotebookAsset).where(
                    NotebookAsset.tenant_id == tenant_id,
                    NotebookAsset.notebook_id == notebook_id,
                    NotebookAsset.asset_type.in_(tuple(allowed_types)),
                )
            )
            notebook_assets = list(result.scalars().all())
            usage_by_key = {(item.asset_type, item.asset_id): item.usage_policy_json or {} for item in notebook_assets}
            asset_keys = list(usage_by_key)
        else:
            asset_keys = [(asset_type, "") for asset_type in allowed_types]

        items: list[dict[str, Any]] = []
        if "dataset" in allowed_types:
            dataset_ids = [asset_id for asset_type, asset_id in asset_keys if asset_type == "dataset"]
            items.extend(
                await self._list_dataset_assets(
                    session=session,
                    tenant_id=tenant_id,
                    dataset_ids=dataset_ids,
                    include_all=notebook_id is None,
                    usage_by_key=usage_by_key,
                )
            )
        if "semantic_model" in allowed_types:
            semantic_ids = [asset_id for asset_type, asset_id in asset_keys if asset_type == "semantic_model"]
            items.extend(
                await self._list_semantic_model_assets(
                    session=session,
                    tenant_id=tenant_id,
                    model_ids=semantic_ids,
                    include_all=notebook_id is None,
                    usage_by_key=usage_by_key,
                )
            )
        if "knowledge_resource" in allowed_types:
            knowledge_ids = [asset_id for asset_type, asset_id in asset_keys if asset_type == "knowledge_resource"]
            items.extend(
                await self._list_knowledge_assets(
                    session=session,
                    tenant_id=tenant_id,
                    knowledge_ids=knowledge_ids,
                    include_all=notebook_id is None,
                    usage_by_key=usage_by_key,
                    include_samples=True,
                )
            )
        if "dashboard" in allowed_types:
            dashboard_ids = [asset_id for asset_type, asset_id in asset_keys if asset_type == "dashboard"]
            items.extend(
                await self._list_dashboard_assets(
                    session=session,
                    tenant_id=tenant_id,
                    dashboard_ids=dashboard_ids,
                    include_all=notebook_id is None,
                    usage_by_key=usage_by_key,
                    include_samples=True,
                )
            )

        filtered = [item for item in items if self._matches_query(item, query)]
        filtered = self._filter_publish_states(filtered, publish_states or [])
        filtered.sort(key=lambda item: (item["asset_type"], item["name"]))
        return filtered[:limit]

    async def describe_asset(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        asset_type: str,
        asset_id: str,
    ) -> dict[str, Any] | None:
        if asset_type == "dataset":
            items = await self._list_dataset_assets(
                session=session,
                tenant_id=tenant_id,
                dataset_ids=[asset_id],
                include_all=False,
                usage_by_key={},
            )
        elif asset_type == "semantic_model":
            items = await self._list_semantic_model_assets(
                session=session,
                tenant_id=tenant_id,
                model_ids=[asset_id],
                include_all=False,
                usage_by_key={},
            )
        elif asset_type == "knowledge_resource":
            items = await self._list_knowledge_assets(
                session=session,
                tenant_id=tenant_id,
                knowledge_ids=[asset_id],
                include_all=False,
                usage_by_key={},
                include_samples=True,
            )
        elif asset_type == "dashboard":
            items = await self._list_dashboard_assets(
                session=session,
                tenant_id=tenant_id,
                dashboard_ids=[asset_id],
                include_all=False,
                usage_by_key={},
                include_samples=True,
            )
        else:
            return None
        return items[0] if items else None

    async def _list_dataset_assets(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        dataset_ids: list[str],
        include_all: bool,
        usage_by_key: dict[tuple[str, str], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        stmt = (
            select(Dataset)
            .where(Dataset.tenant_id == tenant_id)
            .options(selectinload(Dataset.files), selectinload(Dataset.connection))
        )
        if not include_all:
            parsed_ids = [parsed for value in dataset_ids if (parsed := self._parse_uuid(value)) is not None]
            if not parsed_ids:
                return []
            stmt = stmt.where(Dataset.id.in_(parsed_ids))
        result = await session.execute(stmt)
        return [
            self._dataset_payload(dataset, usage_by_key.get(("dataset", str(dataset.id)), {}))
            for dataset in result.scalars().all()
        ]

    async def _list_semantic_model_assets(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        model_ids: list[str],
        include_all: bool,
        usage_by_key: dict[tuple[str, str], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        stmt = (
            select(SemanticModel)
            .where(SemanticModel.tenant_id == tenant_id)
            .options(selectinload(SemanticModel.metrics), selectinload(SemanticModel.dimensions))
        )
        if not include_all:
            clauses = []
            parsed_ids = [parsed for value in model_ids if (parsed := self._parse_uuid(value)) is not None]
            if parsed_ids:
                clauses.append(SemanticModel.id.in_(parsed_ids))
            slugs = [value for value in model_ids if value]
            if slugs:
                clauses.append(SemanticModel.slug.in_(slugs))
            if not clauses:
                return []
            from sqlalchemy import or_

            stmt = stmt.where(or_(*clauses))
        result = await session.execute(stmt)
        return [
            self._semantic_model_payload(
                model,
                usage_by_key.get(("semantic_model", str(model.id)), {})
                or usage_by_key.get(("semantic_model", model.slug), {}),
            )
            for model in result.scalars().all()
        ]

    async def _list_knowledge_assets(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        knowledge_ids: list[str],
        include_all: bool,
        usage_by_key: dict[tuple[str, str], dict[str, Any]],
        include_samples: bool = False,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(KnowledgeResource, SourceResource, SourceSnapshot)
            .join(SourceResource, SourceResource.id == KnowledgeResource.resource_id)
            .join(SourceSnapshot, SourceSnapshot.id == KnowledgeResource.snapshot_id)
            .where(KnowledgeResource.tenant_id == tenant_id)
        )
        if not include_all:
            parsed_ids = [parsed for value in knowledge_ids if (parsed := self._parse_uuid(value)) is not None]
            if not parsed_ids:
                return []
            stmt = stmt.where(KnowledgeResource.id.in_(parsed_ids))
        result = await session.execute(stmt)
        rows = list(result.all())
        items = []
        for knowledge, resource, snapshot in rows:
            samples = []
            if include_samples:
                samples = await self._sample_evidence(
                    session=session, tenant_id=tenant_id, knowledge_resource_id=knowledge.id
                )
            items.append(
                self._knowledge_payload(
                    knowledge=knowledge,
                    resource=resource,
                    snapshot=snapshot,
                    usage_policy=usage_by_key.get(("knowledge_resource", str(knowledge.id)), {}),
                    sample_evidence=samples,
                )
            )
        return items

    async def _list_dashboard_assets(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        dashboard_ids: list[str],
        include_all: bool,
        usage_by_key: dict[tuple[str, str], dict[str, Any]],
        include_samples: bool = False,
    ) -> list[dict[str, Any]]:
        stmt = select(DashboardAsset).where(DashboardAsset.tenant_id == tenant_id)
        if not include_all:
            parsed_ids = [parsed for value in dashboard_ids if (parsed := self._parse_uuid(value)) is not None]
            slugs = [value for value in dashboard_ids if value]
            clauses = []
            if parsed_ids:
                clauses.append(DashboardAsset.id.in_(parsed_ids))
            if slugs:
                clauses.append(DashboardAsset.slug.in_(slugs))
            if not clauses:
                return []
            from sqlalchemy import or_

            stmt = stmt.where(or_(*clauses))
        result = await session.execute(stmt)
        assets = list(result.scalars().all())
        if not assets:
            return []

        version_ids = [
            version_id
            for asset in assets
            for version_id in (asset.published_version_id, asset.current_draft_version_id)
            if version_id
        ]
        versions_by_id: dict[UUID, Dashboard] = {}
        if version_ids:
            versions_result = await session.execute(
                select(Dashboard).where(Dashboard.tenant_id == tenant_id, Dashboard.id.in_(version_ids))
            )
            versions_by_id = {version.id: version for version in versions_result.scalars().all()}

        recent_cases_by_asset: dict[UUID, list[dict[str, Any]]] = {}
        if include_samples:
            asset_ids = [asset.id for asset in assets]
            audit_result = await session.execute(
                select(DashboardAuditEvent)
                .where(
                    DashboardAuditEvent.tenant_id == tenant_id,
                    DashboardAuditEvent.asset_id.in_(asset_ids),
                )
                .order_by(DashboardAuditEvent.created_at.desc(), DashboardAuditEvent.id.desc())
            )
            for event in audit_result.scalars().all():
                if len(recent_cases_by_asset.get(event.asset_id, [])) >= 3:
                    continue
                recent_cases_by_asset.setdefault(event.asset_id, []).append(self._dashboard_case_payload(event))

        return [
            self._dashboard_payload(
                asset=asset,
                published=versions_by_id.get(asset.published_version_id) if asset.published_version_id else None,
                draft=versions_by_id.get(asset.current_draft_version_id) if asset.current_draft_version_id else None,
                usage_policy=usage_by_key.get(("dashboard", str(asset.id)), {})
                or usage_by_key.get(("dashboard", asset.slug), {}),
                recent_cases=recent_cases_by_asset.get(asset.id, []),
            )
            for asset in assets
        ]

    def _dataset_payload(self, dataset: Dataset, usage_policy: dict[str, Any]) -> dict[str, Any]:
        schema = self._loads_json(dataset.schema_cache)
        tables = list((schema.get("tables") or {}).keys()) if isinstance(schema, dict) else []
        file_types = sorted({file.type for file in dataset.files})
        source_snapshot_id = self._source_snapshot_from_schema(schema)
        return {
            "asset_type": "dataset",
            "asset_id": str(dataset.id),
            "name": dataset.name or "Unnamed Dataset",
            "description": dataset.description,
            "status": "ready",
            "capabilities": {
                "execution_modes": ["execute_dataset_query"],
                "query_connection_id": str(dataset.connection_id or dataset.id),
                "dataset_type": dataset.type,
                "tables": tables,
                "file_types": file_types,
            },
            "freshness": {
                "status": "current",
                "schema_updated_at": dataset.schema_updated_at.isoformat() if dataset.schema_updated_at else None,
                "source_updated_at": dataset.created_at.isoformat() if dataset.created_at else None,
            },
            "provenance": {
                "dataset_id": str(dataset.id),
                "source_snapshot_id": source_snapshot_id,
                "connection_id": str(dataset.connection_id) if dataset.connection_id else None,
                "created_by": str(dataset.created_by) if dataset.created_by else None,
            },
            "usage_policy": usage_policy,
            "sample_evidence": [],
        }

    def _semantic_model_payload(self, model: SemanticModel, usage_policy: dict[str, Any]) -> dict[str, Any]:
        publish_state = (
            "published"
            if model.published_version != "v0"
            else "blocked"
            if model.readiness_level == "blocked"
            else "draft"
        )
        blockers = [] if publish_state == "published" else self._semantic_model_blockers(model)
        total = max(1, len(model.metrics) + len(model.dimensions))
        gate = {
            "score": 100 if publish_state == "published" else max(0, min(99, int(model.readiness or 0))),
            "passed": total if publish_state == "published" else 0,
            "total": total,
            "blockers": blockers,
        }
        capabilities = {
            "execution_modes": ["run_semantic_query"],
            "slug": model.slug,
            "domain": model.domain,
            "published_version": model.published_version,
            "readiness": model.readiness,
            "readiness_level": model.readiness_level,
        }
        if publish_state != "published":
            capabilities = {}
            usage_policy = {**usage_policy, "external": False}
        return {
            "asset_type": "semantic_model",
            "asset_id": str(model.id),
            "name": model.name,
            "description": model.description,
            "status": model.status,
            "publish_state": publish_state,
            "gate": gate,
            "version": model.published_version if model.published_version != "v0" else None,
            "consumers": self._semantic_model_consumers(model),
            "capabilities": capabilities,
            "freshness": {
                "status": "current" if model.drift_alerts == 0 else "drift_detected",
                "drift_alerts": model.drift_alerts,
                "updated_at": model.updated_at.isoformat() if model.updated_at else None,
            },
            "provenance": {
                "semantic_model_id": str(model.id),
                "datasource_id": model.datasource_id,
                "datasource_kind": model.datasource_kind,
                "draft_revision": model.draft_revision,
                "published_version": model.published_version,
            },
            "usage_policy": usage_policy,
            "sample_evidence": [],
        }

    def _dashboard_payload(
        self,
        *,
        asset: DashboardAsset,
        published: Dashboard | None,
        draft: Dashboard | None,
        usage_policy: dict[str, Any],
        recent_cases: list[dict[str, Any]],
    ) -> dict[str, Any]:
        version = published or draft
        manifest = version.manifest_json if version and version.manifest_json else {}
        validation = version.validation_result_json if version and version.validation_result_json else {}
        publish_state = self._dashboard_publish_state(asset=asset, version=version, validation=validation)
        gate = self._dashboard_gate(manifest, validation, publish_state)
        can_consume = publish_state == "published" and gate["blockers"] == []
        capabilities = self._dashboard_capabilities(asset, manifest, recent_cases) if can_consume else {}
        if can_consume:
            usage_policy = {"external": True, **usage_policy}
        else:
            usage_policy = {**usage_policy, "external": False}

        return {
            "asset_type": "dashboard",
            "asset_id": str(asset.id),
            "name": asset.name,
            "description": asset.description,
            "status": asset.lifecycle,
            "publish_state": publish_state,
            "gate": gate,
            "version": f"v{version.version_num}" if version else None,
            "consumers": self._dashboard_consumers(asset),
            "capabilities": capabilities,
            "freshness": self._dashboard_freshness(asset),
            "provenance": self._dashboard_provenance(asset, version, manifest),
            "usage_policy": usage_policy,
            "sample_evidence": self._dashboard_sample_evidence(manifest, recent_cases),
        }

    def _knowledge_payload(
        self,
        *,
        knowledge: KnowledgeResource,
        resource: SourceResource,
        snapshot: SourceSnapshot,
        usage_policy: dict[str, Any],
        sample_evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "asset_type": "knowledge_resource",
            "asset_id": str(knowledge.id),
            "name": resource.name,
            "description": resource.source_url,
            "status": knowledge.index_status,
            "capabilities": {
                "execution_modes": ["search_knowledge", "read_evidence"],
                "resource_type": resource.resource_type,
                "locator_types": self._locator_types(resource.resource_type),
                "provider": knowledge.provider,
            },
            "freshness": {
                "status": self._freshness_status(resource, snapshot),
                "source_status": resource.status,
                "snapshot_id": str(snapshot.id),
                "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
                "content_hash": snapshot.content_hash,
            },
            "provenance": {
                "knowledge_resource_id": str(knowledge.id),
                "source_resource_id": str(resource.id),
                "source_resource_type": resource.resource_type,
                "source_connection_id": str(resource.source_connection_id) if resource.source_connection_id else None,
                "source_snapshot_id": str(snapshot.id),
                "source_revision": snapshot.external_revision,
                "parser_version": snapshot.parser_version,
                "source_url": resource.source_url,
            },
            "usage_policy": usage_policy,
            "sample_evidence": sample_evidence,
        }

    async def _sample_evidence(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        knowledge_resource_id: UUID,
    ) -> list[dict[str, Any]]:
        result = await session.execute(
            select(EvidenceFragment)
            .where(
                EvidenceFragment.tenant_id == tenant_id,
                EvidenceFragment.knowledge_resource_id == knowledge_resource_id,
            )
            .order_by(EvidenceFragment.created_at.asc(), EvidenceFragment.id.asc())
            .limit(3)
        )
        return [
            {
                "id": str(evidence.id),
                "fragment_type": evidence.fragment_type,
                "title_path": evidence.title_path,
                "text": evidence.text,
                "locator_json": evidence.locator_json,
                "confidence": evidence.confidence,
                "content_hash": evidence.content_hash,
            }
            for evidence in result.scalars().all()
        ]

    def _matches_query(self, item: dict[str, Any], query: str) -> bool:
        terms = [term for term in re.split(r"\s+", query.strip().lower()) if term]
        if not terms:
            return True
        haystack = json.dumps(item, ensure_ascii=False, default=str).lower()
        return any(term in haystack for term in terms)

    def _filter_publish_states(self, items: list[dict[str, Any]], publish_states: list[str]) -> list[dict[str, Any]]:
        if not publish_states:
            return items
        wanted = set(publish_states)
        return [item for item in items if item.get("publish_state", "draft") in wanted]

    def _dashboard_publish_state(
        self,
        *,
        asset: DashboardAsset,
        version: Dashboard | None,
        validation: dict[str, Any],
    ) -> str:
        if asset.lifecycle == "published" and asset.published_version_id and version and version.status == "published":
            return "published" if not validation.get("blockers") else "blocked"
        if asset.lifecycle in {"archived"}:
            return "archived"
        if asset.lifecycle in {"in_review", "validating"}:
            return "validating"
        if validation.get("blockers"):
            return "blocked"
        return "draft"

    def _dashboard_gate(
        self, manifest: dict[str, Any], validation: dict[str, Any], publish_state: str
    ) -> dict[str, Any]:
        blockers = list(validation.get("blockers") or [])
        if publish_state == "published":
            blockers = []
        checks = [
            bool(manifest.get("data_views")),
            bool(manifest.get("tiles")),
            not blockers,
        ]
        passed = sum(1 for check in checks if check)
        total = len(checks)
        score = 100 if total and passed == total and not blockers else int((passed / total) * 100) if total else 0
        return {"score": score, "passed": passed, "total": total, "blockers": blockers}

    def _dashboard_capabilities(
        self,
        asset: DashboardAsset,
        manifest: dict[str, Any],
        recent_cases: list[dict[str, Any]],
    ) -> dict[str, Any]:
        metrics, dimensions = self._dashboard_metrics_dimensions(manifest)
        return {
            "execution_modes": ["query_dashboard"],
            "slug": asset.slug,
            "metrics": metrics,
            "dimensions": dimensions,
            "default_time_field": self._dashboard_default_time_field(manifest),
            "data_views": [
                {
                    "id": data_view.get("id"),
                    "kind": data_view.get("kind"),
                    "question": data_view.get("question"),
                    "output_schema": data_view.get("output_schema") or [],
                    "filter_fields": data_view.get("filter_fields") or [],
                }
                for data_view in manifest.get("data_views") or []
            ],
            "filters": manifest.get("filters") or [],
            "access_policy": manifest.get("access_policy") or asset.access_policy_json or {},
            "recent_cases": recent_cases,
        }

    def _dashboard_metrics_dimensions(
        self, manifest: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        metrics: list[dict[str, Any]] = []
        dimensions_by_id: dict[str, dict[str, Any]] = {}
        for data_view in manifest.get("data_views") or []:
            semantic_metric = data_view.get("semantic_metric") or {}
            if metric := semantic_metric.get("metric"):
                metrics.append(
                    {
                        "id": metric,
                        "data_view_id": data_view.get("id"),
                        "question": data_view.get("question"),
                        "grain": semantic_metric.get("grain"),
                    }
                )
            for dimension in semantic_metric.get("dimensions") or []:
                dimensions_by_id.setdefault(dimension, {"id": dimension, "source": "semantic_metric"})
            for field in data_view.get("filter_fields") or []:
                dimensions_by_id.setdefault(field, {"id": field, "source": "filter_field"})
            for field in data_view.get("output_schema") or []:
                name = field.get("name")
                if not name:
                    continue
                data_type = str(field.get("data_type") or "").lower()
                if data_type in {"number", "integer", "float", "double", "decimal", "real", "numeric"}:
                    if not any(item["id"] == name for item in metrics):
                        metrics.append(
                            {
                                "id": name,
                                "data_view_id": data_view.get("id"),
                                "question": data_view.get("question"),
                                "source": "output_schema",
                                "unit": field.get("unit"),
                            }
                        )
                else:
                    dimensions_by_id.setdefault(
                        name,
                        {
                            "id": name,
                            "source": "output_schema",
                            "data_type": field.get("data_type"),
                        },
                    )
        return metrics, list(dimensions_by_id.values())

    def _dashboard_default_time_field(self, manifest: dict[str, Any]) -> str | None:
        for dashboard_filter in manifest.get("filters") or []:
            if dashboard_filter.get("filter_type") in {"date", "datetime", "date_range"}:
                return dashboard_filter.get("field")
        for data_view in manifest.get("data_views") or []:
            semantic_metric = data_view.get("semantic_metric") or {}
            if semantic_metric.get("grain"):
                return "time_range"
        return None

    def _dashboard_freshness(self, asset: DashboardAsset) -> dict[str, Any]:
        health = asset.health_summary_json or {}
        return {
            "status": health.get("freshness") or "current",
            "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
            "freshness_policy": asset.freshness_policy_json or {},
        }

    def _dashboard_provenance(
        self,
        asset: DashboardAsset,
        version: Dashboard | None,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "dashboard_asset_id": str(asset.id),
            "dashboard_slug": asset.slug,
            "notebook_id": str(asset.notebook_id) if asset.notebook_id else None,
            "version_id": str(version.id) if version else None,
            "version_num": version.version_num if version else None,
            "content_hash": version.content_hash if version else None,
            "created_by": str(asset.owner_id) if asset.owner_id else None,
            "semantic_bindings": manifest.get("semantic_bindings") or [],
            "lineage": self._dashboard_lineage_from_manifest(manifest),
        }

    def _dashboard_sample_evidence(
        self,
        manifest: dict[str, Any],
        recent_cases: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for data_view in manifest.get("data_views") or []:
            if saved_query := data_view.get("saved_query"):
                evidence.append(
                    {
                        "kind": "sql",
                        "title": data_view.get("question") or data_view.get("id"),
                        "locator": {"query_id": saved_query.get("query_id")},
                        "lineage": saved_query.get("lineage") or data_view.get("lineage") or [],
                    }
                )
            if context_search := data_view.get("context_search"):
                evidence.append(
                    {
                        "kind": "document_section",
                        "title": data_view.get("question") or data_view.get("id"),
                        "locator": {
                            "source_binding_id": context_search.get("source_binding_id"),
                            "query_template": context_search.get("query_template"),
                        },
                    }
                )
            for locator in data_view.get("evidence") or []:
                evidence.append({**locator, "kind": "document_section"})
        if manifest.get("access_policy"):
            evidence.append(
                {
                    "kind": "permission_policy",
                    "title": "Dashboard access policy",
                    "policy": manifest["access_policy"],
                }
            )
        for case in recent_cases:
            evidence.append({"kind": "evaluation_case", **case})
        return evidence[:8]

    def _dashboard_case_payload(self, event: DashboardAuditEvent) -> dict[str, Any]:
        return {
            "id": str(event.id),
            "action": event.action,
            "outcome": event.outcome,
            "created_at": event.created_at.isoformat() if event.created_at else None,
            "details": event.details_json or {},
        }

    def _dashboard_consumers(self, asset: DashboardAsset) -> list[str]:
        summary = asset.consumer_summary_json or {}
        consumers = summary.get("consumers") if isinstance(summary, dict) else None
        if isinstance(consumers, list):
            return sorted(str(consumer) for consumer in consumers)
        if asset.published_version_id:
            return ["agent", "dashboard", "mcp", "share_link"]
        return []

    def _semantic_model_consumers(self, model: SemanticModel) -> list[str]:
        consumers = self._loads_json(model.consumers_json)
        if isinstance(consumers, dict) and isinstance(consumers.get("consumers"), list):
            return sorted(str(consumer) for consumer in consumers["consumers"])
        return ["agent", "mcp"] if model.published_version != "v0" else []

    def _semantic_model_blockers(self, model: SemanticModel) -> list[str]:
        log = self._loads_json(model.validation_log_json)
        if isinstance(log, list) and log:
            return [str(item) for item in log[:5]]
        if model.readiness_level == "blocked":
            return ["semantic model is blocked"]
        if model.published_version == "v0":
            return ["semantic model is not published"]
        return []

    def _dashboard_lineage_from_manifest(self, manifest: dict[str, Any] | None) -> dict[str, Any]:
        manifest = manifest or {}
        data_views = manifest.get("data_views") or []
        return {
            "dashboard_id": manifest.get("dashboard_id"),
            "semantic_bindings": manifest.get("semantic_bindings") or [],
            "data_views": [
                {
                    "id": data_view.get("id"),
                    "kind": data_view.get("kind"),
                    "lineage": data_view.get("lineage") or data_view.get("saved_query", {}).get("lineage", []),
                    "evidence": data_view.get("evidence") or [],
                }
                for data_view in data_views
            ],
            "migration": manifest.get("migration") or {},
        }

    def _locator_types(self, resource_type: str) -> list[str]:
        return {
            "pdf": ["page", "bbox"],
            "web": ["url", "selector", "text_range"],
            "feishu_doc": ["block"],
            "feishu_wiki": ["block"],
            "feishu_sheet": ["sheet_range", "cell"],
            "feishu_base": ["table", "record", "field"],
            "tos_object": ["bucket", "key", "version"],
            "tos_prefix": ["bucket", "prefix"],
            "tos_bucket": ["bucket"],
        }.get(resource_type, ["source_snapshot"])

    def _freshness_status(self, resource: SourceResource, snapshot: SourceSnapshot) -> str:
        if resource.latest_snapshot_id and str(resource.latest_snapshot_id) != str(snapshot.id):
            return "stale"
        if resource.status in {"reauthorization_required", "permission_lost", "source_unavailable", "failed"}:
            return resource.status
        return "current"

    def _source_snapshot_from_schema(self, schema: Any) -> str | None:
        if not isinstance(schema, dict):
            return None
        candidates = [
            schema.get("source_snapshot_id"),
            (schema.get("projection_manifest") or {}).get("source_snapshot_id")
            if isinstance(schema.get("projection_manifest"), dict)
            else None,
            (schema.get("source") or {}).get("snapshot_id") if isinstance(schema.get("source"), dict) else None,
        ]
        return next((str(value) for value in candidates if value), None)

    def _loads_json(self, value: str | None) -> Any:
        if not value:
            return {}
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}

    def _parse_uuid(self, value: str) -> UUID | None:
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None
