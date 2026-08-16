from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.models.evaluation import EvaluationRun, EvaluationSuiteVersion
from server.repositories.evaluation import EvaluationRepository
from server.schemas.evaluation import EvaluationTargetSnapshot


class EvaluationService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = EvaluationRepository(session)

    async def create_preflight_run(
        self,
        *,
        tenant_id: str | UUID,
        suite_version_id: str | UUID,
        target_snapshot_payload: dict[str, Any],
        actor_id: str,
        idempotency_key: str | None = None,
        actor_type: str = "agent",
    ) -> EvaluationRun:
        suite_version = await self._require_suite_version(
            tenant_id=tenant_id,
            suite_version_id=suite_version_id,
        )
        target_snapshot = EvaluationTargetSnapshot.model_validate(target_snapshot_payload)
        blockers = target_snapshot.required_pin_blockers()
        snapshot_json = target_snapshot.model_dump(mode="json")
        snapshot = await self._repo.create_target_snapshot(
            tenant_id=tenant_id,
            target_kind=target_snapshot.target_kind,
            target_ref=target_snapshot.target_ref,
            contract_version=target_snapshot.contract_version,
            snapshot_json=snapshot_json,
            pin_digest=self._digest(snapshot_json),
            blockers_json=blockers,
        )
        status = "blocked" if blockers else "queued"
        run = await self._repo.create_run(
            tenant_id=tenant_id,
            suite_version_id=suite_version.id,
            target_snapshot_id=snapshot.id,
            status=status,
            actor_type=actor_type,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            preflight_blockers_json=blockers,
        )
        await self._repo.create_audit_event(
            tenant_id=tenant_id,
            suite_id=suite_version.suite_id,
            suite_version_id=suite_version.id,
            run_id=run.id,
            actor_type=actor_type,
            actor_id=actor_id,
            action="evaluation.run.preflight",
            outcome=status,
            details_json={"blockers": blockers},
        )
        await self._session.commit()
        await self._session.refresh(run)
        return run

    async def publish_suite_version(
        self,
        *,
        tenant_id: str | UUID,
        suite_version_id: str | UUID,
        actor_id: str,
        actor_type: str = "human",
    ) -> EvaluationSuiteVersion:
        suite_version = await self._require_suite_version(
            tenant_id=tenant_id,
            suite_version_id=suite_version_id,
        )
        suite_version.status = "published"
        suite_version.published_at = datetime.utcnow()
        await self._repo.create_audit_event(
            tenant_id=tenant_id,
            suite_id=suite_version.suite_id,
            suite_version_id=suite_version.id,
            run_id=None,
            actor_type=actor_type,
            actor_id=actor_id,
            action="evaluation.suite_version.publish",
            outcome="published",
            details_json={},
        )
        await self._session.commit()
        await self._session.refresh(suite_version)
        return suite_version

    async def patch_suite_version_manifest(
        self,
        *,
        tenant_id: str | UUID,
        suite_version_id: str | UUID,
        patch: dict[str, Any],
    ) -> EvaluationSuiteVersion:
        suite_version = await self._require_suite_version(
            tenant_id=tenant_id,
            suite_version_id=suite_version_id,
        )
        if suite_version.status == "published":
            raise ValueError("published evaluation suite version manifest is immutable")
        suite_version.manifest_json = {**suite_version.manifest_json, **patch}
        suite_version.content_hash = self._digest(suite_version.manifest_json)
        await self._session.commit()
        await self._session.refresh(suite_version)
        return suite_version

    async def _require_suite_version(
        self,
        *,
        tenant_id: str | UUID,
        suite_version_id: str | UUID,
    ) -> EvaluationSuiteVersion:
        suite_version = await self._repo.get_suite_version(
            tenant_id=tenant_id,
            suite_version_id=suite_version_id,
        )
        if suite_version is None:
            raise ValueError("evaluation suite version not found")
        return suite_version

    @staticmethod
    def _digest(payload: Any) -> str:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()
