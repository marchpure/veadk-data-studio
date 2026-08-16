from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.dashboard import Dashboard, DashboardAsset, DashboardAuditEvent
from server.repositories.dashboard import DashboardRepository
from server.schemas.dashboard import DashboardManifest
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


class DashboardService:
    """Governed Dashboard lifecycle service shared by REST and MCP wrappers."""

    @staticmethod
    def canonical_json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def digest_payload(payload: dict[str, Any]) -> str:
        return "sha256:" + hashlib.sha256(DashboardService.canonical_json(payload).encode("utf-8")).hexdigest()

    @staticmethod
    def validate_manifest_payload(payload: dict[str, Any]) -> dict[str, Any]:
        manifest = DashboardManifest.model_validate(payload)
        return manifest.model_dump(mode="json", by_alias=True)

    async def create_asset_draft(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        actor_id: UUID,
        manifest_payload: dict[str, Any],
        slug: str,
        notebook_id: UUID | None = None,
        description: str = "",
        tags: list[str] | None = None,
        change_summary: str = "Create structured dashboard draft",
        actor_type: str = "human",
    ) -> DashboardAsset:
        if notebook_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="notebook_id is required for P0 drafts")

        repo = DashboardRepository(session)
        existing = await repo.get_asset_by_slug(tenant_id, slug)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dashboard asset slug already exists")

        manifest = self.validate_manifest_payload(manifest_payload)
        content_hash = self.digest_payload(manifest)
        now_etag = self.digest_payload({"manifest": content_hash, "slug": slug, "actor": str(actor_id)})
        asset = DashboardAsset(
            tenant_id=tenant_id,
            notebook_id=notebook_id,
            slug=slug,
            name=manifest["title"],
            description=description or manifest.get("description", ""),
            owner_id=actor_id,
            tags_json=tags or [],
            lifecycle="draft",
            access_policy_json=manifest["access_policy"],
            freshness_policy_json=manifest["freshness_policy"],
            etag=now_etag,
        )
        session.add(asset)
        await session.flush()

        version = Dashboard(
            tenant_id=tenant_id,
            notebook_id=notebook_id,
            asset_id=asset.id,
            version_num=1,
            html_content="",
            manifest_schema_version=manifest["schema_version"],
            manifest_json=manifest,
            content_hash=content_hash,
            status="draft",
            created_by=actor_id,
            actor_type=actor_type,
            change_summary=change_summary,
            pinned_model_versions_json=self._manifest_model_versions(manifest),
            pinned_source_snapshots_json=self._manifest_source_snapshots(manifest),
            validation_result_json=self.validation_summary(manifest),
            migration_state=manifest["migration"]["state"],
            is_published_immutable=False,
        )
        session.add(version)
        await session.flush()

        asset.current_draft_version_id = version.id
        await self._audit(
            session=session,
            tenant_id=tenant_id,
            asset_id=asset.id,
            version_id=version.id,
            actor_type=actor_type,
            actor_id=str(actor_id),
            action="dashboard.draft.create",
            outcome="success",
            after_digest=content_hash,
        )
        await session.commit()
        await session.refresh(asset)
        return asset

    async def patch_draft(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        asset_id: UUID,
        actor_id: UUID,
        manifest_payload: dict[str, Any],
        base_etag: str,
        change_summary: str,
        actor_type: str = "human",
    ) -> Dashboard:
        repo = DashboardRepository(session)
        asset = await repo.get_asset(asset_id, tenant_id)
        if not asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard asset not found")
        if asset.etag != base_etag:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "etag_conflict", "current_etag": asset.etag},
            )
        if not asset.current_draft_version_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dashboard has no editable draft")

        current_draft = await repo.get_asset_version(
            tenant_id=tenant_id,
            asset_id=asset_id,
            version_id=asset.current_draft_version_id,
        )
        if not current_draft:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard draft not found")

        manifest = self.validate_manifest_payload(manifest_payload)
        content_hash = self.digest_payload(manifest)
        next_version = await repo.get_asset_next_version_num(asset_id)
        version = Dashboard(
            tenant_id=tenant_id,
            notebook_id=current_draft.notebook_id,
            asset_id=asset.id,
            version_num=next_version,
            html_content=current_draft.html_content,
            manifest_schema_version=manifest["schema_version"],
            manifest_json=manifest,
            content_hash=content_hash,
            status="draft",
            created_by=actor_id,
            actor_type=actor_type,
            change_summary=change_summary,
            pinned_model_versions_json=self._manifest_model_versions(manifest),
            pinned_source_snapshots_json=self._manifest_source_snapshots(manifest),
            validation_result_json=self.validation_summary(manifest),
            migration_state=manifest["migration"]["state"],
            is_published_immutable=False,
        )
        session.add(version)
        await session.flush()

        asset.current_draft_version_id = version.id
        asset.name = manifest["title"]
        asset.description = manifest.get("description", asset.description)
        asset.access_policy_json = manifest["access_policy"]
        asset.freshness_policy_json = manifest["freshness_policy"]
        asset.etag = self.digest_payload({"manifest": content_hash, "base_etag": base_etag, "version": next_version})
        await self._audit(
            session=session,
            tenant_id=tenant_id,
            asset_id=asset.id,
            version_id=version.id,
            actor_type=actor_type,
            actor_id=str(actor_id),
            action="dashboard.draft.patch",
            outcome="success",
            before_digest=current_draft.content_hash,
            after_digest=content_hash,
        )
        await session.commit()
        await session.refresh(version)
        return version

    async def publish(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        asset_id: UUID,
        actor_id: UUID,
        base_etag: str,
        change_summary: str,
        actor_type: str = "human",
    ) -> Dashboard:
        repo = DashboardRepository(session)
        asset = await repo.get_asset(asset_id, tenant_id)
        if not asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard asset not found")
        if asset.etag != base_etag:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "etag_conflict", "current_etag": asset.etag},
            )
        if not asset.current_draft_version_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dashboard has no validated draft")

        draft = await repo.get_asset_version(
            tenant_id=tenant_id,
            asset_id=asset_id,
            version_id=asset.current_draft_version_id,
        )
        if not draft or not draft.manifest_json:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard draft not found")

        manifest = self.validate_manifest_payload(draft.manifest_json)
        validation = self.validation_summary(manifest)
        if validation["blockers"]:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "validation_blocked", **validation})

        draft.status = "published"
        draft.change_summary = change_summary
        draft.is_published_immutable = True
        draft.validation_result_json = validation
        asset.published_version_id = draft.id
        asset.lifecycle = "published"
        asset.etag = self.digest_payload({"published": str(draft.id), "content_hash": draft.content_hash})
        await self._audit(
            session=session,
            tenant_id=tenant_id,
            asset_id=asset.id,
            version_id=draft.id,
            actor_type=actor_type,
            actor_id=str(actor_id),
            action="dashboard.publish",
            outcome="success",
            after_digest=draft.content_hash,
        )
        await session.commit()
        await session.refresh(draft)
        return draft

    @staticmethod
    def validation_summary(manifest: dict[str, Any]) -> dict[str, Any]:
        blockers: list[str] = []
        warnings: list[str] = []
        if not manifest.get("data_views"):
            blockers.append("manifest must contain at least one data view")
        if not manifest.get("tiles"):
            blockers.append("manifest must contain at least one tile")
        if manifest.get("migration", {}).get("state") == "legacy_unstructured":
            blockers.append("legacy_unstructured dashboards cannot publish structured versions")
        if any(binding.get("readiness") != "published" for binding in manifest.get("semantic_bindings", [])):
            blockers.append("all semantic bindings must pin published model versions")
        saved_query_views = [
            data_view["id"] for data_view in manifest.get("data_views", []) if data_view.get("kind") == "saved_query"
        ]
        if saved_query_views:
            warnings.append(f"saved_query compatibility views require lineage review: {', '.join(saved_query_views)}")
        return {"valid": not blockers, "blockers": blockers, "warnings": warnings, "validated_at": datetime.utcnow().isoformat()}

    @staticmethod
    def _manifest_model_versions(manifest: dict[str, Any]) -> dict[str, str]:
        return {
            binding["model_slug"]: binding["model_version"]
            for binding in manifest.get("semantic_bindings", [])
            if binding.get("model_slug") and binding.get("model_version")
        }

    @staticmethod
    def _manifest_source_snapshots(manifest: dict[str, Any]) -> list[str]:
        snapshots: list[str] = []
        for binding in manifest.get("semantic_bindings", []):
            snapshots.extend(str(snapshot_id) for snapshot_id in binding.get("source_snapshot_ids", []))
        return sorted(set(snapshots))

    async def _audit(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        asset_id: UUID,
        version_id: UUID,
        actor_type: str,
        actor_id: str,
        action: str,
        outcome: str,
        before_digest: str | None = None,
        after_digest: str | None = None,
        correlation_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        session.add(
            DashboardAuditEvent(
                tenant_id=tenant_id,
                asset_id=asset_id,
                version_id=version_id,
                actor_type=actor_type,
                actor_id=actor_id,
                action=action,
                outcome=outcome,
                before_digest=before_digest,
                after_digest=after_digest,
                correlation_id=correlation_id,
                details_json=details or {},
            )
        )
