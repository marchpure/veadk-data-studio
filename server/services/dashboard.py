from __future__ import annotations

import hashlib
import json
from datetime import datetime
from html import escape
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.dashboard import Dashboard, DashboardAsset, DashboardAuditEvent, DashboardRun
from server.repositories.dashboard import DashboardRepository
from server.schemas.dashboard import DashboardManifest
from server.schemas.query import QueryFilter as SavedQueryFilter
from server.services.query_service import QueryService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


class DashboardService:
    """Governed Dashboard lifecycle service shared by REST and MCP wrappers."""

    PATCHABLE_MANIFEST_PATHS = {
        "title",
        "description",
        "audience",
        "semantic_bindings",
        "data_views",
        "filters",
        "layout",
        "tiles",
        "actions",
        "freshness_policy",
        "access_policy",
        "migration",
    }

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

    @staticmethod
    def apply_manifest_patch(manifest_payload: dict[str, Any], patch_operations: list[dict[str, Any]]) -> dict[str, Any]:
        manifest = json.loads(DashboardService.canonical_json(manifest_payload))
        for operation in patch_operations:
            op = operation.get("op")
            path = operation.get("path")
            if op not in {"add", "replace", "remove"} or not isinstance(path, str):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported dashboard patch operation")
            target = DashboardService._manifest_patch_target(path)
            if target not in DashboardService.PATCHABLE_MANIFEST_PATHS:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Dashboard patch path is not allowed")
            manifest = DashboardService._apply_patch_operation(manifest, op, path, operation.get("value"))
        return DashboardService.validate_manifest_payload(manifest)

    @staticmethod
    def _manifest_patch_target(path: str) -> str:
        if not path.startswith("/"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dashboard patch path must be absolute")
        parts = [part for part in path.split("/") if part]
        if not parts:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Dashboard manifest root patch is not allowed")
        return parts[0].replace("~1", "/").replace("~0", "~")

    @staticmethod
    def _apply_patch_operation(payload: dict[str, Any], op: str, path: str, value: Any = None) -> dict[str, Any]:
        parts = [part.replace("~1", "/").replace("~0", "~") for part in path.split("/") if part]
        parent: Any = payload
        for part in parts[:-1]:
            if isinstance(parent, list):
                parent = parent[int(part)]
            elif isinstance(parent, dict) and part in parent:
                parent = parent[part]
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dashboard patch path does not exist")

        leaf = parts[-1]
        if isinstance(parent, list):
            index = len(parent) if leaf == "-" else int(leaf)
            if op == "remove":
                parent.pop(index)
            elif op == "add":
                parent.insert(index, value)
            else:
                parent[index] = value
        elif isinstance(parent, dict):
            if op == "remove":
                if leaf not in parent:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dashboard patch path does not exist")
                parent.pop(leaf)
            elif op in {"add", "replace"}:
                if op == "replace" and leaf not in parent:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dashboard patch path does not exist")
                parent[leaf] = value
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dashboard patch path does not exist")
        return payload

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

    async def apply_draft_patch(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        asset_id: UUID,
        actor_id: UUID,
        base_etag: str,
        patch_operations: list[dict[str, Any]],
        change_summary: str,
        actor_type: str = "human",
    ) -> Dashboard:
        repo = DashboardRepository(session)
        asset = await repo.get_asset(asset_id, tenant_id)
        if not asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard asset not found")
        if not asset.current_draft_version_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dashboard has no editable draft")
        draft = await repo.get_asset_version(
            tenant_id=tenant_id,
            asset_id=asset_id,
            version_id=asset.current_draft_version_id,
        )
        if not draft or not draft.manifest_json:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard draft not found")
        manifest = self.apply_manifest_patch(draft.manifest_json, patch_operations)
        return await self.patch_draft(
            session=session,
            tenant_id=tenant_id,
            asset_id=asset_id,
            actor_id=actor_id,
            manifest_payload=manifest,
            base_etag=base_etag,
            change_summary=change_summary,
            actor_type=actor_type,
        )

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

    async def reload_dashboard(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        asset_id: UUID,
        actor_id: UUID,
        base_etag: str,
        change_summary: str,
        semantic_model_versions: dict[str, str] | None = None,
        source_snapshot_ids: list[str] | None = None,
        actor_type: str = "human",
    ) -> tuple[Dashboard, dict[str, Any]]:
        repo = DashboardRepository(session)
        asset = await repo.get_asset(asset_id, tenant_id)
        if not asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard asset not found")
        if asset.etag != base_etag:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "etag_conflict", "current_etag": asset.etag},
            )
        if not asset.published_version_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dashboard has no published version to reload")

        published = await repo.get_asset_version(
            tenant_id=tenant_id,
            asset_id=asset_id,
            version_id=asset.published_version_id,
        )
        if not published or not published.manifest_json:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Published dashboard version not found")

        manifest = json.loads(self.canonical_json(published.manifest_json))
        semantic_diff = self._apply_reload_targets(
            manifest=manifest,
            base_version=published,
            semantic_model_versions=semantic_model_versions or {},
            source_snapshot_ids=source_snapshot_ids,
        )
        manifest.setdefault("provenance", {})["updated_at"] = datetime.utcnow().isoformat()
        manifest.setdefault("migration", {})["state"] = "needs_review"
        manifest = self.validate_manifest_payload(manifest)
        validation = self.validation_summary(manifest)
        semantic_diff["blockers"] = validation["blockers"]
        semantic_diff["warnings"] = [*semantic_diff["warnings"], *validation["warnings"]]

        content_hash = self.digest_payload(manifest)
        next_version = await repo.get_asset_next_version_num(asset_id)
        version = Dashboard(
            tenant_id=tenant_id,
            notebook_id=published.notebook_id,
            asset_id=asset.id,
            version_num=next_version,
            html_content=published.html_content,
            manifest_schema_version=manifest["schema_version"],
            manifest_json=manifest,
            content_hash=content_hash,
            status="draft",
            created_by=actor_id,
            actor_type=actor_type,
            change_summary=change_summary,
            pinned_model_versions_json=self._manifest_model_versions(manifest),
            pinned_source_snapshots_json=self._manifest_source_snapshots(manifest),
            validation_result_json={**validation, "semantic_diff": semantic_diff},
            migration_state=manifest["migration"]["state"],
            is_published_immutable=False,
        )
        session.add(version)
        await session.flush()

        semantic_diff["draft_version_id"] = str(version.id)
        semantic_diff["draft_version_num"] = version.version_num
        version.validation_result_json = {**validation, "semantic_diff": semantic_diff}
        asset.current_draft_version_id = version.id
        asset.lifecycle = "in_review"
        asset.etag = self.digest_payload({"reload": str(version.id), "base_etag": base_etag, "content_hash": content_hash})
        asset.health_summary_json = {
            **(asset.health_summary_json or {}),
            "freshness": "unknown",
            "last_reload_draft_version_id": str(version.id),
            "last_reload_base_version_id": str(published.id),
            "semantic_diff": semantic_diff,
        }
        await self._audit(
            session=session,
            tenant_id=tenant_id,
            asset_id=asset.id,
            version_id=version.id,
            actor_type=actor_type,
            actor_id=str(actor_id),
            action="dashboard.reload",
            outcome="blocked" if validation["blockers"] else "success",
            before_digest=published.content_hash,
            after_digest=content_hash,
            details={"semantic_diff": semantic_diff},
        )
        await session.commit()
        await session.refresh(version)
        return version, semantic_diff

    async def export_dashboard_html(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        asset_id: UUID,
        actor_id: UUID,
        actor_type: str = "human",
        version_num: int | None = None,
        correlation_id: str | None = None,
    ) -> tuple[str, str]:
        repo = DashboardRepository(session)
        asset = await repo.get_asset(asset_id, tenant_id)
        if not asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard asset not found")

        if version_num is not None:
            version = await repo.get_asset_version_by_num(
                tenant_id=tenant_id,
                asset_id=asset_id,
                version_num=version_num,
            )
        elif asset.published_version_id:
            version = await repo.get_asset_version(
                tenant_id=tenant_id,
                asset_id=asset_id,
                version_id=asset.published_version_id,
            )
        else:
            version = None
        if not version:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard version not found")
        if version.status == "draft":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Draft dashboards must be published before export")

        if not version.manifest_json:
            if not version.html_content:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dashboard version has no exportable content")
            html_content = version.html_content
            artifact_kind = "legacy_html"
        else:
            manifest = self.validate_manifest_payload(version.manifest_json)
            html_content = self._render_structured_export_html(asset, version, manifest)
            artifact_kind = "structured_manifest_html"

        await self._audit(
            session=session,
            tenant_id=tenant_id,
            asset_id=asset.id,
            version_id=version.id,
            actor_type=actor_type,
            actor_id=str(actor_id),
            action="dashboard.export",
            outcome="success",
            correlation_id=correlation_id,
            after_digest=version.content_hash,
            details={"version_num": version.version_num, "artifact_kind": artifact_kind},
        )
        await session.commit()
        filename = f"{asset.slug or asset.id}-v{version.version_num}.html"
        return html_content, filename

    async def query_dashboard(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        asset_id: UUID,
        actor_id: str,
        actor_type: str,
        filters: dict[str, Any] | None = None,
        data_view_ids: list[str] | None = None,
        mode: str = "live",
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if mode != "live":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="pinned_snapshot artifacts are not available")

        repo = DashboardRepository(session)
        asset = await repo.get_asset(asset_id, tenant_id)
        if not asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard asset not found")
        if not asset.published_version_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dashboard has no published version")

        version = await repo.get_asset_version(
            tenant_id=tenant_id,
            asset_id=asset_id,
            version_id=asset.published_version_id,
        )
        if not version or not version.manifest_json:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Published dashboard version not found")

        manifest = self.validate_manifest_payload(version.manifest_json)
        selected_data_views = self._select_data_views(manifest, data_view_ids)
        normalized_filters = self._normalize_filters(filters or {})
        filter_digest = self.digest_payload(normalized_filters)
        execution_plan_digest = self.digest_payload(
            {
                "dashboard_version_id": str(version.id),
                "data_view_ids": [view["id"] for view in selected_data_views],
                "pinned_versions": {
                    "semantic_models": version.pinned_model_versions_json,
                    "source_snapshots": version.pinned_source_snapshots_json,
                },
            }
        )
        started_at = datetime.utcnow()
        view_results = []
        for data_view in selected_data_views:
            view_results.append(
                await self._execute_data_view(
                    session=session,
                    data_view=data_view,
                    normalized_filters=normalized_filters,
                )
            )

        completed_at = datetime.utcnow()
        overall_freshness = self._overall_freshness(view_results)
        run_payload = {
            "contract_version": "dashboard.run.v1",
            "run_id": str(uuid4()),
            "dashboard_id": str(asset.id),
            "dashboard_version_id": str(version.id),
            "actor_type": actor_type,
            "actor_id": actor_id,
            "correlation_id": correlation_id,
            "idempotency_key": idempotency_key,
            "mode": mode,
            "normalized_filters": normalized_filters,
            "filter_digest": filter_digest,
            "pinned_versions": {
                "semantic_models": version.pinned_model_versions_json,
                "source_snapshots": version.pinned_source_snapshots_json,
            },
            "execution_plan_digest": execution_plan_digest,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "overall_freshness": overall_freshness,
            "views": view_results,
            "warnings": self._run_warnings(view_results),
            "errors": [view["error"] for view in view_results if view.get("error")],
        }
        run = DashboardRun(
            id=UUID(run_payload["run_id"]),
            tenant_id=tenant_id,
            asset_id=asset.id,
            version_id=version.id,
            actor_type=actor_type,
            actor_id=actor_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            mode=mode,
            normalized_filters_json=normalized_filters,
            filter_digest=filter_digest,
            pinned_versions_json=run_payload["pinned_versions"],
            execution_plan_digest=execution_plan_digest,
            overall_freshness=overall_freshness,
            result_manifest_json=run_payload,
            warnings_json=run_payload["warnings"],
            errors_json=run_payload["errors"],
            started_at=started_at,
            completed_at=completed_at,
        )
        session.add(run)
        await self._audit(
            session=session,
            tenant_id=tenant_id,
            asset_id=asset.id,
            version_id=version.id,
            actor_type=actor_type,
            actor_id=actor_id,
            action="dashboard.query",
            outcome="success" if not run_payload["errors"] else "partial",
            correlation_id=correlation_id,
            details={"run_id": str(run.id), "data_view_ids": [view["data_view_id"] for view in view_results]},
        )
        await session.commit()
        return run_payload

    async def preview_dashboard(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        asset_id: UUID,
        actor_id: str,
        actor_type: str,
        filters: dict[str, Any] | None = None,
        data_view_ids: list[str] | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        repo = DashboardRepository(session)
        asset = await repo.get_asset(asset_id, tenant_id)
        if not asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard asset not found")
        if not asset.current_draft_version_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dashboard has no editable draft")

        version = await repo.get_asset_version(
            tenant_id=tenant_id,
            asset_id=asset_id,
            version_id=asset.current_draft_version_id,
        )
        if not version or not version.manifest_json:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard draft not found")

        manifest = self.validate_manifest_payload(version.manifest_json)
        selected_data_views = self._select_data_views(manifest, data_view_ids)
        normalized_filters = self._normalize_filters(filters or {})
        filter_digest = self.digest_payload(normalized_filters)
        execution_plan_digest = self.digest_payload(
            {
                "dashboard_version_id": str(version.id),
                "data_view_ids": [view["id"] for view in selected_data_views],
                "preview": True,
            }
        )
        started_at = datetime.utcnow()
        view_results = [
            await self._execute_data_view(
                session=session,
                data_view=data_view,
                normalized_filters=normalized_filters,
            )
            for data_view in selected_data_views
        ]
        completed_at = datetime.utcnow()
        run_payload = {
            "contract_version": "dashboard.run.v1",
            "run_id": str(uuid4()),
            "dashboard_id": str(asset.id),
            "dashboard_version_id": str(version.id),
            "actor_type": actor_type,
            "actor_id": actor_id,
            "correlation_id": correlation_id,
            "mode": "live",
            "preview": True,
            "normalized_filters": normalized_filters,
            "filter_digest": filter_digest,
            "pinned_versions": {
                "semantic_models": version.pinned_model_versions_json,
                "source_snapshots": version.pinned_source_snapshots_json,
            },
            "execution_plan_digest": execution_plan_digest,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "overall_freshness": self._overall_freshness(view_results),
            "views": view_results,
            "warnings": self._run_warnings(view_results),
            "errors": [view["error"] for view in view_results if view.get("error")],
        }
        await self._audit(
            session=session,
            tenant_id=tenant_id,
            asset_id=asset.id,
            version_id=version.id,
            actor_type=actor_type,
            actor_id=actor_id,
            action="dashboard.preview",
            outcome="success" if not run_payload["errors"] else "partial",
            correlation_id=correlation_id,
            details={"run_id": run_payload["run_id"], "data_view_ids": [view["data_view_id"] for view in view_results]},
        )
        await session.commit()
        return run_payload

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

    def _select_data_views(self, manifest: dict[str, Any], data_view_ids: list[str] | None) -> list[dict[str, Any]]:
        views_by_id = {data_view["id"]: data_view for data_view in manifest.get("data_views", [])}
        if not data_view_ids:
            return list(views_by_id.values())
        missing = [data_view_id for data_view_id in data_view_ids if data_view_id not in views_by_id]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="One or more data views are not available for this dashboard",
            )
        return [views_by_id[data_view_id] for data_view_id in data_view_ids]

    @staticmethod
    def _normalize_filters(filters: dict[str, Any]) -> dict[str, Any]:
        return {key: filters[key] for key in sorted(filters)}

    async def _execute_data_view(
        self,
        *,
        session: AsyncSession,
        data_view: dict[str, Any],
        normalized_filters: dict[str, Any],
    ) -> dict[str, Any]:
        if data_view["kind"] == "saved_query":
            return await self._execute_saved_query_view(
                session=session,
                data_view=data_view,
                normalized_filters=normalized_filters,
            )
        return {
            "data_view_id": data_view["id"],
            "status": "blocked",
            "result": None,
            "schema": data_view.get("output_schema", []),
            "row_count": 0,
            "cached": False,
            "stale": False,
            "warnings": [f"{data_view['kind']} execution is not wired in this slice"],
            "error": {
                "code": "execution_not_wired",
                "message": "Data view execution is not available yet",
                "retryable": False,
            },
            "evidence": data_view.get("evidence", []),
            "lineage": data_view.get("lineage", []),
        }

    async def _execute_saved_query_view(
        self,
        *,
        session: AsyncSession,
        data_view: dict[str, Any],
        normalized_filters: dict[str, Any],
    ) -> dict[str, Any]:
        saved_query = data_view["saved_query"]
        filter_payload = self._filters_for_data_view(data_view, normalized_filters)
        result = await QueryService.execute_saved_query(
            session,
            saved_query["query_id"],
            filters=filter_payload,
        )
        success = bool(result.get("success"))
        rows = result.get("data") if success else None
        row_count = len(rows) if isinstance(rows, list) else (1 if isinstance(rows, dict) else 0)
        view_result = {
            "data_view_id": data_view["id"],
            "status": "success" if success and row_count > 0 else "empty" if success else "error",
            "result": rows,
            "schema": data_view.get("output_schema", []),
            "row_count": row_count,
            "cached": bool(result.get("cached", False)),
            "stale": bool(result.get("stale", False)),
            "as_of": datetime.utcnow().isoformat(),
            "warnings": [f"saved_query compatibility binding: {saved_query['compatibility_reason']}"],
            "evidence": data_view.get("evidence", []),
            "lineage": data_view.get("lineage") or saved_query.get("lineage", []),
        }
        if not success:
            view_result["error"] = {
                "code": "saved_query_failed",
                "message": "Dashboard data view execution failed",
                "retryable": True,
            }
        return view_result

    @staticmethod
    def _filters_for_data_view(data_view: dict[str, Any], normalized_filters: dict[str, Any]) -> list[SavedQueryFilter] | None:
        filter_fields = set(data_view.get("filter_fields") or [])
        if not filter_fields:
            return None
        filters: list[SavedQueryFilter] = []
        for field in sorted(filter_fields):
            if field in normalized_filters:
                filters.append(SavedQueryFilter(field=field, operator="eq", value=normalized_filters[field]))
        return filters or None

    @staticmethod
    def _overall_freshness(view_results: list[dict[str, Any]]) -> str:
        if any(view.get("status") in {"error", "blocked", "permission_denied"} for view in view_results):
            return "partial" if any(view.get("status") in {"success", "empty", "stale"} for view in view_results) else "blocked"
        if any(view.get("stale") for view in view_results):
            return "stale"
        return "fresh"

    @staticmethod
    def _run_warnings(view_results: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        for view in view_results:
            warnings.extend(str(warning) for warning in view.get("warnings", []))
        return warnings

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

    def _apply_reload_targets(
        self,
        *,
        manifest: dict[str, Any],
        base_version: Dashboard,
        semantic_model_versions: dict[str, str],
        source_snapshot_ids: list[str] | None,
    ) -> dict[str, Any]:
        diff: dict[str, Any] = {
            "base_version_id": str(base_version.id),
            "base_version_num": base_version.version_num,
            "draft_version_id": None,
            "draft_version_num": None,
            "model_version_changes": [],
            "source_snapshot_changes": [],
            "filter_changes": [],
            "tile_changes": [],
            "policy_changes": [],
            "warnings": [],
            "blockers": [],
        }
        for binding in manifest.get("semantic_bindings", []):
            requested_model_version = semantic_model_versions.get(binding["id"]) or semantic_model_versions.get(
                binding["model_slug"]
            )
            if requested_model_version and requested_model_version != binding["model_version"]:
                diff["model_version_changes"].append(
                    {
                        "binding_id": binding["id"],
                        "model_slug": binding["model_slug"],
                        "from": binding["model_version"],
                        "to": requested_model_version,
                    }
                )
                binding["model_version"] = requested_model_version

            if source_snapshot_ids is not None:
                next_snapshots = sorted(set(source_snapshot_ids))
                current_snapshots = sorted(set(binding.get("source_snapshot_ids", [])))
                if next_snapshots != current_snapshots:
                    diff["source_snapshot_changes"].append(
                        {
                            "binding_id": binding["id"],
                            "model_slug": binding["model_slug"],
                            "from": current_snapshots,
                            "to": next_snapshots,
                        }
                    )
                    binding["source_snapshot_ids"] = next_snapshots

        if not diff["model_version_changes"] and not diff["source_snapshot_changes"]:
            diff["warnings"].append(
                "No semantic model or source snapshot changes were supplied; reload draft captures the current published baseline for review."
            )
        return diff

    @staticmethod
    def _render_structured_export_html(asset: DashboardAsset, version: Dashboard, manifest: dict[str, Any]) -> str:
        title = escape(manifest.get("title") or asset.name)
        description = escape(manifest.get("description") or asset.description or "")
        bindings = "".join(
            "<li>"
            f"<strong>{escape(binding.get('model_slug', 'model'))}</strong> "
            f"version {escape(binding.get('model_version', 'unknown'))}"
            f"<span>{escape(', '.join(binding.get('source_snapshot_ids', [])) or 'no source snapshot')}</span>"
            "</li>"
            for binding in manifest.get("semantic_bindings", [])
        )
        filters = "".join(
            "<li>"
            f"{escape(dashboard_filter.get('label', dashboard_filter.get('id', 'filter')))}"
            f"<span>{escape(dashboard_filter.get('field', ''))} / {escape(dashboard_filter.get('filter_type', ''))}</span>"
            "</li>"
            for dashboard_filter in manifest.get("filters", [])
        )
        data_views_by_id = {data_view.get("id"): data_view for data_view in manifest.get("data_views", [])}
        tiles = "".join(
            DashboardService._render_export_tile(tile, data_views_by_id.get(tile.get("data_view_id")))
            for tile in manifest.get("tiles", [])
        )
        manifest_json = escape(json.dumps(manifest, sort_keys=True, ensure_ascii=False))
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{ margin: 0; font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0d0f11; color: #eef2f3; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px; }}
    header {{ border-bottom: 1px solid #293037; padding-bottom: 20px; margin-bottom: 20px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    h2 {{ font-size: 14px; text-transform: uppercase; color: #9aa4ac; }}
    p, li, td, th {{ color: #cdd3d8; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }}
    .panel {{ border: 1px solid #293037; border-radius: 8px; background: #14181c; padding: 16px; }}
    .tile h3 {{ margin: 0 0 8px; font-size: 16px; }}
    .meta {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }}
    .pill {{ border: 1px solid #3a444d; border-radius: 999px; padding: 4px 8px; color: #cdd3d8; font-size: 12px; }}
    li span {{ display: block; color: #818c95; font-size: 12px; margin-top: 4px; }}
    code {{ white-space: pre-wrap; word-break: break-word; color: #d6dde2; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{title}</h1>
      <p>{description}</p>
      <div class="meta">
        <span class="pill">dashboard.manifest.v1</span>
        <span class="pill">version {version.version_num}</span>
        <span class="pill">{escape(version.status)}</span>
        <span class="pill">{escape(version.content_hash or "no hash")}</span>
      </div>
    </header>
    <section class="grid">
      <div class="panel"><h2>Semantic Bindings</h2><ul>{bindings or "<li>No bindings</li>"}</ul></div>
      <div class="panel"><h2>Filters</h2><ul>{filters or "<li>No global filters</li>"}</ul></div>
    </section>
    <section>
      <h2>Tiles</h2>
      <div class="grid">{tiles or '<div class="panel">No tiles</div>'}</div>
    </section>
    <section class="panel">
      <h2>Canonical Manifest</h2>
      <script type="application/json" id="dashboard-manifest">{manifest_json}</script>
      <code>{manifest_json}</code>
    </section>
  </main>
</body>
</html>"""

    @staticmethod
    def _render_export_tile(tile: dict[str, Any], data_view: dict[str, Any] | None) -> str:
        title = escape(tile.get("title", tile.get("id", "Tile")))
        question = escape(tile.get("business_question", ""))
        tile_type = escape(tile.get("tile_type", "tile"))
        data_view_id = escape(tile.get("data_view_id") or "none")
        data_view_question = escape((data_view or {}).get("question", "No data view binding"))
        fields = ", ".join(field.get("name", "") for field in (data_view or {}).get("output_schema", []))
        return (
            '<article class="panel tile">'
            f"<h3>{title}</h3>"
            f"<p>{question}</p>"
            '<div class="meta">'
            f'<span class="pill">{tile_type}</span>'
            f'<span class="pill">{data_view_id}</span>'
            "</div>"
            f"<p>{data_view_question}</p>"
            f"<p>{escape(fields or 'No output schema')}</p>"
            "</article>"
        )

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
