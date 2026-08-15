from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from server.models.datasets import Dataset
from server.models.knowledge_resources import EvidenceFragment, KnowledgeResource
from server.models.notebook_assets import NotebookAsset
from server.models.notebooks import NotebookDataset
from server.models.semantic_models import SemanticModel
from server.models.source_connections import SourceConnection
from server.models.source_resources import SourceResource
from server.models.source_snapshots import SourceSnapshot
from server.models.user import User
from server.schemas.source_overview import SourceOverviewItem

SOURCE_OVERVIEW_RESOURCE_TYPES = (
    "file",
    "pdf",
    "web",
    "feishu_doc",
    "feishu_wiki",
    "feishu_sheet",
    "feishu_base",
    "tos_bucket",
    "tos_prefix",
    "tos_object",
    "extracted_table",
)

SOURCE_STATUS_LABELS = {
    "ready": "Ready",
    "pending": "Pending",
    "syncing": "Syncing",
    "understanding": "Analyzing",
    "authorization_required": "Authorization required",
    "reauthorization_required": "Reauthorization required",
    "permission_lost": "Permission lost",
    "source_unavailable": "Source unavailable",
    "needs_confirmation": "Needs confirmation",
    "failed": "Failed",
    "disconnected": "Authorization required",
}


@dataclass
class _ConsumerIndex:
    semantic_by_id: dict[str, int] = field(default_factory=dict)
    notebooks_by_dataset_id: dict[str, set[str]] = field(default_factory=dict)
    notebooks_by_knowledge_id: dict[str, set[str]] = field(default_factory=dict)


