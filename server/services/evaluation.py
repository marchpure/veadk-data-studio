from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.models.evaluation import EvaluationArtifact, EvaluationRun, EvaluationSuiteVersion
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
        if idempotency_key:
            existing = await self._repo.get_run_by_idempotency_key(
                tenant_id=tenant_id,
                suite_version_id=suite_version.id,
                idempotency_key=idempotency_key,
            )
            if existing is not None:
                return existing
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

    async def heartbeat_run(
        self,
        *,
        tenant_id: str | UUID,
        run_id: str | UUID,
        worker_id: str,
        lease_seconds: int,
    ) -> EvaluationRun:
        run = await self._require_worker_run(
            tenant_id=tenant_id,
            run_id=run_id,
            worker_id=worker_id,
        )
        now = datetime.utcnow()
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(seconds=lease_seconds)
        outcome = "running"
        if run.stop_requested:
            run.status = "canceled"
            run.completed_at = now
            run.summary_json = {**(run.summary_json or {}), "gate_decision": "canceled", "stop_requested": True}
            outcome = "canceled"
        suite_version = await self._require_suite_version(
            tenant_id=tenant_id,
            suite_version_id=run.suite_version_id,
        )
        await self._repo.create_audit_event(
            tenant_id=tenant_id,
            suite_id=suite_version.suite_id,
            suite_version_id=suite_version.id,
            run_id=run.id,
            actor_type="worker",
            actor_id=worker_id,
            action="evaluation.run.heartbeat",
            outcome=outcome,
            details_json={"lease_seconds": lease_seconds},
        )
        await self._session.commit()
        await self._session.refresh(run)
        return run

    async def request_run_stop(
        self,
        *,
        tenant_id: str | UUID,
        run_id: str | UUID,
        actor_id: str,
        actor_type: str = "human",
    ) -> EvaluationRun:
        run = await self._repo.get_run(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise ValueError("evaluation run not found")
        run.stop_requested = True
        suite_version = await self._require_suite_version(
            tenant_id=tenant_id,
            suite_version_id=run.suite_version_id,
        )
        await self._repo.create_audit_event(
            tenant_id=tenant_id,
            suite_id=suite_version.suite_id,
            suite_version_id=suite_version.id,
            run_id=run.id,
            actor_type=actor_type,
            actor_id=actor_id,
            action="evaluation.run.stop_request",
            outcome="requested",
            details_json={},
        )
        await self._session.commit()
        await self._session.refresh(run)
        return run

    async def record_run_artifact(
        self,
        *,
        tenant_id: str | UUID,
        run_id: str | UUID,
        artifact_type: str,
        uri: str,
        content: Any,
    ) -> EvaluationArtifact:
        run = await self._repo.get_run(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise ValueError("evaluation run not found")
        content_hash = self._digest(content)
        artifact = await self._repo.create_artifact(
            tenant_id=tenant_id,
            run_id=run.id,
            case_run_id=None,
            artifact_type=artifact_type,
            uri=uri,
            content_hash=content_hash,
            metadata_json={"content_hash": content_hash},
        )
        suite_version = await self._require_suite_version(
            tenant_id=tenant_id,
            suite_version_id=run.suite_version_id,
        )
        await self._repo.create_audit_event(
            tenant_id=tenant_id,
            suite_id=suite_version.suite_id,
            suite_version_id=suite_version.id,
            run_id=run.id,
            actor_type="service",
            actor_id="evaluation-service",
            action="evaluation.artifact.record",
            outcome="created",
            details_json={"artifact_type": artifact_type, "uri": uri, "content_hash": content_hash},
        )
        await self._session.commit()
        await self._session.refresh(artifact)
        return artifact

    async def claim_next_run(
        self,
        *,
        tenant_id: str | UUID,
        worker_id: str,
        lease_seconds: int,
    ) -> EvaluationRun | None:
        now = datetime.utcnow()
        run = await self._repo.get_next_claimable_run(tenant_id=tenant_id, now=now)
        if run is None:
            return None
        previous_holder = run.lease_holder
        suite_version = await self._require_suite_version(
            tenant_id=tenant_id,
            suite_version_id=run.suite_version_id,
        )
        run.status = "running"
        run.lease_holder = worker_id
        run.lease_expires_at = now + timedelta(seconds=lease_seconds)
        run.heartbeat_at = now
        run.started_at = run.started_at or now
        run.attempt += 1 if previous_holder and previous_holder != worker_id else 0
        await self._repo.create_audit_event(
            tenant_id=tenant_id,
            suite_id=suite_version.suite_id,
            suite_version_id=run.suite_version_id,
            run_id=run.id,
            actor_type="worker",
            actor_id=worker_id,
            action="evaluation.run.claim",
            outcome="running",
            details_json={"lease_seconds": lease_seconds},
        )
        await self._session.commit()
        await self._session.refresh(run)
        return run

    async def complete_run_with_case_results(
        self,
        *,
        tenant_id: str | UUID,
        run_id: str | UUID,
        worker_id: str,
        case_results: list[dict[str, Any]],
    ) -> EvaluationRun:
        run = await self._repo.get_run(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise ValueError("evaluation run not found")
        if run.status != "running" or run.lease_holder != worker_id:
            raise ValueError("evaluation run is not leased by this worker")

        suite_version = await self._require_suite_version(
            tenant_id=tenant_id,
            suite_version_id=run.suite_version_id,
        )
        cases = await self._repo.list_cases_for_suite_version(
            tenant_id=tenant_id,
            suite_version_id=run.suite_version_id,
        )
        cases_by_key = {case.case_key: case for case in cases}
        result_keys = {str(result.get("case_key")) for result in case_results}
        if result_keys != set(cases_by_key):
            missing = sorted(set(cases_by_key) - result_keys)
            unknown = sorted(result_keys - set(cases_by_key))
            raise ValueError(f"case results do not match suite version cases: missing={missing} unknown={unknown}")

        now = datetime.utcnow()
        hard_failures = 0
        passed_cases = 0
        failed_cases = 0
        for result in case_results:
            case = cases_by_key[str(result["case_key"])]
            status = str(result.get("status") or "failed")
            if status == "passed":
                passed_cases += 1
            else:
                failed_cases += 1
            result_payload = dict(result.get("result") or {})
            error_payload = dict(result.get("error") or {})
            case_run = await self._repo.create_case_run(
                tenant_id=tenant_id,
                run_id=run.id,
                case_id=case.id,
                status=status,
                attempt=run.attempt,
                input_digest=self._digest(case.expected_contract_json),
                output_digest=self._digest(result_payload),
                result_json=result_payload,
                error_json=error_payload,
                immutable=True,
                started_at=now,
                completed_at=now,
            )
            for assessment_payload in result.get("assessments") or []:
                hard_fail = bool(assessment_payload.get("hard_fail"))
                if hard_fail:
                    hard_failures += 1
                await self._repo.create_assessment(
                    tenant_id=tenant_id,
                    case_run_id=case_run.id,
                    category=str(assessment_payload.get("category") or "overall"),
                    status=str(assessment_payload.get("status") or status),
                    score=assessment_payload.get("score"),
                    hard_fail=hard_fail,
                    details_json=dict(assessment_payload.get("details") or {}),
                )

        total_cases = len(cases)
        pass_rate = passed_cases / total_cases if total_cases else 0.0
        gate_policy = suite_version.gate_policy_json or {}
        security_hard_fail = bool(gate_policy.get("security_hard_fail", True))
        min_overall_pass_rate = float(gate_policy.get("min_overall_pass_rate", 1.0))
        gate_failed = (security_hard_fail and hard_failures > 0) or pass_rate < min_overall_pass_rate
        run.status = "failed" if gate_failed else "passed"
        run.completed_at = now
        run.summary_json = {
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": failed_cases,
            "pass_rate": pass_rate,
            "hard_failures": hard_failures,
            "gate_decision": "failed" if gate_failed else "passed",
            "security_hard_fail": security_hard_fail,
            "min_overall_pass_rate": min_overall_pass_rate,
        }
        await self._repo.create_audit_event(
            tenant_id=tenant_id,
            suite_id=suite_version.suite_id,
            suite_version_id=suite_version.id,
            run_id=run.id,
            actor_type="worker",
            actor_id=worker_id,
            action="evaluation.run.complete",
            outcome=run.status,
            details_json=run.summary_json,
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

    async def _require_worker_run(
        self,
        *,
        tenant_id: str | UUID,
        run_id: str | UUID,
        worker_id: str,
    ) -> EvaluationRun:
        run = await self._repo.get_run(tenant_id=tenant_id, run_id=run_id)
        if run is None:
            raise ValueError("evaluation run not found")
        if run.status != "running" or run.lease_holder != worker_id:
            raise ValueError("evaluation run is not leased by this worker")
        return run

    @staticmethod
    def _digest(payload: Any) -> str:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()
