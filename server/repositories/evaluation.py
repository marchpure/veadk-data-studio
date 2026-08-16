from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.evaluation import (
    EvaluationAuditEvent,
    EvaluationRun,
    EvaluationSuiteVersion,
    EvaluationTargetSnapshot,
)


class EvaluationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_suite_version(
        self,
        *,
        tenant_id: str | UUID,
        suite_version_id: str | UUID,
    ) -> EvaluationSuiteVersion | None:
        result = await self._session.execute(
            select(EvaluationSuiteVersion).where(
                EvaluationSuiteVersion.tenant_id == tenant_id,
                EvaluationSuiteVersion.id == suite_version_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_target_snapshot(
        self,
        *,
        tenant_id: str | UUID,
        target_kind: str,
        target_ref: str,
        contract_version: str,
        snapshot_json: dict,
        pin_digest: str,
        blockers_json: list[str],
    ) -> EvaluationTargetSnapshot:
        snapshot = EvaluationTargetSnapshot(
            tenant_id=tenant_id,
            target_kind=target_kind,
            target_ref=target_ref,
            contract_version=contract_version,
            snapshot_json=snapshot_json,
            pin_digest=pin_digest,
            blockers_json=blockers_json,
        )
        self._session.add(snapshot)
        await self._session.flush()
        return snapshot

    async def create_run(
        self,
        *,
        tenant_id: str | UUID,
        suite_version_id: str | UUID,
        target_snapshot_id: str | UUID,
        status: str,
        actor_type: str,
        actor_id: str,
        idempotency_key: str | None,
        preflight_blockers_json: list[str],
    ) -> EvaluationRun:
        run = EvaluationRun(
            tenant_id=tenant_id,
            suite_version_id=suite_version_id,
            target_snapshot_id=target_snapshot_id,
            status=status,
            actor_type=actor_type,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            preflight_blockers_json=preflight_blockers_json,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def create_audit_event(
        self,
        *,
        tenant_id: str | UUID,
        suite_id: str | UUID | None,
        suite_version_id: str | UUID | None,
        run_id: str | UUID | None,
        actor_type: str,
        actor_id: str,
        action: str,
        outcome: str,
        details_json: dict,
    ) -> EvaluationAuditEvent:
        event = EvaluationAuditEvent(
            tenant_id=tenant_id,
            suite_id=suite_id,
            suite_version_id=suite_version_id,
            run_id=run_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            outcome=outcome,
            details_json=details_json,
        )
        self._session.add(event)
        await self._session.flush()
        return event
