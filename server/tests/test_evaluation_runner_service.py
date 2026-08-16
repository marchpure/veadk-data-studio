from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.evaluation import (
    EvaluationArtifact,
    EvaluationAssessment,
    EvaluationCase,
    EvaluationCaseRun,
    EvaluationRun,
    EvaluationSuite,
    EvaluationSuiteVersion,
)
from server.models.tenant import Tenant
from server.models.user import User
from server.services.evaluation import EvaluationService

pytestmark = pytest.mark.asyncio


async def _seed_published_suite_version_with_cases(test_session: AsyncSession) -> tuple[str, str]:
    owner = User(
        id=uuid4(),
        email=f"evaluation-runner-owner-{uuid4()}@example.test",
        hashed_password="fakehash",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    test_session.add(owner)
    await test_session.flush()
    tenant = Tenant(
        id=uuid4(),
        name="Evaluation Runner Tenant",
        slug=f"evaluation-runner-{uuid4().hex[:8]}",
        owner_id=owner.id,
        is_personal=True,
    )
    test_session.add(tenant)
    await test_session.flush()
    suite = EvaluationSuite(
        tenant_id=tenant.id,
        slug=f"eval-runner-suite-{uuid4()}",
        name="Runner suite",
        description="Evaluation runner smoke suite",
        owner_id=owner.id,
        lifecycle="published",
    )
    test_session.add(suite)
    await test_session.flush()
    version = EvaluationSuiteVersion(
        tenant_id=tenant.id,
        suite_id=suite.id,
        version_num=1,
        status="published",
        contract_version="evaluation.suite_version.v1",
        manifest_json={"contract_version": "evaluation.suite_version.v1", "suite_id": "runner", "version": 1},
        gate_policy_json={"version": "gate-policy.v1", "security_hard_fail": True, "min_overall_pass_rate": 1.0},
        case_count=2,
        content_hash="sha256:published",
        created_by=owner.id,
    )
    test_session.add(version)
    await test_session.flush()
    test_session.add_all(
        [
            EvaluationCase(
                tenant_id=tenant.id,
                suite_version_id=version.id,
                case_key="case-pass",
                title="Passing case",
                target_kinds_json=["semantic_model"],
                operation="answer_question",
                question="What is revenue?",
                expected_contract_json={"policy": {"security_hard_fail": True}},
                provenance_json={"source": "manual"},
                tags_json=["runner"],
                content_hash="sha256:case-pass",
                immutable=True,
            ),
            EvaluationCase(
                tenant_id=tenant.id,
                suite_version_id=version.id,
                case_key="case-security-fail",
                title="Security failure case",
                target_kinds_json=["semantic_model"],
                operation="answer_question",
                question="Read restricted text",
                expected_contract_json={"policy": {"security_hard_fail": True}},
                provenance_json={"source": "manual"},
                tags_json=["runner"],
                content_hash="sha256:case-fail",
                immutable=True,
            ),
        ]
    )
    await test_session.commit()
    return str(tenant.id), str(version.id)


def _complete_snapshot() -> dict:
    return {
        "contract_version": "evaluation.target_snapshot.v1",
        "target_kind": "semantic_model",
        "target_ref": "semantic_model:sales",
        "app": {
            "git_sha": "abc123",
            "image_digest": "sha256:image",
            "migration_revision": "add_evaluation_authoritative_model",
        },
        "source": {"snapshot_id": "source-1", "snapshot_hash": "sha256:source"},
        "semantic_model": {"version_id": "semver-1", "version_hash": "sha256:semantic"},
        "principal": {"tenant_id": "tenant-1", "actor_type": "agent", "actor_id": "agent-1", "scopes": []},
        "dataset": {"snapshot_id": "dataset-1", "snapshot_hash": "sha256:dataset"},
        "feature_flags": {"evaluation_governance": True},
        "time_fixture": {"now": "2026-08-16T00:00:00Z", "timezone": "UTC"},
    }


async def test_runner_claims_queued_run_persists_case_results_and_hard_fail_gate(
    test_session: AsyncSession,
) -> None:
    tenant_id, suite_version_id = await _seed_published_suite_version_with_cases(test_session)
    service = EvaluationService(test_session)
    run = await service.create_preflight_run(
        tenant_id=tenant_id,
        suite_version_id=suite_version_id,
        target_snapshot_payload=_complete_snapshot(),
        actor_id="agent-1",
        idempotency_key="runner-hard-fail",
    )
    assert run.status == "queued"

    claimed = await service.claim_next_run(tenant_id=tenant_id, worker_id="worker-a", lease_seconds=60)

    assert claimed is not None
    assert claimed.id == run.id
    assert claimed.status == "running"
    assert claimed.lease_holder == "worker-a"
    assert await service.claim_next_run(tenant_id=tenant_id, worker_id="worker-b", lease_seconds=60) is None

    completed = await service.complete_run_with_case_results(
        tenant_id=tenant_id,
        run_id=str(run.id),
        worker_id="worker-a",
        case_results=[
            {
                "case_key": "case-pass",
                "status": "passed",
                "assessments": [
                    {"category": "answer", "status": "passed", "score": "1.0", "hard_fail": False},
                ],
                "result": {"answer": "Revenue is 10"},
            },
            {
                "case_key": "case-security-fail",
                "status": "failed",
                "assessments": [
                    {"category": "security", "status": "failed", "score": "0.0", "hard_fail": True},
                ],
                "result": {"answer": "restricted free text count"},
            },
        ],
    )

    assert completed.status == "failed"
    assert completed.summary_json["total_cases"] == 2
    assert completed.summary_json["passed_cases"] == 1
    assert completed.summary_json["failed_cases"] == 1
    assert completed.summary_json["hard_failures"] == 1
    assert completed.summary_json["gate_decision"] == "failed"
    case_runs = (
        await test_session.execute(select(EvaluationCaseRun).where(EvaluationCaseRun.run_id == run.id))
    ).scalars().all()
    assert {case_run.status for case_run in case_runs} == {"passed", "failed"}
    assert all(case_run.immutable for case_run in case_runs)
    assessments = (
        await test_session.execute(select(EvaluationAssessment).join(EvaluationCaseRun).where(EvaluationCaseRun.run_id == run.id))
    ).scalars().all()
    assert any(assessment.category == "security" and assessment.hard_fail for assessment in assessments)
    saved = await test_session.get(EvaluationRun, run.id)
    assert saved is not None and saved.completed_at is not None


async def test_preflight_run_is_idempotent_for_suite_and_key(test_session: AsyncSession) -> None:
    tenant_id, suite_version_id = await _seed_published_suite_version_with_cases(test_session)
    service = EvaluationService(test_session)

    first = await service.create_preflight_run(
        tenant_id=tenant_id,
        suite_version_id=suite_version_id,
        target_snapshot_payload=_complete_snapshot(),
        actor_id="agent-1",
        idempotency_key="same-key",
    )
    second = await service.create_preflight_run(
        tenant_id=tenant_id,
        suite_version_id=suite_version_id,
        target_snapshot_payload=_complete_snapshot(),
        actor_id="agent-1",
        idempotency_key="same-key",
    )

    assert second.id == first.id
    runs = (
        await test_session.execute(
            select(EvaluationRun).where(
                EvaluationRun.suite_version_id == suite_version_id,
                EvaluationRun.idempotency_key == "same-key",
            )
        )
    ).scalars().all()
    assert len(runs) == 1


async def test_runner_reclaims_expired_lease_rejects_stale_worker_and_persists_artifact(
    test_session: AsyncSession,
) -> None:
    tenant_id, suite_version_id = await _seed_published_suite_version_with_cases(test_session)
    service = EvaluationService(test_session)
    run = await service.create_preflight_run(
        tenant_id=tenant_id,
        suite_version_id=suite_version_id,
        target_snapshot_payload=_complete_snapshot(),
        actor_id="agent-1",
        idempotency_key="reclaim-stop",
    )
    first_claim = await service.claim_next_run(tenant_id=tenant_id, worker_id="worker-a", lease_seconds=-1)
    assert first_claim is not None and first_claim.lease_holder == "worker-a"

    reclaimed = await service.claim_next_run(tenant_id=tenant_id, worker_id="worker-b", lease_seconds=60)

    assert reclaimed is not None
    assert reclaimed.id == run.id
    assert reclaimed.lease_holder == "worker-b"
    assert reclaimed.attempt == 2
    with pytest.raises(ValueError, match="leased by this worker"):
        await service.heartbeat_run(tenant_id=tenant_id, run_id=str(run.id), worker_id="worker-a", lease_seconds=60)

    await service.request_run_stop(tenant_id=tenant_id, run_id=str(run.id), actor_id="owner")
    stopped = await service.heartbeat_run(tenant_id=tenant_id, run_id=str(run.id), worker_id="worker-b", lease_seconds=60)

    assert stopped.stop_requested is True
    assert stopped.status == "canceled"
    artifact = await service.record_run_artifact(
        tenant_id=tenant_id,
        run_id=str(run.id),
        artifact_type="runner.log",
        uri="memory://runner-log",
        content={"events": ["claimed", "stopped"]},
    )
    assert artifact.immutable is True
    saved_artifact = await test_session.get(EvaluationArtifact, artifact.id)
    assert saved_artifact is not None
    assert saved_artifact.content_hash.startswith("sha256:")
