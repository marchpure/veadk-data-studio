from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.evaluation import (
    AdvisorChangeSet,
    EvaluationArtifact,
    EvaluationCase,
    EvaluationRun,
    EvaluationSuite,
    EvaluationSuiteVersion,
    EvaluationTargetSnapshot,
)
from server.models.tenant import Tenant
from server.models.tenant_member import TenantMember, TenantRole
from server.models.user import User

pytestmark = pytest.mark.asyncio


async def _seed_suite_version(test_session: AsyncSession) -> tuple[Tenant, User, EvaluationSuiteVersion]:
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    owner = await test_session.get(User, tenant.owner_id)
    assert owner is not None
    suite = EvaluationSuite(
        tenant_id=tenant.id,
        slug=f"rest-eval-suite-{uuid4()}",
        name="REST Evaluation suite",
        description="Evaluation suite exposed through REST",
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
        manifest_json={"contract_version": "evaluation.suite_version.v1", "suite_id": "rest", "version": 1},
        gate_policy_json={"version": "gate-policy.v1", "security_hard_fail": True, "min_overall_pass_rate": 1.0},
        case_count=2,
        content_hash="sha256:rest-suite",
        created_by=owner.id,
    )
    test_session.add(version)
    await test_session.flush()
    test_session.add_all(
        [
            EvaluationCase(
                tenant_id=tenant.id,
                suite_version_id=version.id,
                case_key="case-one",
                title="Case one",
                target_kinds_json=["semantic_model"],
                operation="answer_question",
                question="What is revenue?",
                expected_contract_json={"policy": {"security_hard_fail": True}},
                provenance_json={"source": "manual"},
                tags_json=["rest"],
                content_hash="sha256:case-one",
                immutable=True,
            ),
            EvaluationCase(
                tenant_id=tenant.id,
                suite_version_id=version.id,
                case_key="case-two",
                title="Case two",
                target_kinds_json=["semantic_model"],
                operation="answer_question",
                question="What is margin?",
                expected_contract_json={"policy": {"security_hard_fail": True}},
                provenance_json={"source": "manual"},
                tags_json=["rest"],
                content_hash="sha256:case-two",
                immutable=True,
            ),
        ]
    )
    await test_session.commit()
    return tenant, owner, version


def _complete_snapshot(tenant_id: str) -> dict:
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
        "principal": {"tenant_id": tenant_id, "actor_type": "agent", "actor_id": "agent-1", "scopes": []},
        "dataset": {"snapshot_id": "dataset-1", "snapshot_hash": "sha256:dataset"},
        "feature_flags": {"evaluation_governance": True},
        "time_fixture": {"now": "2026-08-16T00:00:00Z", "timezone": "UTC"},
    }


async def _seed_completed_run(
    test_session: AsyncSession,
    *,
    tenant_id,
    suite_version_id,
    gate_decision: str,
) -> EvaluationRun:
    snapshot = EvaluationTargetSnapshot(
        tenant_id=tenant_id,
        target_kind="semantic_model",
        target_ref=f"semantic_model:{gate_decision}",
        contract_version="evaluation.target_snapshot.v1",
        snapshot_json={"target_ref": f"semantic_model:{gate_decision}"},
        pin_digest=f"sha256:{gate_decision}",
        blockers_json=[],
    )
    test_session.add(snapshot)
    await test_session.flush()
    run = EvaluationRun(
        tenant_id=tenant_id,
        suite_version_id=suite_version_id,
        target_snapshot_id=snapshot.id,
        status="passed" if gate_decision == "passed" else "failed",
        actor_type="agent",
        actor_id="agent-1",
        preflight_blockers_json=[],
        summary_json={"gate_decision": gate_decision},
    )
    test_session.add(run)
    await test_session.flush()
    return run


async def test_evaluation_run_rest_lifecycle_artifact_and_completion(
    test_client,
    test_session: AsyncSession,
) -> None:
    tenant, _owner, suite_version = await _seed_suite_version(test_session)

    preflight_response = await test_client.post(
        "/api/evaluation/runs/preflight",
        json={
            "suite_version_id": str(suite_version.id),
            "target_snapshot": _complete_snapshot(str(tenant.id)),
            "idempotency_key": "rest-lifecycle",
            "actor_type": "agent",
            "actor_id": "agent-1",
        },
    )
    assert preflight_response.status_code == 202
    run_payload = preflight_response.json()["data"]
    assert run_payload["status"] == "queued"
    assert run_payload["preflight_blockers"] == []
    run_id = run_payload["id"]

    retry_response = await test_client.post(
        "/api/evaluation/runs/preflight",
        json={
            "suite_version_id": str(suite_version.id),
            "target_snapshot": _complete_snapshot(str(tenant.id)),
            "idempotency_key": "rest-lifecycle",
            "actor_type": "agent",
            "actor_id": "agent-1",
        },
    )
    assert retry_response.status_code == 202
    assert retry_response.json()["data"]["id"] == run_id

    claim_response = await test_client.post(
        "/api/evaluation/runs/claim",
        json={"worker_id": "worker-rest", "lease_seconds": 60},
    )
    assert claim_response.status_code == 200
    claimed = claim_response.json()["data"]
    assert claimed["id"] == run_id
    assert claimed["status"] == "running"
    assert claimed["lease_holder"] == "worker-rest"

    heartbeat_response = await test_client.post(
        f"/api/evaluation/runs/{run_id}/heartbeat",
        json={"worker_id": "worker-rest", "lease_seconds": 60},
    )
    assert heartbeat_response.status_code == 200
    assert heartbeat_response.json()["data"]["status"] == "running"

    artifact_response = await test_client.post(
        f"/api/evaluation/runs/{run_id}/artifacts",
        json={
            "artifact_type": "runner.log",
            "uri": "memory://rest-runner-log",
            "content": {"events": ["claimed"], "token": "super-secret-token"},
        },
    )
    assert artifact_response.status_code == 201
    artifact_payload = artifact_response.json()["data"]
    assert artifact_payload["content_hash"].startswith("sha256:")
    assert "super-secret-token" not in json.dumps(artifact_payload)

    complete_response = await test_client.post(
        f"/api/evaluation/runs/{run_id}/complete",
        json={
            "worker_id": "worker-rest",
            "case_results": [
                {
                    "case_key": "case-one",
                    "status": "passed",
                    "assessments": [
                        {"category": "answer", "status": "passed", "score": "1.0", "hard_fail": False},
                    ],
                    "result": {"answer": "Revenue is 10"},
                },
                {
                    "case_key": "case-two",
                    "status": "passed",
                    "assessments": [
                        {"category": "answer", "status": "passed", "score": "1.0", "hard_fail": False},
                    ],
                    "result": {"answer": "Margin is 5"},
                },
            ],
        },
    )
    assert complete_response.status_code == 200
    completed = complete_response.json()["data"]
    assert completed["status"] == "passed"
    assert completed["summary"]["gate_decision"] == "passed"
    saved_artifacts = (
        await test_session.execute(select(EvaluationArtifact).where(EvaluationArtifact.run_id == run_id))
    ).scalars().all()
    assert len(saved_artifacts) == 1
    assert saved_artifacts[0].metadata_json == {"content_hash": artifact_payload["content_hash"]}