class SourceOverviewService:
    async def list_overview(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
    ) -> dict[str, Any]:
        datasets = await self._list_visible_datasets(session=session, tenant_id=tenant_id, user_id=user_id)
        resources = await self._list_visible_source_resources(session=session, tenant_id=tenant_id, user_id=user_id)
        source_resource_context = await self._source_resource_context(
            session=session,
            tenant_id=tenant_id,
            resources=resources,
        )
        consumer_index = await self._consumer_index(session=session, tenant_id=tenant_id)

        items: list[SourceOverviewItem] = []
        seen_connection_ids: set[str] = set()
        for dataset in datasets:
            item = self._dataset_item(
                dataset=dataset,
                seen_connection_ids=seen_connection_ids,
                consumer_index=consumer_index,
            )
            if item is not None:
                items.append(item)

        for resource in resources:
            items.append(
                self._source_resource_item(
                    resource=resource,
                    context=source_resource_context.get(str(resource.id), {}),
                    consumer_index=consumer_index,
                )
            )

        items.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
        return {"items": items, "total": len(items), "counts_partial": True}

    async def _list_visible_datasets(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
    ) -> list[Dataset]:
        result = await session.execute(
            select(Dataset)
            .where(Dataset.tenant_id == tenant_id)
            .options(joinedload(Dataset.files), joinedload(Dataset.connection))
        )
        datasets = list(result.scalars().unique().all())
        return [dataset for dataset in datasets if self._is_dataset_visible(dataset=dataset, user_id=user_id)]

    async def _list_visible_source_resources(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
    ) -> list[SourceResource]:
        result = await session.execute(
            select(SourceResource)
            .where(
                SourceResource.tenant_id == tenant_id,
                SourceResource.resource_type.in_(SOURCE_OVERVIEW_RESOURCE_TYPES),
            )
            .options(
                joinedload(SourceResource.owner),
                joinedload(SourceResource.source_connection),
            )
            .order_by(SourceResource.updated_at.desc())
        )
        resources = list(result.scalars().unique().all())
        return [
            resource
            for resource in resources
            if not self._is_removed(resource)
            and self._is_visible(
                created_by=resource.owner_id,
                is_public=resource.visibility in {"team", "public"},
                user_id=user_id,
            )
        ]

    async def _source_resource_context(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        resources: list[SourceResource],
    ) -> dict[str, dict[str, Any]]:
        if not resources:
            return {}
        resource_ids = [resource.id for resource in resources]

        snapshots_by_id: dict[str, SourceSnapshot] = {}
        snapshot_ids = [resource.latest_snapshot_id for resource in resources if resource.latest_snapshot_id]
        if snapshot_ids:
            snapshot_result = await session.execute(
                select(SourceSnapshot).where(
                    SourceSnapshot.tenant_id == tenant_id,
                    SourceSnapshot.id.in_(snapshot_ids),
                )
            )
            snapshots_by_id = {str(snapshot.id): snapshot for snapshot in snapshot_result.scalars().all()}

        knowledge_result = await session.execute(
            select(KnowledgeResource)
            .where(
                KnowledgeResource.tenant_id == tenant_id,
                KnowledgeResource.resource_id.in_(resource_ids),
            )
            .order_by(KnowledgeResource.created_at.desc())
        )
        knowledge_by_resource: dict[str, KnowledgeResource] = {}
        for knowledge in knowledge_result.scalars().all():
            knowledge_by_resource.setdefault(str(knowledge.resource_id), knowledge)

        evidence_counts: dict[str, int] = {}
        if knowledge_by_resource:
            evidence_result = await session.execute(
                select(EvidenceFragment.knowledge_resource_id, func.count(EvidenceFragment.id))
                .where(EvidenceFragment.tenant_id == tenant_id)
                .where(EvidenceFragment.knowledge_resource_id.in_([item.id for item in knowledge_by_resource.values()]))
                .group_by(EvidenceFragment.knowledge_resource_id)
            )
            evidence_counts = {str(knowledge_id): int(count) for knowledge_id, count in evidence_result.all()}

        context: dict[str, dict[str, Any]] = {}
        for resource in resources:
            snapshot = snapshots_by_id.get(str(resource.latest_snapshot_id)) if resource.latest_snapshot_id else None
            knowledge = knowledge_by_resource.get(str(resource.id))
            context[str(resource.id)] = {
                "latest_snapshot": snapshot,
                "knowledge_resource": knowledge,
                "evidence_count": evidence_counts.get(str(knowledge.id), 0) if knowledge else 0,
            }
        return context

    async def _consumer_index(self, *, session: AsyncSession, tenant_id: UUID) -> _ConsumerIndex:
        index = _ConsumerIndex()

        semantic_result = await session.execute(
            select(SemanticModel.datasource_id, func.count(SemanticModel.id))
            .where(SemanticModel.tenant_id == tenant_id)
            .group_by(SemanticModel.datasource_id)
        )
        index.semantic_by_id = {str(datasource_id): int(count) for datasource_id, count in semantic_result.all()}

        notebook_dataset_result = await session.execute(
            select(NotebookDataset.dataset_id, NotebookDataset.notebook_id)
            .join(Dataset, Dataset.id == NotebookDataset.dataset_id)
            .where(Dataset.tenant_id == tenant_id)
        )
        for dataset_id, notebook_id in notebook_dataset_result.all():
            index.notebooks_by_dataset_id.setdefault(str(dataset_id), set()).add(str(notebook_id))

        notebook_asset_result = await session.execute(
            select(NotebookAsset.asset_type, NotebookAsset.asset_id, NotebookAsset.notebook_id).where(
                NotebookAsset.tenant_id == tenant_id
            )
        )
        for asset_type, asset_id, notebook_id in notebook_asset_result.all():
            if asset_type == "dataset":
                index.notebooks_by_dataset_id.setdefault(str(asset_id), set()).add(str(notebook_id))
            elif asset_type == "knowledge_resource":
                index.notebooks_by_knowledge_id.setdefault(str(asset_id), set()).add(str(notebook_id))

        return index

    def _dataset_item(
        self,
        *,
        dataset: Dataset,
        seen_connection_ids: set[str],
        consumer_index: _ConsumerIndex,
    ) -> SourceOverviewItem | None:
        if dataset.type == "connection":
            if dataset.connection is None:
                return None
            connection_id = str(dataset.connection_id)
            if connection_id in seen_connection_ids:
                return None
            seen_connection_ids.add(connection_id)
            provider = dataset.connection.type
            updated_at = dataset.connection.schema_updated_at or dataset.created_at
            semantic_keys = {str(dataset.id), connection_id}
            notebooks = set(consumer_index.notebooks_by_dataset_id.get(str(dataset.id), set()))
            return SourceOverviewItem(
                id=str(dataset.id),
                source_kind="connection",
                connection_id=connection_id,
                family="warehouses" if provider == "databricks" else "databases",
                provider=provider,
                resource_type=provider,
                name=dataset.connection.name or "Database Connection",
                status="Ready",
                attention_state="none",
                freshness_status="fresh" if dataset.connection.schema_updated_at else "unknown",
                last_synced_at=self._isoformat(dataset.connection.schema_updated_at),
                context_index_status="unavailable",
                parse_status="parsed",
                parsed_asset_counts={"tables": self._schema_table_count(dataset.connection.schema_cache)},
                consumer_counts={
                    "semantic_models": self._semantic_count(consumer_index, semantic_keys),
                    "dashboards": 0,
                    "notebooks": len(notebooks),
                    "mcp_tools": 0,
                },
                owner=self._owner_payload(dataset.connection.created_by),
                visibility="public" if dataset.connection.is_public else "private",
                next_actions=self._connection_next_actions(
                    provider=provider,
                    has_schema=bool(dataset.connection.schema_updated_at),
                    semantic_count=self._semantic_count(consumer_index, semantic_keys),
                ),
                created_at=self._isoformat(dataset.created_at) or "",
                updated_at=self._isoformat(updated_at),
            )

        if dataset.type != "file":
            return None
        file_type = dataset.files[0].type if dataset.files else None
        updated_at = dataset.schema_updated_at or dataset.created_at
        notebooks = set(consumer_index.notebooks_by_dataset_id.get(str(dataset.id), set()))
        return SourceOverviewItem(
            id=str(dataset.id),
            source_kind="dataset",
            connection_id=str(dataset.connection_id) if dataset.connection_id else None,
            family="files",
            provider="local_file",
            resource_type=file_type,
            name=dataset.name or "Unnamed Dataset",
            status="Ready" if dataset.files else "Pending",
            attention_state="none",
            freshness_status="fresh" if dataset.files else "unknown",
            last_synced_at=self._isoformat(updated_at),
            context_index_status="unavailable",
            parse_status="parsed" if dataset.files else "pending",
            parsed_asset_counts={
                "tables": self._schema_table_count(dataset.schema_cache),
                "files": len(dataset.files or []),
            },
            consumer_counts={
                "semantic_models": self._semantic_count(consumer_index, {str(dataset.id)}),
                "dashboards": 0,
                "notebooks": len(notebooks),
                "mcp_tools": 0,
            },
            owner=self._owner_payload(dataset.created_by),
            visibility="public" if dataset.is_public else "private",
            next_actions=self._dataset_next_actions(
                has_files=bool(dataset.files),
                has_schema=bool(dataset.schema_cache),
                semantic_count=self._semantic_count(consumer_index, {str(dataset.id)}),
            ),
            created_at=self._isoformat(dataset.created_at) or "",
            updated_at=self._isoformat(updated_at),
        )

    def _source_resource_item(
        self,
        *,
        resource: SourceResource,
        context: dict[str, Any],
        consumer_index: _ConsumerIndex,
    ) -> SourceOverviewItem:
        source_connection = resource.source_connection
        status = self._effective_source_resource_status(resource=resource, connection=source_connection)
        latest_snapshot = context.get("latest_snapshot")
        knowledge_resource = context.get("knowledge_resource")
        evidence_count = int(context.get("evidence_count") or 0)
        projected_dataset_id = (resource.sync_config_json or {}).get("projected_dataset_id")
        projection = (resource.sync_config_json or {}).get("projected_dataset") or {}
        notebooks = set()
        if knowledge_resource:
            notebooks.update(consumer_index.notebooks_by_knowledge_id.get(str(knowledge_resource.id), set()))
        if projected_dataset_id:
            notebooks.update(consumer_index.notebooks_by_dataset_id.get(str(projected_dataset_id), set()))
        semantic_keys = {str(resource.id)}
        if projected_dataset_id:
            semantic_keys.add(str(projected_dataset_id))

        return SourceOverviewItem(
            id=str(resource.id),
            source_kind="source_resource",
            connection_id=str(resource.source_connection_id) if resource.source_connection_id else None,
            family=self._resource_family(resource.resource_type),
            provider=self._source_resource_provider(resource=resource, connection=source_connection),
            resource_type=resource.resource_type,
            name=resource.name,
            status=SOURCE_STATUS_LABELS.get(status, status.replace("_", " ").capitalize()),
            attention_state=self._attention_state(status=status, knowledge_resource=knowledge_resource),
            freshness_status=self._freshness_status(status=status, latest_snapshot=latest_snapshot),
            last_synced_at=self._isoformat(latest_snapshot.captured_at if latest_snapshot else resource.updated_at),
            latest_snapshot_id=str(resource.latest_snapshot_id) if resource.latest_snapshot_id else None,
            projected_dataset_id=str(projected_dataset_id) if projected_dataset_id else None,
            context_index_status=self._context_index_status(status=status, knowledge_resource=knowledge_resource),
            parse_status=self._parse_status(latest_snapshot=latest_snapshot, knowledge_resource=knowledge_resource),
            parsed_asset_counts={
                "blocks": evidence_count,
                "tables": self._projection_table_count(projection),
                "files": int(projection.get("files_count") or len(projection.get("files") or [])),
                "evidence": evidence_count,
            },
            consumer_counts={
                "semantic_models": self._semantic_count(consumer_index, semantic_keys),
                "dashboards": 0,
                "notebooks": len(notebooks),
                "mcp_tools": 0,
            },
            owner=self._user_owner_payload(resource.owner) or self._owner_payload(resource.owner_id),
            visibility=self._visibility(resource.visibility),
            next_actions=self._source_resource_next_actions(
                status=status,
                family=self._resource_family(resource.resource_type),
                has_snapshot=latest_snapshot is not None,
                projected_dataset_id=str(projected_dataset_id) if projected_dataset_id else None,
                knowledge_resource=knowledge_resource,
                semantic_count=self._semantic_count(consumer_index, semantic_keys),
            ),
            created_at=self._isoformat(resource.created_at) or "",
            updated_at=self._isoformat(resource.updated_at),
        )

    def _effective_source_resource_status(
        self,
        *,
        resource: SourceResource,
        connection: SourceConnection | None,
    ) -> str:
        if connection is None:
            return resource.status
        if connection.status in {"reauthorization_required", "authorization_required", "disconnected"}:
            return connection.status
        if connection.status == "failed":
            return "source_unavailable"
        return resource.status

    def _source_resource_provider(
        self,
        *,
        resource: SourceResource,
        connection: SourceConnection | None,
    ) -> str:
        if connection is not None:
            return connection.provider
        if resource.resource_type.startswith("feishu_"):
            return "feishu"
        if resource.resource_type.startswith("tos_"):
            return "volcengine_tos"
        if resource.resource_type == "web":
            return "web"
        return "local_file"

    def _resource_family(self, resource_type: str) -> str:
        if resource_type == "web":
            return "web"
        if resource_type.startswith("feishu_"):
            return "documents"
        if resource_type.startswith("tos_"):
            return "object_storage"
        if resource_type.startswith("database_"):
            return "databases"
        return "files"

    def _attention_state(self, *, status: str, knowledge_resource: KnowledgeResource | None) -> str:
        if status in {"authorization_required", "reauthorization_required", "disconnected"}:
            return "auth"
        if status == "permission_lost":
            return "permission"
        if status in {"needs_confirmation", "failed"}:
            return "parse"
        if status == "source_unavailable":
            return "stale"
        if knowledge_resource and knowledge_resource.index_status == "failed":
            return "index"
        return "none"

    def _freshness_status(self, *, status: str, latest_snapshot: SourceSnapshot | None) -> str:
        if status == "ready" and latest_snapshot is not None:
            return "fresh"
        if (
            status
            in {
                "authorization_required",
                "reauthorization_required",
                "permission_lost",
                "source_unavailable",
                "failed",
                "disconnected",
            }
            and latest_snapshot is not None
        ):
            return "stale"
        return "unknown"

    def _context_index_status(self, *, status: str, knowledge_resource: KnowledgeResource | None) -> str:
        if knowledge_resource is None:
            return "unavailable" if status in {"needs_confirmation", "failed"} else "pending"
        if knowledge_resource.index_status == "indexed":
            return "indexed"
        if knowledge_resource.index_status == "failed":
            return "failed"
        return "indexing"

    def _parse_status(
        self,
        *,
        latest_snapshot: SourceSnapshot | None,
        knowledge_resource: KnowledgeResource | None,
    ) -> str:
        if knowledge_resource is not None:
            return knowledge_resource.parse_status
        if latest_snapshot is None:
            return "pending"
        if latest_snapshot.status == "failed":
            return "failed"
        return "parsed"

    def _connection_next_actions(self, *, provider: str, has_schema: bool, semantic_count: int) -> list[str]:
        if not has_schema:
            return ["Refresh schema profile"]
        if provider == "databricks":
            if semantic_count == 0:
                return ["Generate semantic model", "Open warehouse catalog"]
            return ["Review warehouse consumers", "Refresh schema profile"]
        if semantic_count == 0:
            return ["Generate semantic model"]
        return ["Review semantic consumers", "Refresh schema profile"]

    def _dataset_next_actions(self, *, has_files: bool, has_schema: bool, semantic_count: int) -> list[str]:
        if not has_files:
            return ["Upload files"]
        if not has_schema:
            return ["Profile dataset"]
        if semantic_count == 0:
            return ["Generate semantic model"]
        return ["Review semantic consumers"]

    def _source_resource_next_actions(
        self,
        *,
        status: str,
        family: str,
        has_snapshot: bool,
        projected_dataset_id: str | None,
        knowledge_resource: KnowledgeResource | None,
        semantic_count: int,
    ) -> list[str]:
        if status in {"authorization_required", "reauthorization_required", "disconnected"}:
            return ["Reauthorize source"]
        if status == "permission_lost":
            return ["Review resource permissions", "Reauthorize source"]
        if status == "source_unavailable":
            return ["Retry sync", "Check upstream source"]
        if status == "failed":
            return ["Review parser warning", "Retry sync"]
        if status == "needs_confirmation":
            return ["Confirm resource selection"]
        if knowledge_resource and knowledge_resource.index_status == "failed":
            return ["Retry context indexing"]
        if family in {"documents", "web"}:
            if knowledge_resource and knowledge_resource.index_status == "indexed":
                return ["Search evidence", "Attach to notebook"]
            if has_snapshot:
                return ["Index context"]
            return ["Capture snapshot"]
        if family == "object_storage":
            if projected_dataset_id and semantic_count == 0:
                return ["Review projection", "Generate semantic model"]
            if knowledge_resource and knowledge_resource.index_status == "indexed":
                return ["Search evidence", "Review projection"]
            if has_snapshot:
                return ["Parse object", "Index context"]
            return ["Browse bucket or prefix"]
        if family == "databases":
            if projected_dataset_id and semantic_count == 0:
                return ["Generate semantic model"]
            return ["Review schema profile"]
        if projected_dataset_id and semantic_count == 0:
            return ["Generate semantic model"]
        if has_snapshot:
            return ["Open source detail"]
        return ["Capture snapshot"]

    def _schema_table_count(self, schema_cache: str | None) -> int:
        if not schema_cache:
            return 0
        try:
            schema = json.loads(schema_cache)
        except json.JSONDecodeError:
            return 0
        tables = schema.get("schema") if isinstance(schema, dict) else None
        if isinstance(tables, dict):
            return len(tables)
        tables = schema.get("tables") if isinstance(schema, dict) else None
        return len(tables) if isinstance(tables, dict) else 0

    def _projection_table_count(self, projection: dict[str, Any]) -> int:
        tables = projection.get("schema_tables")
        return len(tables) if isinstance(tables, list) else 0

    def _semantic_count(self, consumer_index: _ConsumerIndex, ids: set[str]) -> int:
        return sum(consumer_index.semantic_by_id.get(item_id, 0) for item_id in ids)

    def _is_visible(self, *, created_by: UUID | None, is_public: bool, user_id: UUID) -> bool:
        if created_by is None:
            return True
        return created_by == user_id or is_public

    def _is_dataset_visible(self, *, dataset: Dataset, user_id: UUID) -> bool:
        if dataset.type == "connection" and dataset.connection is not None:
            return self._is_visible(
                created_by=dataset.created_by,
                is_public=dataset.connection.is_public,
                user_id=user_id,
            )
        return self._is_visible(created_by=dataset.created_by, is_public=dataset.is_public, user_id=user_id)

    def _is_removed(self, resource: SourceResource) -> bool:
        return ((resource.sync_config_json or {}).get("deletion_marker") or {}).get("status") == "removed"

    def _visibility(self, visibility: str) -> str:
        return visibility if visibility in {"private", "workspace", "team", "public"} else "workspace"

    def _owner_payload(self, owner_id: UUID | None) -> dict[str, str] | None:
        return {"id": str(owner_id)} if owner_id else None

    def _user_owner_payload(self, owner: User | None) -> dict[str, str] | None:
        if owner is None:
            return None
        return {"id": str(owner.id), "name": owner.full_name or owner.email}

    def _isoformat(self, value: datetime | None) -> str | None:
        return value.isoformat() if value else None
