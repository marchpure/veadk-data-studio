from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.evaluation import (
    AdvisorChangeSet,
    AdvisorSuggestion,
    EvaluationArtifact,
    EvaluationAssessment,
    EvaluationCase,
    EvaluationCaseRun,
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
        target_kinds_json=["semantic_model"],
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


def _import_case_payload(case_key: str = "imported-case-one") -> dict:
    return {
        "case_key": case_key,
        "title": "Imported case one",
        "target_kinds": ["semantic_model"],
        "operation": "answer_question",
        "question": "What is governed revenue?",
        "expected_contract": {
            "answer": {"must_include_all": ["revenue"]},
            "policy": {"security_hard_fail": True},
        },
        "provenance": {"source": "import", "principal": {"source": "rest-test"}},
        "tags": ["imported", "release-gate"],
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


async def _seed_case_result(
    test_session: AsyncSession,
    *,
    tenant_id,
    run_id,
    case_id,
    status: str,
    hard_fail: bool = False,
) -> EvaluationCaseRun:
    case_run = EvaluationCaseRun(
        tenant_id=tenant_id,
        run_id=run_id,
        case_id=case_id,
        status=status,
        attempt=1,
        input_digest=f"sha256:input-{status}",
        output_digest=f"sha256:output-{status}",
        result_json={"answer": status, "token": "super-secret-token"},
        error_json={"sql": "select * from restricted_table"} if status != "passed" else {},
        immutable=True,
    )
    test_session.add(case_run)
    await test_session.flush()
    assessment = EvaluationAssessment(
        tenant_id=tenant_id,
        case_run_id=case_run.id,
        category="security" if hard_fail else "answer",
        status=status,
        score="0.0" if status != "passed" else "1.0",
        hard_fail=hard_fail,
        details_json={"reason": "contains token=super-secret-token"},
        immutable=True,
    )
    test_session.add(assessment)
    await test_session.flush()
    return case_run


async def test_evaluation_rest_read_surfaces_describe_inventory_runs_failures_and_compare(
    test_client,
    test_session: AsyncSession,
) -> None:
    tenant, _owner, suite_version = await _seed_suite_version(test_session)
    suite = await test_session.get(EvaluationSuite, suite_version.suite_id)
    assert suite is not None
    cases = (
        await test_session.execute(
            select(EvaluationCase)
            .where(EvaluationCase.suite_version_id == suite_version.id)
            .order_by(EvaluationCase.case_key)
        )
    ).scalars().all()
    assert len(cases) == 2
    baseline_run = await _seed_completed_run(
        test_session,
        tenant_id=tenant.id,
        suite_version_id=suite_version.id,
        gate_decision="passed",
    )
    candidate_run = await _seed_completed_run(
        test_session,
        tenant_id=tenant.id,
        suite_version_id=suite_version.id,
        gate_decision="failed",
    )
    await _seed_case_result(
        test_session,
        tenant_id=tenant.id,
        run_id=baseline_run.id,
        case_id=cases[0].id,
        status="passed",
    )
    await _seed_case_result(
        test_session,
        tenant_id=tenant.id,
        run_id=candidate_run.id,
        case_id=cases[0].id,
        status="failed",
        hard_fail=True,
    )
    await test_session.commit()

    suites_response = await test_client.get("/api/evaluation/suites?query=REST&target_kind=semantic_model")
    assert suites_response.status_code == 200
    suites_payload = suites_response.json()["data"]
    assert suites_payload["total"] == 1
    assert suites_payload["items"][0]["id"] == str(suite.id)
    assert "super-secret-token" not in json.dumps(suites_payload)

    suite_response = await test_client.get(f"/api/evaluation/suites/{suite.id}?include_manifests=true")
    assert suite_response.status_code == 200
    suite_payload = suite_response.json()["data"]["suite"]
    assert suite_payload["versions"][0]["id"] == str(suite_version.id)
    assert suite_payload["versions"][0]["manifest"]["suite_id"] == "rest"

    cases_response = await test_client.get(f"/api/evaluation/suite-versions/{suite_version.id}/cases")
    assert cases_response.status_code == 200
    cases_payload = cases_response.json()["data"]
    assert cases_payload["total"] == 2
    assert cases_payload["items"][0]["case_key"] == "case-one"

    runs_response = await test_client.get(f"/api/evaluation/suite-versions/{suite_version.id}/runs")
    assert runs_response.status_code == 200
    runs_payload = runs_response.json()["data"]
    assert runs_payload["total"] == 2
    assert {item["id"] for item in runs_payload["items"]} == {str(baseline_run.id), str(candidate_run.id)}

    run_response = await test_client.get(f"/api/evaluation/runs/{candidate_run.id}")
    assert run_response.status_code == 200
    run_payload = run_response.json()["data"]
    assert run_payload["run"]["id"] == str(candidate_run.id)
    assert run_payload["case_runs"][0]["assessments"][0]["hard_fail"] is True
    assert "super-secret-token" not in json.dumps(run_payload)
    assert "restricted_table" not in json.dumps(run_payload)

    failures_response = await test_client.get(f"/api/evaluation/runs/{candidate_run.id}/failures")
    assert failures_response.status_code == 200
    failures_payload = failures_response.json()["data"]
    assert failures_payload["total"] == 1
    assert failures_payload["failures"][0]["status"] == "failed"
    assert failures_payload["failures"][0]["assessments"][0]["category"] == "security"

    compare_response = await test_client.get(
        f"/api/evaluation/runs/compare?baseline_run_id={baseline_run.id}&candidate_run_id={candidate_run.id}"
    )
    assert compare_response.status_code == 200
    comparison = compare_response.json()["data"]["comparison"]
    assert comparison["summary"]["regression_count"] == 1
    assert comparison["regressions"][0]["case_id"] == str(cases[0].id)


async def test_evaluation_rest_create_import_publish_and_run_closed_loop(
    test_client,
    test_session: AsyncSession,
) -> None:
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None

    create_response = await test_client.post(
        "/api/evaluation/suites",
        json={
            "slug": f"commercial-loop-{uuid4().hex[:8]}",
            "name": "Commercial Evaluation Loop",
            "description": "Explicit non-production acceptance fixture",
            "target_kinds": ["semantic_model"],
            "gate_policy": {"security_hard_fail": True, "min_overall_pass_rate": 1.0},
        },
    )
    assert create_response.status_code == 201
    suite = create_response.json()["data"]["suite"]
    assert suite["lifecycle"] == "draft"
    assert suite["versions"][0]["status"] == "draft"
    draft_version_id = suite["versions"][0]["id"]

    import_response = await test_client.post(
        f"/api/evaluation/suite-versions/{draft_version_id}/cases/import",
        json={"format": "json", "cases": [_import_case_payload("case-one"), _import_case_payload("case-two")]},
    )
    assert import_response.status_code == 201
    import_payload = import_response.json()["data"]
    assert import_payload["created_count"] == 2
    assert import_payload["existing_count"] == 0

    retry_import = await test_client.post(
        f"/api/evaluation/suite-versions/{draft_version_id}/cases/import",
        json={"format": "json", "cases": [_import_case_payload("case-one")]},
    )
    assert retry_import.status_code == 201
    assert retry_import.json()["data"]["created_count"] == 0
    assert retry_import.json()["data"]["existing_count"] == 1

    cases_response = await test_client.get(f"/api/evaluation/suite-versions/{draft_version_id}/cases")
    assert cases_response.status_code == 200
    assert cases_response.json()["data"]["total"] == 2

    publish_response = await test_client.post(f"/api/evaluation/suite-versions/{draft_version_id}/publish")
    assert publish_response.status_code == 200
    published = publish_response.json()["data"]["version"]
    assert published["status"] == "published"
    assert published["case_count"] == 2

    suite_response = await test_client.get(f"/api/evaluation/suites/{suite['id']}?include_manifests=true")
    assert suite_response.status_code == 200
    described = suite_response.json()["data"]["suite"]
    assert described["lifecycle"] == "published"
    assert described["published_version_id"] == draft_version_id
    assert described["current_draft_version_id"] is None

    import_after_publish = await test_client.post(
        f"/api/evaluation/suite-versions/{draft_version_id}/cases",
        json=_import_case_payload("case-after-publish"),
    )
    assert import_after_publish.status_code == 409

    preflight_response = await test_client.post(
        "/api/evaluation/runs/preflight",
        json={
            "suite_version_id": draft_version_id,
            "target_snapshot": _complete_snapshot(str(tenant.id)),
            "idempotency_key": "commercial-loop",
            "actor_type": "agent",
            "actor_id": "agent-release-gate",
        },
    )
    assert preflight_response.status_code == 202
    run_id = preflight_response.json()["data"]["id"]

    claim_response = await test_client.post(
        "/api/evaluation/runs/claim",
        json={"worker_id": "commercial-loop-worker", "lease_seconds": 60},
    )
    assert claim_response.status_code == 200
    assert claim_response.json()["data"]["id"] == run_id

    complete_response = await test_client.post(
        f"/api/evaluation/runs/{run_id}/complete",
        json={
            "worker_id": "commercial-loop-worker",
            "case_results": [
                {
                    "case_key": "case-one",
                    "status": "passed",
                    "assessments": [{"category": "answer", "status": "passed", "score": "1.0", "hard_fail": False}],
                    "result": {"answer": "revenue is governed"},
                },
                {
                    "case_key": "case-two",
                    "status": "failed",
                    "assessments": [{"category": "answer", "status": "failed", "score": "0", "hard_fail": True}],
                    "result": {"answer": "incorrect"},
                    "error": {"token": "super-secret-token", "sql": "select * from private_table"},
                },
            ],
        },
    )
    assert complete_response.status_code == 200
    completed = complete_response.json()["data"]
    assert completed["status"] == "failed"
    assert completed["summary"]["gate_decision"] == "failed"

    failures_response = await test_client.get(f"/api/evaluation/runs/{run_id}/failures")
    assert failures_response.status_code == 200
    failures = failures_response.json()["data"]
    assert failures["total"] == 1
    assert failures["failures"][0]["status"] == "failed"
    assert "super-secret-token" not in json.dumps(failures)
    assert "private_table" not in json.dumps(failures)


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


async def test_evaluation_advisor_rest_review_verify_regress_and_apply_surfaces(
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
        gate_decision="failed",
    )
    change_set = AdvisorChangeSet(
        tenant_id=tenant.id,
        suite_version_id=suite_version.id,
        target_ref="semantic_model:sales",
        base_version_ref="semantic_model:sales:v1",
        base_etag="sha256:base",
        status="draft",
        evidence_json={"token": "super-secret-token", "summary": "Review this staged patch"},
        verification_run_id=verification_run.id,
        regression_run_id=regression_run.id,
        created_by="advisor-1",
    )
    test_session.add(change_set)
    await test_session.flush()
    test_session.add(
        AdvisorSuggestion(
            tenant_id=tenant.id,
            change_set_id=change_set.id,
            suggestion_type="semantic_metadata",
            patch_json={"op": "replace", "path": "/description", "value": "password=plain"},
            affected_case_ids_json=["case-one"],
            status="draft",
        )
    )
    member = User(
        id=uuid4(),
        email=f"advisor-member-{uuid4()}@example.test",
        hashed_password="fakehash",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    test_session.add(member)
    await test_session.flush()
    test_session.add(TenantMember(user_id=member.id, tenant_id=tenant.id, role=TenantRole.MEMBER.value))
    await test_session.commit()

    review_response = await test_client.get(f"/api/evaluation/advisor-change-sets/{change_set.id}/review")
    assert review_response.status_code == 200
    review = review_response.json()["data"]
    assert review["change_set"]["id"] == str(change_set.id)
    assert review["advisor_suggestions"][0]["suggestion_type"] == "semantic_metadata"
    assert review["verification_run"]["id"] == str(verification_run.id)
    assert review["regression_run"]["id"] == str(regression_run.id)
    assert review["gate_summary"] == {
        "verification_gate": "passed",
        "regression_gate": "failed",
        "ready_to_apply": False,
    }
    assert "super-secret-token" not in json.dumps(review)
    assert "plain" not in json.dumps(review)

    advisor_list_response = await test_client.get(
        f"/api/evaluation/suite-versions/{suite_version.id}/advisor-change-sets"
    )
    assert advisor_list_response.status_code == 200
    advisor_list = advisor_list_response.json()["data"]
    assert advisor_list["total"] == 1
    assert advisor_list["items"][0]["id"] == str(change_set.id)

    verify_response = await test_client.post(
        f"/api/evaluation/advisor-change-sets/{change_set.id}/verification",
        json={"target_snapshot": _complete_snapshot(str(tenant.id)), "idempotency_key": "advisor-rest-verify"},
    )
    assert verify_response.status_code == 202
    verify_payload = verify_response.json()["data"]
    assert verify_payload["change_set"]["verification_run_id"] == verify_payload["run"]["id"]
    assert verify_payload["change_set"]["status"] == "verification_queued"
    assert verify_payload["run"]["status"] == "queued"

    regress_response = await test_client.post(
        f"/api/evaluation/advisor-change-sets/{change_set.id}/regression",
        json={"target_snapshot": _complete_snapshot(str(tenant.id)), "idempotency_key": "advisor-rest-regress"},
    )
    assert regress_response.status_code == 202
    regress_payload = regress_response.json()["data"]
    assert regress_payload["change_set"]["regression_run_id"] == regress_payload["run"]["id"]
    assert regress_payload["change_set"]["status"] == "regression_queued"

    monkeypatch.setenv("BYAAN_LOCAL_AUTH_IMPERSONATION_ENABLED", "true")
    denied_apply = await test_client.post(
        f"/api/evaluation/advisor-change-sets/{change_set.id}/apply",
        headers={"x-local-user-id": str(member.id), "x-tenant-id": str(tenant.id)},
    )
    assert denied_apply.status_code == 403

    latest_change_set = await test_session.get(AdvisorChangeSet, change_set.id)
    assert latest_change_set is not None
    verification_pass = await _seed_completed_run(
        test_session,
        tenant_id=tenant.id,
        suite_version_id=suite_version.id,
        gate_decision="passed",
    )
    regression_pass = await _seed_completed_run(
        test_session,
        tenant_id=tenant.id,
        suite_version_id=suite_version.id,
        gate_decision="passed",
    )
    latest_change_set.verification_run_id = verification_pass.id
    latest_change_set.regression_run_id = regression_pass.id
    latest_change_set.status = "ready_for_review"
    await test_session.commit()

    apply_response = await test_client.post(f"/api/evaluation/advisor-change-sets/{change_set.id}/apply")
    assert apply_response.status_code == 200
    apply_payload = apply_response.json()["data"]
    assert apply_payload["promotion"]["decision"] == "accepted"
    assert apply_payload["review"]["gate_summary"]["ready_to_apply"] is True
    assert apply_payload["review"]["change_set"]["status"] == "promoted"


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
