from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import aiofiles
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from server.config.storage import dataset_directory, source_resource_directory
from server.models.datasets import Dataset
from server.models.files import File
from server.models.knowledge_resources import EvidenceFragment, KnowledgeResource
from server.models.notebook_assets import NotebookAsset
from server.models.notebooks import Notebook
from server.models.source_connections import SourceConnection
from server.models.source_resources import SourceResource
from server.models.source_snapshots import SourceSnapshot
from server.schemas.source_resources import SourceResourceCreate, SourceResourceImportRequest, SourceResourceSyncRequest
from server.services.dataset_storage import DatasetStorageService
from server.services.file_operations import DataFrameFileService
from server.services.knowledge_provider import get_knowledge_provider, stable_hash
from server.services.source_connectors import (
    CapturedSnapshot,
    ConnectorError,
    SourceConnectorAdapter,
    get_connector_adapter,
    parse_object_bytes,
)
from server.services.web_source_adapter import WebCapturedPage, WebSourceAdapter


class SourceResourceService:
    pdf_max_upload_bytes = 50 * 1024 * 1024
    sync_run_statuses = ("queued", "running", "succeeded", "failed", "partial", "cancelled")

    connector_ready_types = {
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
    }

    async def create_resource(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        user_id: UUID | None,
        payload: SourceResourceCreate,
    ) -> dict[str, Any]:
        resource = SourceResource(
            tenant_id=tenant_id,
            resource_type=payload.resource_type,
            name=payload.name,
            external_id=payload.external_id,
            source_url=payload.source_url,
            owner_id=user_id,
            visibility=payload.visibility,
            sync_mode=payload.sync_mode,
            sync_config_json=payload.sync_config,
            status="pending",
        )
        session.add(resource)
        await session.flush()

        if payload.content and payload.content.strip():
            await self._capture_and_ingest(
                session=session,
                resource=resource,
                content=payload.content,
                external_revision=payload.external_revision,
                metadata=payload.metadata,
                provider=payload.provider,
            )
            resource.status = "ready"
        elif payload.resource_type == "web" and payload.source_url:
            try:
                captured = await WebSourceAdapter().capture(payload.source_url)
                await self._capture_web_page(session=session, resource=resource, captured=captured)
                resource.status = "ready"
            except ConnectorError as exc:
                resource.status = self._status_for_connector_error(exc)
                resource.sync_config_json = {
                    **(resource.sync_config_json or {}),
                    "last_error": {"code": exc.code, "message": str(exc), "permanent": exc.permanent},
                }
        else:
            resource.status = "needs_confirmation"

        await session.commit()
        await session.refresh(resource)
        return await self.resource_payload(session=session, resource=resource)

    async def import_resources(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        user_id: UUID | None,
        payload: SourceResourceImportRequest,
        adapter: SourceConnectorAdapter | None = None,
    ) -> dict[str, Any]:
        connection = await session.scalar(
            select(SourceConnection).where(
                SourceConnection.tenant_id == tenant_id,
                SourceConnection.id == payload.connection_id,
            )
        )
        if connection is None:
            raise ValueError("Source connection not found")
        if connection.status in {"reauthorization_required", "authorization_required", "disconnected"}:
            raise ValueError(f"Source connection is not usable: {connection.status}")
        adapter = adapter or get_connector_adapter(connection.provider)
        results: list[dict[str, Any]] = []
        for selection in payload.selections:
            resource = await self._get_or_create_imported_resource(
                session=session,
                tenant_id=tenant_id,
                user_id=user_id,
                connection=connection,
                payload=payload,
                selection=selection,
            )
            try:
                await self._sync_resource_via_adapter(
                    session=session,
                    resource=resource,
                    connection=connection,
                    adapter=adapter,
                )
                status = "ready"
                error = None
            except ConnectorError as exc:
                resource.status = self._status_for_connector_error(exc)
                resource.sync_config_json = {
                    **(resource.sync_config_json or {}),
                    "last_error": {"code": exc.code, "message": str(exc), "permanent": exc.permanent},
                }
                await session.flush()
                status = resource.status
                error = {"code": exc.code, "message": str(exc), "permanent": exc.permanent}
            await session.refresh(resource)
            results.append(
                {
                    "selection": selection.model_dump(),
                    "resource": await self.resource_payload(session=session, resource=resource),
                    "status": status,
                    "error": error,
                }
            )
        await session.commit()
        return {
            "connection_id": connection.id,
            "results": results,
            "succeeded": len([item for item in results if item["status"] == "ready"]),
            "failed": len([item for item in results if item["status"] != "ready"]),
        }

    async def sync_resource(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        resource_id: str,
        payload: SourceResourceSyncRequest,
    ) -> dict[str, Any]:
        resource = await self.get_resource(session=session, tenant_id=tenant_id, resource_id=resource_id)
        if resource is None:
            raise ValueError("Source resource not found")
        if resource.source_connection_id:
            connection = await session.get(SourceConnection, resource.source_connection_id)
            if connection is None or connection.tenant_id != tenant_id:
                raise ValueError("Source connection not found")
            await self._sync_resource_via_adapter(
                session=session,
                resource=resource,
                connection=connection,
                adapter=get_connector_adapter(connection.provider),
            )
            await session.commit()
            await session.refresh(resource)
            return await self.resource_payload(session=session, resource=resource)
        if resource.resource_type == "web" and resource.source_url:
            previous_snapshot_id = resource.latest_snapshot_id
            sync_run = self._start_sync_run(resource=resource, trigger="manual")
            try:
                captured = await WebSourceAdapter().capture(resource.source_url)
                snapshot = await self._capture_web_page(session=session, resource=resource, captured=captured)
                resource.status = "ready"
                self._finish_sync_run(resource=resource, sync_run=sync_run, status="succeeded", snapshot=snapshot)
            except ConnectorError as exc:
                resource.latest_snapshot_id = previous_snapshot_id
                resource.status = self._status_for_connector_error(exc)
                self._finish_sync_run(resource=resource, sync_run=sync_run, status="failed", error=exc)
                resource.sync_config_json = {
                    **(resource.sync_config_json or {}),
                    "last_error": {"code": exc.code, "message": str(exc), "permanent": exc.permanent},
                }
            await session.commit()
            await session.refresh(resource)
            return await self.resource_payload(session=session, resource=resource)
        if not payload.content or not payload.content.strip():
            resource.status = "needs_confirmation"
            await session.commit()
            await session.refresh(resource)
            return await self.resource_payload(session=session, resource=resource)

        await self._capture_and_ingest(
            session=session,
            resource=resource,
            content=payload.content,
            external_revision=payload.external_revision,
            metadata=payload.metadata,
            provider=payload.provider,
        )
        resource.status = "ready"
        await session.commit()
        await session.refresh(resource)
        return await self.resource_payload(session=session, resource=resource)

    async def create_pdf_resource_from_upload(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        user_id: UUID | None,
        name: str,
        filename: str,
        data: bytes,
        visibility: str = "workspace",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not data:
            raise ValueError("PDF file is empty")
        if len(data) > self.pdf_max_upload_bytes:
            raise ValueError("PDF file exceeds the 50 MB limit")
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Only PDF files are supported by this endpoint")

        resource = SourceResource(
            tenant_id=tenant_id,
            resource_type="pdf",
            name=name.strip() or Path(filename).stem or "PDF document",
            external_id=None,
            source_url=None,
            owner_id=user_id,
            visibility=visibility,
            sync_mode="manual",
            sync_config_json={"original_filename": filename, "upload_size": len(data)},
            status="pending",
        )
        session.add(resource)
        await session.flush()

        try:
            content_text, parser_version, fragment_hint = parse_object_bytes(key=filename, raw_bytes=data)
            captured = CapturedSnapshot(
                raw_bytes=data,
                content_text=content_text,
                external_revision="sha256:" + hashlib.sha256(data).hexdigest(),
                metadata={
                    **(metadata or {}),
                    "provider": "local_pdf_upload",
                    "original_filename": filename,
                    "size": len(data),
                    "fragment_hint": fragment_hint,
                },
                provider="byaan-native",
                parser_version=parser_version,
                raw_storage_uri="pending://local-pdf-upload",
            )
            await self._capture_uploaded_file(session=session, resource=resource, captured=captured, filename=filename)
            resource.status = "ready"
        except ConnectorError as exc:
            captured = CapturedSnapshot(
                raw_bytes=data,
                content_text="",
                external_revision="sha256:" + hashlib.sha256(data).hexdigest(),
                metadata={
                    **(metadata or {}),
                    "provider": "local_pdf_upload",
                    "original_filename": filename,
                    "size": len(data),
                    "parse_error": {"code": exc.code, "message": str(exc), "permanent": exc.permanent},
                },
                provider="byaan-native",
                parser_version="pdf-upload-parse-failed-v1",
                raw_storage_uri="pending://local-pdf-upload",
            )
            await self._capture_uploaded_file(
                session=session,
                resource=resource,
                captured=captured,
                filename=filename,
                error=exc,
            )
            resource.status = self._status_for_connector_error(exc)
            resource.sync_config_json = {
                **(resource.sync_config_json or {}),
                "last_error": {"code": exc.code, "message": str(exc), "permanent": exc.permanent},
            }

        await session.commit()
        await session.refresh(resource)
        return await self.resource_payload(session=session, resource=resource)

    async def list_resources(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
    ) -> list[dict[str, Any]]:
        result = await session.execute(
            select(SourceResource)
            .where(
                SourceResource.tenant_id == tenant_id,
                SourceResource.resource_type.in_(self.connector_ready_types),
            )
            .order_by(SourceResource.updated_at.desc())
        )
        resources = list(result.scalars().all())
        resources = [resource for resource in resources if not self._is_removed(resource)]
        return [await self.resource_payload(session=session, resource=resource) for resource in resources]

    async def delete_resource(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        resource_id: str | UUID,
    ) -> bool:
        resource = await self.get_resource(session=session, tenant_id=tenant_id, resource_id=resource_id)
        if resource is None:
            return False
        await self._mark_resource_removed(session=session, resource=resource)
        await session.commit()
        return True

    async def get_resource(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        resource_id: str | UUID,
    ) -> SourceResource | None:
        return await session.scalar(
            select(SourceResource).where(SourceResource.tenant_id == tenant_id, SourceResource.id == resource_id)
        )

    async def resource_payload(self, *, session: AsyncSession, resource: SourceResource) -> dict[str, Any]:
        latest_snapshot = None
        if resource.latest_snapshot_id:
            latest_snapshot = await session.get(SourceSnapshot, resource.latest_snapshot_id)
        status = resource.status
        sync_config = dict(resource.sync_config_json or {})
        if resource.source_connection_id:
            connection = await session.get(SourceConnection, resource.source_connection_id)
            if connection is not None and connection.status in {
                "reauthorization_required",
                "authorization_required",
                "disconnected",
            }:
                status = (
                    "reauthorization_required"
                    if connection.status in {"reauthorization_required", "authorization_required"}
                    else "disconnected"
                )
                sync_config = {
                    **sync_config,
                    "connection_status": connection.status,
                    "last_error": {
                        "code": status,
                        "message": f"Source connection is not usable: {connection.status}",
                        "permanent": True,
                    },
                }

        knowledge_resource = await session.scalar(
            select(KnowledgeResource)
            .where(KnowledgeResource.tenant_id == resource.tenant_id, KnowledgeResource.resource_id == resource.id)
            .order_by(KnowledgeResource.created_at.desc())
            .limit(1)
        )
        knowledge_payload = None
        if knowledge_resource:
            knowledge_payload = await self._knowledge_resource_payload(
                session=session,
                knowledge_resource=knowledge_resource,
            )

        return {
            "id": resource.id,
            "connection_id": resource.connection_id,
            "source_connection_id": resource.source_connection_id,
            "resource_type": resource.resource_type,
            "name": resource.name,
            "external_id": resource.external_id,
            "source_url": resource.source_url,
            "parent_external_id": resource.parent_external_id,
            "selection_config_json": resource.selection_config_json,
            "visibility": resource.visibility,
            "sync_mode": resource.sync_mode,
            "sync_config_json": sync_config,
            "status": status,
            "latest_snapshot_id": resource.latest_snapshot_id,
            "projected_dataset_id": (resource.sync_config_json or {}).get("projected_dataset_id"),
            "created_at": resource.created_at,
            "updated_at": resource.updated_at,
            "latest_snapshot": self._snapshot_payload(latest_snapshot) if latest_snapshot else None,
            "knowledge_resource": knowledge_payload,
        }

    async def processing_payload(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        resource_id: str,
    ) -> dict[str, Any]:
        resource = await self.get_resource(session=session, tenant_id=tenant_id, resource_id=resource_id)
        if resource is None:
            raise ValueError("Source resource not found")
        knowledge_resource = await session.scalar(
            select(KnowledgeResource)
            .where(KnowledgeResource.tenant_id == tenant_id, KnowledgeResource.resource_id == resource.id)
            .order_by(KnowledgeResource.created_at.desc())
            .limit(1)
        )
        evidence_count = 0
        if knowledge_resource:
            evidence_count = int(
                await session.scalar(
                    select(func.count(EvidenceFragment.id)).where(
                        EvidenceFragment.knowledge_resource_id == knowledge_resource.id
                    )
                )
                or 0
            )

        sync_config = resource.sync_config_json or {}
        last_error = sync_config.get("last_error") if isinstance(sync_config.get("last_error"), dict) else None
        if resource.status == "ready":
            stage = "indexed"
            message = "Resource has a captured Source Snapshot and indexed Evidence Fragments."
            next_actions = ["Use search_knowledge/read_evidence in agent runs", "Attach to a notebook asset"]
            connector_required = False
        elif resource.status in {
            "failed",
            "source_unavailable",
            "permission_lost",
            "reauthorization_required",
            "authorization_required",
        }:
            stage = "failed"
            message = (last_error or {}).get("message") or "Resource processing failed."
            next_actions = [
                "Fix the source configuration",
                "Reauthorize the source connection if required",
                "Retry sync after the source is available",
            ]
            connector_required = False
        elif resource.latest_snapshot_id:
            stage = "captured"
            message = "Snapshot is captured but indexing is incomplete."
            next_actions = ["Retry sync with connector-supplied content"]
            connector_required = False
        else:
            stage = "waiting_for_connector"
            message = "No content has been captured yet. Provide connector output; the API will not fake retrieval."
            next_actions = ["Run Feishu/PDF/Web/Sheet connector", "POST content to the sync endpoint"]
            connector_required = True

        return {
            "resource_id": resource.id,
            "status": resource.status,
            "stage": stage,
            "message": message,
            "last_error": last_error,
            "latest_snapshot_id": resource.latest_snapshot_id,
            "knowledge_resource_id": knowledge_resource.id if knowledge_resource else None,
            "evidence_count": evidence_count,
            "connector_required": connector_required,
            "next_actions": next_actions,
        }

    async def list_snapshots(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        resource_id: str | UUID,
    ) -> dict[str, Any]:
        resource = await self.get_resource(session=session, tenant_id=tenant_id, resource_id=resource_id)
        if resource is None:
            raise ValueError("Source resource not found")
        result = await session.execute(
            select(SourceSnapshot)
            .where(SourceSnapshot.tenant_id == tenant_id, SourceSnapshot.resource_id == resource.id)
            .order_by(SourceSnapshot.captured_at.desc(), SourceSnapshot.id.desc())
        )
        snapshots = list(result.scalars().all())
        items = []
        for snapshot in snapshots:
            payload = self._snapshot_payload(snapshot) or {}
            payload["is_latest"] = snapshot.id == resource.latest_snapshot_id
            items.append(payload)
        return {"resource_id": resource.id, "items": items, "total": len(items)}

    async def search_knowledge(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        query: str,
        resource_ids: list[UUID],
        limit: int,
    ) -> list[EvidenceFragment]:
        provider = get_knowledge_provider()
        from server.services.knowledge_provider import KnowledgeSearchInput

        return await provider.search(
            session=session,
            input=KnowledgeSearchInput(tenant_id=tenant_id, query=query, resource_ids=tuple(resource_ids), limit=limit),
        )

    async def read_evidence(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        evidence_id: str | UUID,
    ) -> dict[str, Any] | None:
        try:
            parsed_evidence_id = UUID(str(evidence_id))
        except ValueError:
            return None

        provider = get_knowledge_provider()
        evidence = await provider.read(
            session=session,
            tenant_id=tenant_id,
            evidence_id=parsed_evidence_id,
        )
        if evidence is None:
            return None

        knowledge_resource = await session.get(KnowledgeResource, evidence.knowledge_resource_id)
        snapshot = await session.get(SourceSnapshot, evidence.snapshot_id)
        if knowledge_resource is None or knowledge_resource.tenant_id != tenant_id:
            return None
        if snapshot is None or snapshot.tenant_id != tenant_id:
            return None

        resource = await self.get_resource(session=session, tenant_id=tenant_id, resource_id=knowledge_resource.resource_id)
        if resource is None:
            return None

        return {
            "evidence": self._evidence_payload(evidence),
            "knowledge_resource": await self._knowledge_resource_payload(
                session=session,
                knowledge_resource=knowledge_resource,
            ),
            "source_snapshot": self._snapshot_payload(snapshot),
            "source_resource": await self.resource_payload(session=session, resource=resource),
        }

    async def bind_notebook_asset(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        user_id: UUID | None,
        notebook_id: str,
        asset_type: str,
        asset_id: str,
        usage_policy: dict[str, Any],
    ) -> NotebookAsset:
        notebook = await session.scalar(
            select(Notebook).where(Notebook.tenant_id == tenant_id, Notebook.id == notebook_id)
        )
        if notebook is None:
            raise ValueError("Notebook not found")

        await self._validate_asset(session=session, tenant_id=tenant_id, asset_type=asset_type, asset_id=asset_id)
        existing = await session.scalar(
            select(NotebookAsset).where(
                NotebookAsset.tenant_id == tenant_id,
                NotebookAsset.notebook_id == notebook.id,
                NotebookAsset.asset_type == asset_type,
                NotebookAsset.asset_id == str(asset_id),
            )
        )
        if existing:
            existing.usage_policy_json = usage_policy
            await session.commit()
            await session.refresh(existing)
            return existing

        asset = NotebookAsset(
            tenant_id=tenant_id,
            notebook_id=notebook.id,
            asset_type=asset_type,
            asset_id=str(asset_id),
            added_by=user_id,
            usage_policy_json=usage_policy,
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        return asset

    async def list_notebook_assets(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        notebook_id: str,
    ) -> list[NotebookAsset]:
        result = await session.execute(
            select(NotebookAsset)
            .where(NotebookAsset.tenant_id == tenant_id, NotebookAsset.notebook_id == notebook_id)
            .order_by(NotebookAsset.added_at.desc())
        )
        return list(result.scalars().all())

    async def _validate_asset(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        asset_type: str,
        asset_id: str,
    ) -> None:
        if asset_type == "knowledge_resource":
            exists = await session.scalar(
                select(KnowledgeResource.id).where(
                    KnowledgeResource.tenant_id == tenant_id,
                    KnowledgeResource.id == asset_id,
                )
            )
        elif asset_type == "dataset":
            from server.models.datasets import Dataset

            exists = await session.scalar(select(Dataset.id).where(Dataset.tenant_id == tenant_id, Dataset.id == asset_id))
        elif asset_type == "semantic_model":
            from server.models.semantic_models import SemanticModel

            semantic_filters = [SemanticModel.slug == asset_id]
            try:
                semantic_filters.append(SemanticModel.id == UUID(asset_id))
            except ValueError:
                pass
            exists = await session.scalar(
                select(SemanticModel.id).where(SemanticModel.tenant_id == tenant_id, or_(*semantic_filters))
            )
        else:
            raise ValueError("Unsupported notebook asset type")
        if exists is None:
            raise ValueError(f"{asset_type} asset not found")

    async def _capture_and_ingest(
        self,
        *,
        session: AsyncSession,
        resource: SourceResource,
        content: str,
        external_revision: str | None,
        metadata: dict[str, Any],
        provider: str,
    ) -> SourceSnapshot:
        content_hash = stable_hash(content)
        existing_snapshot = await session.scalar(
            select(SourceSnapshot)
            .where(
                SourceSnapshot.tenant_id == resource.tenant_id,
                SourceSnapshot.resource_id == resource.id,
                SourceSnapshot.content_hash == content_hash,
            )
            .order_by(SourceSnapshot.captured_at.desc())
            .limit(1)
        )
        if existing_snapshot:
            resource.latest_snapshot_id = existing_snapshot.id
            resource.status = "ready"
            await session.flush()
            return existing_snapshot
        snapshot = SourceSnapshot(
            tenant_id=resource.tenant_id,
            resource_id=resource.id,
            external_revision=external_revision,
            content_hash=content_hash,
            raw_storage_uri=f"inline://source-resources/{resource.id}/{content_hash.replace(':', '-')}",
            captured_at=datetime.utcnow(),
            parser_version="byaan-native-text-v1",
            metadata_json={
                **metadata,
                "content_size": len(content.encode("utf-8")),
                "provider": provider,
                "content_preview_hash": hashlib.sha256(content[:1024].encode("utf-8")).hexdigest(),
            },
            status="captured",
        )
        session.add(snapshot)
        await session.flush()
        resource.latest_snapshot_id = snapshot.id

        provider_impl = get_knowledge_provider(provider)
        ingest_result = await provider_impl.ingest(
            session=session,
            resource=resource,
            snapshot=snapshot,
            content=content,
        )
        snapshot.status = "indexed" if ingest_result.index_status == "indexed" else "parsed"
        return snapshot

    async def _get_or_create_imported_resource(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        user_id: UUID | None,
        connection: SourceConnection,
        payload: SourceResourceImportRequest,
        selection,
    ) -> SourceResource:
        existing = await session.scalar(
            select(SourceResource)
            .where(
                SourceResource.tenant_id == tenant_id,
                SourceResource.source_connection_id == connection.id,
                SourceResource.external_id == selection.external_id,
                SourceResource.resource_type == selection.resource_type,
                SourceResource.selection_config_json == selection.selection_config,
            )
            .limit(1)
        )
        if existing:
            existing.name = selection.name or existing.name
            existing.source_url = selection.source_url or existing.source_url
            existing.parent_external_id = selection.parent_external_id
            existing.sync_mode = payload.sync_mode
            existing.sync_config_json = {
                **(existing.sync_config_json or {}),
                "schedule": payload.schedule,
            }
            return existing
        resource = SourceResource(
            tenant_id=tenant_id,
            source_connection_id=connection.id,
            resource_type=selection.resource_type,
            name=selection.name or selection.external_id,
            external_id=selection.external_id,
            source_url=selection.source_url,
            parent_external_id=selection.parent_external_id,
            selection_config_json={
                **selection.selection_config,
                **({"subresources": selection.subresources} if selection.subresources else {}),
                **({"metadata": selection.metadata} if selection.metadata else {}),
            },
            owner_id=user_id,
            visibility="workspace",
            sync_mode=payload.sync_mode,
            sync_config_json={"schedule": payload.schedule},
            status="pending",
        )
        session.add(resource)
        await session.flush()
        return resource

    async def _sync_resource_via_adapter(
        self,
        *,
        session: AsyncSession,
        resource: SourceResource,
        connection: SourceConnection,
        adapter: SourceConnectorAdapter,
    ) -> SourceSnapshot:
        previous_snapshot_id = resource.latest_snapshot_id
        sync_run = self._start_sync_run(resource=resource, trigger="manual")
        resource.status = "syncing"
        await session.flush()
        try:
            captured = await adapter.sync_resource(session=session, connection=connection, resource=resource)
            content_hash = stable_hash(captured.raw_bytes.decode("utf-8", errors="replace"))
            existing_snapshot = await session.scalar(
                select(SourceSnapshot)
                .where(
                    SourceSnapshot.tenant_id == resource.tenant_id,
                    SourceSnapshot.resource_id == resource.id,
                    SourceSnapshot.content_hash == content_hash,
                )
                .order_by(SourceSnapshot.captured_at.desc())
                .limit(1)
            )
            if existing_snapshot:
                if not (resource.sync_config_json or {}).get("projected_dataset_id"):
                    await self._maybe_project_dataset(
                        session=session,
                        resource=resource,
                        snapshot=existing_snapshot,
                        captured=captured,
                    )
                resource.latest_snapshot_id = existing_snapshot.id
                resource.status = "ready"
                self._finish_sync_run(resource=resource, sync_run=sync_run, status="succeeded", snapshot=existing_snapshot)
                await session.flush()
                return existing_snapshot

            snapshot = SourceSnapshot(
                tenant_id=resource.tenant_id,
                resource_id=resource.id,
                external_revision=captured.external_revision,
                content_hash=content_hash,
                raw_storage_uri=captured.raw_storage_uri,
                captured_at=datetime.utcnow(),
                parser_version=captured.parser_version,
                metadata_json={
                    **captured.metadata,
                    **self._captured_source_metadata(resource=resource, captured=captured),
                    "source_connection_id": str(connection.id),
                    "source_resource_id": str(resource.id),
                    "permission_snapshot": self._permission_snapshot(connection),
                    "sync_run": sync_run,
                    "raw_size": len(captured.raw_bytes),
                    "content_size": len(captured.content_text.encode("utf-8")),
                    "content_preview_hash": hashlib.sha256(captured.content_text[:1024].encode("utf-8")).hexdigest(),
                },
                status="captured",
            )
            session.add(snapshot)
            await session.flush()
            provider_impl = get_knowledge_provider(captured.provider)
            ingest_result = await provider_impl.ingest(
                session=session,
                resource=resource,
                snapshot=snapshot,
                content=captured.content_text,
            )
            snapshot.status = "indexed" if ingest_result.index_status == "indexed" else "parsed"
            await self._maybe_project_dataset(
                session=session,
                resource=resource,
                snapshot=snapshot,
                captured=captured,
            )
            resource.latest_snapshot_id = snapshot.id
            resource.status = "ready"
            self._finish_sync_run(resource=resource, sync_run=sync_run, status="succeeded", snapshot=snapshot)
            await session.flush()
            return snapshot
        except ConnectorError as exc:
            resource.latest_snapshot_id = previous_snapshot_id
            resource.status = self._status_for_connector_error(exc)
            self._finish_sync_run(resource=resource, sync_run=sync_run, status="failed", error=exc)
            await session.flush()
            raise
        except Exception as exc:
            resource.latest_snapshot_id = previous_snapshot_id
            connector_error = ConnectorError(
                f"Source sync failed: {exc}",
                code="source_sync_failed",
                permanent=False,
            )
            resource.status = "failed"
            self._finish_sync_run(resource=resource, sync_run=sync_run, status="failed", error=connector_error)
            await session.flush()
            raise connector_error from exc

    async def _capture_web_page(
        self,
        *,
        session: AsyncSession,
        resource: SourceResource,
        captured: WebCapturedPage,
    ) -> SourceSnapshot:
        content_hash = stable_hash(captured.raw_bytes.decode("utf-8", errors="replace"))
        existing_snapshot = await session.scalar(
            select(SourceSnapshot)
            .where(
                SourceSnapshot.tenant_id == resource.tenant_id,
                SourceSnapshot.resource_id == resource.id,
                SourceSnapshot.content_hash == content_hash,
            )
            .order_by(SourceSnapshot.captured_at.desc())
            .limit(1)
        )
        if existing_snapshot:
            resource.latest_snapshot_id = existing_snapshot.id
            resource.status = "ready"
            await session.flush()
            return existing_snapshot
        snapshot = SourceSnapshot(
            tenant_id=resource.tenant_id,
            resource_id=resource.id,
            external_revision=captured.external_revision,
            content_hash=content_hash,
            raw_storage_uri=captured.raw_storage_uri,
            captured_at=datetime.utcnow(),
            parser_version=captured.parser_version,
            metadata_json={
                **captured.metadata,
                "source_connection_id": str(resource.source_connection_id) if resource.source_connection_id else None,
                "source_resource_id": str(resource.id),
                "content_hash": content_hash,
                "content_size": len(captured.content_text.encode("utf-8")),
                "content_preview_hash": hashlib.sha256(captured.content_text[:1024].encode("utf-8")).hexdigest(),
            },
            status="captured",
        )
        session.add(snapshot)
        await session.flush()
        resource.latest_snapshot_id = snapshot.id
        provider_impl = get_knowledge_provider("byaan-native")
        ingest_result = await provider_impl.ingest(
            session=session,
            resource=resource,
            snapshot=snapshot,
            content=captured.content_text,
        )
        snapshot.status = "indexed" if ingest_result.index_status == "indexed" else "parsed"
        await session.flush()
        return snapshot

    async def _mark_resource_removed(self, *, session: AsyncSession, resource: SourceResource) -> None:
        deletion_marker = {
            "status": "removed",
            "source_resource_id": str(resource.id),
            "latest_snapshot_id": str(resource.latest_snapshot_id) if resource.latest_snapshot_id else None,
            "removed_at": datetime.utcnow().isoformat(),
        }
        resource.status = "failed"
        resource.sync_config_json = {
            **(resource.sync_config_json or {}),
            "deletion_marker": deletion_marker,
        }
        snapshot = SourceSnapshot(
            tenant_id=resource.tenant_id,
            resource_id=resource.id,
            external_revision=f"removed:{deletion_marker['removed_at']}",
            content_hash=stable_hash(json.dumps(deletion_marker, sort_keys=True)),
            raw_storage_uri=f"tombstone://source-resources/{resource.id}",
            captured_at=datetime.utcnow(),
            parser_version="source-resource-tombstone-v1",
            metadata_json={"deletion_marker": deletion_marker},
            status="captured",
        )
        session.add(snapshot)
        await session.flush()

    def _is_removed(self, resource: SourceResource) -> bool:
        marker = (resource.sync_config_json or {}).get("deletion_marker") or {}
        return marker.get("status") == "removed"

    async def _capture_uploaded_file(
        self,
        *,
        session: AsyncSession,
        resource: SourceResource,
        captured: CapturedSnapshot,
        filename: str,
        error: ConnectorError | None = None,
    ) -> SourceSnapshot:
        raw_hash = hashlib.sha256(captured.raw_bytes).hexdigest()
        content_hash = f"sha256:{raw_hash}"
        existing_snapshot = await session.scalar(
            select(SourceSnapshot)
            .where(
                SourceSnapshot.tenant_id == resource.tenant_id,
                SourceSnapshot.resource_id == resource.id,
                SourceSnapshot.content_hash == content_hash,
            )
            .order_by(SourceSnapshot.captured_at.desc())
            .limit(1)
        )
        if existing_snapshot:
            resource.latest_snapshot_id = existing_snapshot.id
            resource.status = self._status_for_connector_error(error) if error else "ready"
            await session.flush()
            return existing_snapshot

        safe_filename = self._safe_filename(filename)
        raw_dir = source_resource_directory(str(resource.id)) / "raw"
        raw_path = raw_dir / f"{raw_hash}_{safe_filename}"
        async with aiofiles.open(raw_path, "wb") as outfile:
            await outfile.write(captured.raw_bytes)
        snapshot = SourceSnapshot(
            tenant_id=resource.tenant_id,
            resource_id=resource.id,
            external_revision=captured.external_revision,
            content_hash=content_hash,
            raw_storage_uri=f"file://source-resources/{resource.id}/raw/{raw_path.name}",
            captured_at=datetime.utcnow(),
            parser_version=captured.parser_version,
            metadata_json={
                **captured.metadata,
                "raw_size": len(captured.raw_bytes),
                "content_size": len(captured.content_text.encode("utf-8")),
                "content_preview_hash": hashlib.sha256(captured.content_text[:1024].encode("utf-8")).hexdigest(),
            },
            status="failed" if error else "captured",
            error_json={"code": error.code, "message": str(error), "permanent": error.permanent} if error else None,
        )
        session.add(snapshot)
        await session.flush()
        resource.latest_snapshot_id = snapshot.id
        if error:
            await session.flush()
            return snapshot
        provider_impl = get_knowledge_provider(captured.provider)
        ingest_result = await provider_impl.ingest(
            session=session,
            resource=resource,
            snapshot=snapshot,
            content=captured.content_text,
        )
        snapshot.status = "indexed" if ingest_result.index_status == "indexed" else "parsed"
        await session.flush()
        return snapshot

    async def _maybe_project_dataset(
        self,
        *,
        session: AsyncSession,
        resource: SourceResource,
        snapshot: SourceSnapshot,
        captured: CapturedSnapshot,
    ) -> dict[str, Any] | None:
        files = self._projection_files_for(resource=resource, captured=captured)
        if not files:
            return None

        existing_dataset_id = (resource.sync_config_json or {}).get("projected_dataset_id") or (
            snapshot.metadata_json or {}
        ).get("projected_dataset_id")
        if existing_dataset_id:
            existing = await session.get(Dataset, existing_dataset_id)
            if existing is not None:
                projection = {
                    "dataset_id": str(existing.id),
                    "status": "ready",
                    "reused": True,
                }
                resource.sync_config_json = {
                    **(resource.sync_config_json or {}),
                    "projected_dataset_id": str(existing.id),
                    "projected_dataset": {
                        **((resource.sync_config_json or {}).get("projected_dataset") or {}),
                        **projection,
                    },
                }
                snapshot.metadata_json = {**(snapshot.metadata_json or {}), "projected_dataset": projection}
                return projection

        dataset = Dataset(
            tenant_id=resource.tenant_id,
            created_by=resource.owner_id,
            type="file",
            name=f"{resource.name} Dataset",
        )
        session.add(dataset)
        await session.flush()

        dataset_dir = dataset_directory(str(dataset.id))
        dataset.storage_path = str(dataset_dir)
        dataset.duckdb_path = str(dataset_dir / "duckdb" / "dataset.duckdb")
        file_records: list[File] = []
        projected_files: list[dict[str, Any]] = []

        try:
            for file_spec in files:
                storage = await DatasetStorageService.save_bytes(
                    dataset_id=str(dataset.id),
                    filename=file_spec["filename"],
                    data=file_spec["data"],
                )
                file_record = File(
                    tenant_id=resource.tenant_id,
                    name=file_spec["filename"],
                    content=None,
                    type=file_spec["file_type"],
                    size=storage.size,
                    dataset_id=dataset.id,
                    storage_path=str(storage.relative_path),
                    checksum=storage.checksum,
                    source_url=resource.source_url,
                )
                session.add(file_record)
                await session.flush()
                file_records.append(file_record)
                projected_files.append(
                    {
                        "file_id": str(file_record.id),
                        "filename": file_record.name,
                        "file_type": file_record.type,
                        "checksum": file_record.checksum,
                        "source_locator": file_spec.get("source_locator") or {},
                        "row_mappings": file_spec.get("row_mappings") or [],
                        **(
                            {"column_mappings": file_spec["column_mappings"]}
                            if "column_mappings" in file_spec
                            else {}
                        ),
                        **(
                            {"cell_mappings": file_spec["cell_mappings"]}
                            if "cell_mappings" in file_spec
                            else {}
                        ),
                        **(
                            {"coordinate_system": file_spec["coordinate_system"]}
                            if "coordinate_system" in file_spec
                            else {}
                        ),
                    }
                )

            dataset = await session.get(Dataset, dataset.id)
            schema = await DataFrameFileService.get_file_schema_multi(
                file_records,
                session=session,
                dataset=dataset,
                use_cache=False,
                save_to_cache=False,
            )
        except ConnectorError:
            await self._delete_projected_dataset(session=session, dataset=dataset, file_records=file_records)
            raise
        except Exception as exc:
            await self._delete_projected_dataset(session=session, dataset=dataset, file_records=file_records)
            raise ConnectorError(
                f"Dataset projection failed: {exc}",
                code="dataset_projection_failed",
                permanent=False,
            ) from exc

        try:
            dataset.schema_cache = json.dumps(schema)
            dataset.schema_updated_at = datetime.utcnow()
            projection = {
                "dataset_id": str(dataset.id),
                "status": "ready",
                "files_count": len(file_records),
                "file_types": sorted({file_record.type for file_record in file_records}),
                "schema_tables": sorted((schema.get("schema") or {}).keys()),
                "source_snapshot_id": str(snapshot.id),
                "files": projected_files,
            }
            resource.sync_config_json = {
                **(resource.sync_config_json or {}),
                "projected_dataset_id": str(dataset.id),
                "projected_dataset": projection,
            }
            snapshot.metadata_json = {
                **(snapshot.metadata_json or {}),
                "projected_dataset_id": str(dataset.id),
                "projected_dataset": projection,
                "projection_manifest": {
                    "source_snapshot_id": str(snapshot.id),
                    "dataset_id": str(dataset.id),
                    "files": projected_files,
                },
            }
            await session.flush()
            return projection
        except Exception:
            await self._delete_projected_dataset(session=session, dataset=dataset, file_records=file_records)
            raise

    def _projection_files_for(
        self,
        *,
        resource: SourceResource,
        captured: CapturedSnapshot,
    ) -> list[dict[str, Any]]:
        if resource.resource_type == "feishu_sheet":
            return self._projection_files_from_feishu_sheet(resource=resource, captured=captured)
        if resource.resource_type == "feishu_base":
            return self._projection_files_from_feishu_base(resource=resource, captured=captured)
        if resource.resource_type == "tos_object":
            return self._projection_files_from_tos_object(resource=resource, captured=captured)
        return []

    def _captured_source_metadata(
        self,
        *,
        resource: SourceResource,
        captured: CapturedSnapshot,
    ) -> dict[str, Any]:
        if resource.resource_type == "feishu_sheet":
            raw = self._json_from_bytes(captured.raw_bytes)
            sheets = []
            for entry in raw.get("sheets") or []:
                sheet = entry.get("sheet") or {}
                sheets.append(
                    {
                        "sheet_id": sheet.get("sheet_id"),
                        "title": sheet.get("title"),
                        "range": entry.get("range"),
                        "row_count": max(0, len(entry.get("values") or []) - 1),
                    }
                )
            return {"spreadsheet_token": resource.external_id, "sheets": sheets}

        if resource.resource_type == "feishu_base":
            raw = self._json_from_bytes(captured.raw_bytes)
            tables = []
            for entry in raw.get("tables") or []:
                table = entry.get("table") or {}
                records = ((entry.get("records") or {}).get("items") or [])
                fields = ((entry.get("fields") or {}).get("items") or [])
                tables.append(
                    {
                        "table_id": table.get("table_id"),
                        "name": table.get("name"),
                        "view_id": table.get("view_id") or entry.get("view_id"),
                        "record_count": len(records),
                        "field_ids": [field.get("field_id") for field in fields if field.get("field_id")],
                        "field_names": [field.get("field_name") for field in fields if field.get("field_name")],
                    }
                )
            return {"app_token": resource.external_id, "tables": tables}

        return {}

    def _projection_files_from_feishu_sheet(
        self,
        *,
        resource: SourceResource,
        captured: CapturedSnapshot,
    ) -> list[dict[str, Any]]:
        raw = self._json_from_bytes(captured.raw_bytes)
        files: list[dict[str, Any]] = []
        for index, sheet_entry in enumerate(raw.get("sheets") or [], start=1):
            sheet = sheet_entry.get("sheet") or {}
            values = sheet_entry.get("values") or []
            if not values:
                continue
            sheet_id = sheet.get("sheet_id") or f"sheet_{index}"
            title = sheet.get("title") or sheet_id
            filename = f"{self._safe_filename(resource.name)}__{self._safe_filename(str(title))}.csv"
            range_name = sheet_entry.get("range")
            start_row = self._range_start_row(range_name)
            start_column = self._range_start_column(range_name)
            files.append(
                {
                    "filename": filename,
                    "file_type": "csv",
                    "data": self._rows_to_csv_bytes(values),
                    "source_locator": {
                        "kind": "feishu_sheet",
                        "source_connection_id": str(resource.source_connection_id) if resource.source_connection_id else None,
                        "source_resource_id": str(resource.id),
                        "spreadsheet_token": resource.external_id,
                        "sheet_id": sheet_id,
                        "range": range_name,
                    },
                    "row_mappings": self._sheet_row_mappings(values=values, range_name=range_name),
                    "column_mappings": self._sheet_column_mappings(values=values, range_name=range_name),
                    "cell_mappings": self._sheet_cell_mappings(values=values, range_name=range_name),
                    "coordinate_system": {
                        "kind": "sheet_grid",
                        "range": range_name,
                        "header_row": start_row,
                        "first_data_row": start_row + 1,
                        "first_column": start_column,
                    },
                }
            )
        return files

    def _projection_files_from_feishu_base(
        self,
        *,
        resource: SourceResource,
        captured: CapturedSnapshot,
    ) -> list[dict[str, Any]]:
        raw = self._json_from_bytes(captured.raw_bytes)
        files: list[dict[str, Any]] = []
        for index, table_entry in enumerate(raw.get("tables") or [], start=1):
            table = table_entry.get("table") or {}
            fields = ((table_entry.get("fields") or {}).get("items") or [])
            field_names = [field.get("field_name") for field in fields if field.get("field_name")]
            if not field_names:
                continue
            rows = [field_names]
            for record in ((table_entry.get("records") or {}).get("items") or []):
                values = record.get("fields") or {}
                rows.append([self._cell_to_csv_value(values.get(name, "")) for name in field_names])
            if len(rows) <= 1:
                continue
            table_id = table.get("table_id") or f"table_{index}"
            view_id = table.get("view_id") or table_entry.get("view_id") or (resource.selection_config_json or {}).get("view_id")
            title = table.get("name") or table_id
            filename = f"{self._safe_filename(resource.name)}__{self._safe_filename(str(title))}.csv"
            records = ((table_entry.get("records") or {}).get("items") or [])
            field_mappings = [
                {
                    "dataset_column": field.get("field_name"),
                    "field_id": field.get("field_id"),
                    "field_name": field.get("field_name"),
                }
                for field in fields
                if field.get("field_name")
            ]
            files.append(
                {
                    "filename": filename,
                    "file_type": "csv",
                    "data": self._rows_to_csv_bytes(rows),
                    "source_locator": {
                        "kind": "feishu_base",
                        "source_connection_id": str(resource.source_connection_id) if resource.source_connection_id else None,
                        "source_resource_id": str(resource.id),
                        "app_token": resource.external_id,
                        "table_id": table_id,
                        "view_id": view_id,
                        "field_mappings": field_mappings,
                    },
                    "row_mappings": [
                        {
                            "dataset_row": row_index,
                            "record_id": record.get("record_id"),
                        }
                        for row_index, record in enumerate(records, start=1)
                    ],
                }
            )
        return files

    def _projection_files_from_tos_object(
        self,
        *,
        resource: SourceResource,
        captured: CapturedSnapshot,
    ) -> list[dict[str, Any]]:
        key = str((captured.metadata or {}).get("key") or resource.name or resource.external_id or "")
        file_type = self._file_type_from_name(key)
        if file_type is None:
            return []
        filename = key.rsplit("/", 1)[-1] or resource.name
        return [
            {
                "filename": filename,
                "file_type": file_type,
                "data": captured.raw_bytes,
                "source_locator": {
                    "kind": "tos_object",
                    "source_connection_id": str(resource.source_connection_id) if resource.source_connection_id else None,
                    "source_resource_id": str(resource.id),
                    "bucket": (captured.metadata or {}).get("bucket"),
                    "key": (captured.metadata or {}).get("key"),
                    "version_id": (captured.metadata or {}).get("version_id"),
                    "etag": (captured.metadata or {}).get("etag"),
                    "last_modified": (captured.metadata or {}).get("last_modified"),
                },
                "row_mappings": [],
            }
        ]

    async def _delete_projected_dataset(
        self,
        *,
        session: AsyncSession,
        dataset: Dataset,
        file_records: list[File],
    ) -> None:
        dataset_id = str(dataset.id)
        for file_record in file_records:
            await session.delete(file_record)
        await session.delete(dataset)
        await session.flush()
        await DatasetStorageService.delete_dataset(dataset_id)

    def _file_type_from_name(self, filename: str) -> str | None:
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if suffix == "csv":
            return "csv"
        if suffix in {"xlsx", "xls", "xlsm"}:
            return "excel"
        if suffix == "parquet":
            return "parquet"
        if suffix in {"json", "jsonl"}:
            return "json"
        return None

    def _json_from_bytes(self, raw_bytes: bytes) -> dict[str, Any]:
        try:
            value = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _rows_to_csv_bytes(self, rows: list[Any]) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        for row in rows:
            if isinstance(row, list):
                writer.writerow([self._cell_to_csv_value(value) for value in row])
            else:
                writer.writerow([self._cell_to_csv_value(row)])
        return buffer.getvalue().encode("utf-8")

    def _cell_to_csv_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value)

    def _sheet_row_mappings(self, *, values: list[Any], range_name: str | None) -> list[dict[str, int]]:
        if len(values) <= 1:
            return []
        start_row = self._range_start_row(range_name)
        return [
            {
                "dataset_row": index,
                "source_row": start_row + index,
            }
            for index in range(1, len(values))
        ]

    def _range_start_row(self, range_name: str | None) -> int:
        if not range_name:
            return 1
        range_part = range_name.split("!", 1)[-1]
        match = re.search(r"([A-Za-z]+)(\d+)", range_part)
        if not match:
            return 1
        return int(match.group(2))

    def _range_start_column(self, range_name: str | None) -> str:
        if not range_name:
            return "A"
        range_part = range_name.split("!", 1)[-1]
        match = re.search(r"([A-Za-z]+)(\d+)", range_part)
        if not match:
            return "A"
        return match.group(1).upper()

    def _sheet_column_mappings(self, *, values: list[Any], range_name: str | None) -> list[dict[str, str]]:
        if not values or not isinstance(values[0], list):
            return []
        start_column_number = self._column_number(self._range_start_column(range_name))
        header_row = self._range_start_row(range_name)
        mappings: list[dict[str, str]] = []
        for offset, value in enumerate(values[0]):
            dataset_column = self._cell_to_csv_value(value)
            if not dataset_column:
                continue
            source_column = self._column_name(start_column_number + offset)
            mappings.append(
                {
                    "dataset_column": dataset_column,
                    "source_column": source_column,
                    "header_cell": f"{source_column}{header_row}",
                }
            )
        return mappings

    def _sheet_cell_mappings(self, *, values: list[Any], range_name: str | None) -> list[dict[str, Any]]:
        if len(values) <= 1 or not isinstance(values[0], list):
            return []
        start_row = self._range_start_row(range_name)
        start_column_number = self._column_number(self._range_start_column(range_name))
        headers = [self._cell_to_csv_value(value) for value in values[0]]
        mappings: list[dict[str, Any]] = []
        for dataset_row, row in enumerate(values[1:], start=1):
            if not isinstance(row, list):
                row = [row]
            for offset, dataset_column in enumerate(headers):
                if not dataset_column or offset >= len(row):
                    continue
                source_column = self._column_name(start_column_number + offset)
                mappings.append(
                    {
                        "dataset_row": dataset_row,
                        "dataset_column": dataset_column,
                        "source_cell": f"{source_column}{start_row + dataset_row}",
                    }
                )
        return mappings

    def _column_number(self, column_name: str) -> int:
        value = 0
        for char in column_name.upper():
            if not ("A" <= char <= "Z"):
                continue
            value = value * 26 + (ord(char) - ord("A") + 1)
        return max(value, 1)

    def _column_name(self, index: int) -> str:
        index = max(1, index)
        result = ""
        while index:
            index, rem = divmod(index - 1, 26)
            result = chr(ord("A") + rem) + result
        return result

    def _start_sync_run(self, *, resource: SourceResource, trigger: str) -> dict[str, Any]:
        config = dict(resource.sync_config_json or {})
        attempt = int(config.get("sync_attempt") or 0) + 1
        run = {
            "status": "running",
            "allowed_statuses": list(self.sync_run_statuses),
            "trigger": trigger,
            "attempt": attempt,
            "started_at": datetime.utcnow().isoformat(),
            "finished_at": None,
            "error": None,
        }
        config["sync_attempt"] = attempt
        config["latest_sync_run"] = run
        config["sync_runs"] = [*list(config.get("sync_runs") or [])[-9:], run]
        resource.sync_config_json = config
        flag_modified(resource, "sync_config_json")
        return run

    def _finish_sync_run(
        self,
        *,
        resource: SourceResource,
        sync_run: dict[str, Any],
        status: str,
        snapshot: SourceSnapshot | None = None,
        error: ConnectorError | None = None,
    ) -> None:
        if status not in self.sync_run_statuses:
            raise ValueError(f"Unsupported source sync run status: {status}")
        sync_run.update(
            {
                "status": status,
                "finished_at": datetime.utcnow().isoformat(),
                "snapshot_id": str(snapshot.id) if snapshot else None,
                "checkpoint": self._sync_checkpoint(snapshot) if snapshot else None,
                "error": {"code": error.code, "message": str(error), "permanent": error.permanent} if error else None,
            }
        )
        config = dict(resource.sync_config_json or {})
        config["latest_sync_run"] = sync_run
        runs = list(config.get("sync_runs") or [])
        if runs:
            runs[-1] = sync_run
        else:
            runs = [sync_run]
        config["sync_runs"] = runs[-10:]
        resource.sync_config_json = config
        flag_modified(resource, "sync_config_json")

    def _sync_checkpoint(self, snapshot: SourceSnapshot) -> dict[str, Any]:
        return {
            "snapshot_id": str(snapshot.id),
            "external_revision": snapshot.external_revision,
            "content_hash": snapshot.content_hash,
            "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
        }

    def _permission_snapshot(self, connection: SourceConnection) -> dict[str, Any]:
        capabilities = connection.capabilities_json or {}
        return {
            "provider": connection.provider,
            "auth_mode": connection.auth_mode,
            "connection_status": connection.status,
            "external_account_id": connection.external_account_id,
            "created_by": str(connection.created_by) if connection.created_by else None,
            "scopes": capabilities.get("scopes") or capabilities.get("scope") or [],
        }

    def _safe_filename(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._") or "resource"

    def _status_for_connector_error(self, error: ConnectorError) -> str:
        if error.code in {"reauthorization_required", "invalid_state"}:
            return "reauthorization_required"
        if error.code == "permission_lost":
            return "permission_lost"
        if error.code == "source_unavailable":
            return "source_unavailable"
        if error.code == "large_file_confirmation_required":
            return "needs_confirmation"
        return "failed"

    def _snapshot_payload(self, snapshot: SourceSnapshot | None) -> dict[str, Any] | None:
        if snapshot is None:
            return None
        return {
            "id": snapshot.id,
            "resource_id": snapshot.resource_id,
            "external_revision": snapshot.external_revision,
            "content_hash": snapshot.content_hash,
            "raw_storage_uri": snapshot.raw_storage_uri,
            "captured_at": snapshot.captured_at,
            "parser_version": snapshot.parser_version,
            "metadata_json": snapshot.metadata_json,
            "status": snapshot.status,
            "error_json": snapshot.error_json,
        }

    async def _knowledge_resource_payload(
        self,
        *,
        session: AsyncSession,
        knowledge_resource: KnowledgeResource,
    ) -> dict[str, Any]:
        evidence_count = await session.scalar(
            select(func.count(EvidenceFragment.id)).where(
                EvidenceFragment.knowledge_resource_id == knowledge_resource.id
            )
        )
        return {
            "id": knowledge_resource.id,
            "resource_id": knowledge_resource.resource_id,
            "snapshot_id": knowledge_resource.snapshot_id,
            "provider": knowledge_resource.provider,
            "provider_resource_id": knowledge_resource.provider_resource_id,
            "parse_status": knowledge_resource.parse_status,
            "index_status": knowledge_resource.index_status,
            "completeness_score": knowledge_resource.completeness_score,
            "created_at": knowledge_resource.created_at,
            "evidence_count": int(evidence_count or 0),
        }

    def _evidence_payload(self, evidence: EvidenceFragment) -> dict[str, Any]:
        return {
            "id": evidence.id,
            "knowledge_resource_id": evidence.knowledge_resource_id,
            "snapshot_id": evidence.snapshot_id,
            "fragment_type": evidence.fragment_type,
            "title_path": evidence.title_path,
            "text": evidence.text,
            "locator_json": evidence.locator_json,
            "confidence": evidence.confidence,
            "content_hash": evidence.content_hash,
            "created_at": evidence.created_at,
        }