async def test_evaluation_promotion_rest_requires_publish_scope_and_records_gate_evidence(
    test_client,
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, _owner, suite_version = await _seed_suite_version(test_session)
    verification_run = await _seed_completed_run(
        test_session,
        tenant_id=tenant.id,
        suite_version_id=suite_version.id,
        gate_decision="passed",
    )
    regression_run = await _seed_completed_run(
        test_session,
        tenant_id=tenant.id,
        suite_version_id=suite_version.id,
        gate_decision="passed",
    )
    change_set = AdvisorChangeSet(
        tenant_id=tenant.id,
        suite_version_id=suite_version.id,
        target_ref="semantic_model:sales",
        base_version_ref="semantic_model:sales:v1",
        base_etag="sha256:base",
        status="ready_for_review",
        evidence_json={"verification": str(verification_run.id), "regression": str(regression_run.id)},
        verification_run_id=verification_run.id,
        regression_run_id=regression_run.id,
        created_by="advisor-1",
    )
    member = User(
        id=uuid4(),
        email=f"evaluation-member-{uuid4()}@example.test",
        hashed_password="fakehash",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    test_session.add(member)
    await test_session.flush()
    test_session.add(TenantMember(user_id=member.id, tenant_id=tenant.id, role=TenantRole.MEMBER.value))
    test_session.add(change_set)
    await test_session.commit()

    monkeypatch.setenv("BYAAN_LOCAL_AUTH_IMPERSONATION_ENABLED", "true")
    denied_response = await test_client.post(
        f"/api/evaluation/advisor-change-sets/{change_set.id}/promotion-decision",
        headers={"x-local-user-id": str(member.id), "x-tenant-id": str(tenant.id)},
    )
    assert denied_response.status_code == 403

    decision_response = await test_client.post(
        f"/api/evaluation/advisor-change-sets/{change_set.id}/promotion-decision",
    )
    assert decision_response.status_code == 200
    decision = decision_response.json()["data"]
    assert decision["decision"] == "accepted"
    assert decision["change_set_id"] == str(change_set.id)
    assert decision["audit"]["verification_gate"] == "passed"
    assert decision["audit"]["regression_gate"] == "passed"
    assert "super-secret" not in json.dumps(decision)


async def test_evaluation_preflight_rest_is_tenant_scoped(
    test_client,
    test_session: AsyncSession,
) -> None:
    _tenant, owner, _version = await _seed_suite_version(test_session)
    other_tenant = Tenant(
        id=uuid4(),
        name="Other Evaluation Tenant",
        slug=f"other-eval-{uuid4().hex[:8]}",
        owner_id=owner.id,
        is_personal=True,
    )
    test_session.add(other_tenant)
    await test_session.flush()
    suite = EvaluationSuite(
        tenant_id=other_tenant.id,
        slug=f"other-eval-suite-{uuid4()}",
        name="Other suite",
        description="Cross-tenant suite",
        owner_id=owner.id,
        lifecycle="published",
    )
    test_session.add(suite)
    await test_session.flush()
    other_version = EvaluationSuiteVersion(
        tenant_id=other_tenant.id,
        suite_id=suite.id,
        version_num=1,
        status="published",
        contract_version="evaluation.suite_version.v1",
        manifest_json={"contract_version": "evaluation.suite_version.v1", "suite_id": "other", "version": 1},
        gate_policy_json={"version": "gate-policy.v1"},
        case_count=0,
        content_hash="sha256:other",
        created_by=owner.id,
    )
    test_session.add(other_version)
    await test_session.commit()

    response = await test_client.post(
        "/api/evaluation/runs/preflight",
        json={
            "suite_version_id": str(other_version.id),
            "target_snapshot": _complete_snapshot(str(other_tenant.id)),
            "idempotency_key": "cross-tenant",
        },
    )

    assert response.status_code == 404
