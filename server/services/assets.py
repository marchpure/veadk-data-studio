from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        allowed_types = set(asset_types or ("dataset", "semantic_model", "knowledge_resource"))
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
            usage_by_key = {
                (item.asset_type, item.asset_id): item.usage_policy_json or {}
                for item in notebook_assets
            }
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

        filtered = [item for item in items if self._matches_query(item, query)]
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
        return [self._dataset_payload(dataset, usage_by_key.get(("dataset", str(dataset.id)), {})) for dataset in result.scalars().all()]

    async def _list_semantic_model_assets(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        model_ids: list[str],
        include_all: bool,
        usage_by_key: dict[tuple[str, str], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        stmt = select(SemanticModel).where(SemanticModel.tenant_id == tenant_id)
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
            self._semantic_model_payload(model, usage_by_key.get(("semantic_model", str(model.id)), {}) or usage_by_key.get(("semantic_model", model.slug), {}))
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
                samples = await self._sample_evidence(session=session, tenant_id=tenant_id, knowledge_resource_id=knowledge.id)
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
        return {
            "asset_type": "semantic_model",
            "asset_id": str(model.id),
            "name": model.name,
            "description": model.description,
            "status": model.status,
            "capabilities": {
                "execution_modes": ["run_semantic_query"],
                "slug": model.slug,
                "domain": model.domain,
                "published_version": model.published_version,
                "readiness": model.readiness,
                "readiness_level": model.readiness_level,
            },
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
