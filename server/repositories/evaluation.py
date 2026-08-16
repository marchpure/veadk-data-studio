from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.evaluation import (
    EvaluationArtifact,
    EvaluationAssessment,
    EvaluationAuditEvent,
    EvaluationCase,
    EvaluationCaseRun,
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

    async def get_run(
        self,
        *,
        tenant_id: str | UUID,
        run_id: str | UUID,
    ) -> EvaluationRun | None:
        result = await self._session.execute(
            select(EvaluationRun).where(
                EvaluationRun.tenant_id == tenant_id,
                EvaluationRun.id == run_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_run_by_idempotency_key(
        self,
        *,
        tenant_id: str | UUID,
        suite_version_id: str | UUID,
        idempotency_key: str,
    ) -> EvaluationRun | None:
        result = await self._session.execute(
            select(EvaluationRun).where(
                EvaluationRun.tenant_id == tenant_id,
                EvaluationRun.suite_version_id == suite_version_id,
                EvaluationRun.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def get_next_claimable_run(
        self,
        *,
        tenant_id: str | UUID,
        now: datetime,
    ) -> EvaluationRun | None:
        result = await self._session.execute(
            select(EvaluationRun)
            .where(
                EvaluationRun.tenant_id == tenant_id,
                EvaluationRun.preflight_blockers_json == [],
                (
                    (EvaluationRun.status == "queued")
                    | ((EvaluationRun.status == "running") & (EvaluationRun.lease_expires_at < now))
                ),
            )
            .order_by(EvaluationRun.created_at, EvaluationRun.id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_cases_for_suite_version(
        self,
        *,
        tenant_id: str | UUID,
        suite_version_id: str | UUID,
    ) -> list[EvaluationCase]:
        result = await self._session.execute(
            select(EvaluationCase)
            .where(
                EvaluationCase.tenant_id == tenant_id,
                EvaluationCase.suite_version_id == suite_version_id,
            )
            .order_by(EvaluationCase.case_key)
        )
        return list(result.scalars().all())

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

    async def create_case_run(
        self,
        *,
        tenant_id: str | UUID,
        run_id: str | UUID,
        case_id: str | UUID,
        status: str,
        attempt: int,
        input_digest: str,
        output_digest: str,
        result_json: dict,
        error_json: dict,
        immutable: bool,
        started_at: datetime,
        completed_at: datetime,
    ) -> EvaluationCaseRun:
        case_run = EvaluationCaseRun(
            tenant_id=tenant_id,
            run_id=run_id,
            case_id=case_id,
            status=status,
            attempt=attempt,
            input_digest=input_digest,
            output_digest=output_digest,
            result_json=result_json,
            error_json=error_json,
            immutable=immutable,
            started_at=started_at,
            completed_at=completed_at,
        )
        self._session.add(case_run)
        await self._session.flush()
        return case_run

    async def create_assessment(
        self,
        *,
        tenant_id: str | UUID,
        case_run_id: str | UUID,
        category: str,
        status: str,
        score: str | None,
        hard_fail: bool,
        details_json: dict,
    ) -> EvaluationAssessment:
        assessment = EvaluationAssessment(
            tenant_id=tenant_id,
            case_run_id=case_run_id,
            category=category,
            status=status,
            score=score,
            hard_fail=hard_fail,
            details_json=details_json,
            immutable=True,
        )
        self._session.add(assessment)
        await self._session.flush()
        return assessment

    async def create_artifact(
        self,
        *,
        tenant_id: str | UUID,
        run_id: str | UUID | None,
        case_run_id: str | UUID | None,
        artifact_type: str,
        uri: str,
        content_hash: str,
        metadata_json: dict,
    ) -> EvaluationArtifact:
        artifact = EvaluationArtifact(
            tenant_id=tenant_id,
            run_id=run_id,
            case_run_id=case_run_id,
            artifact_type=artifact_type,
            uri=uri,
            content_hash=content_hash,
            metadata_json=metadata_json,
            immutable=True,
        )
        self._session.add(artifact)
        await self._session.flush()
        return artifact

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
