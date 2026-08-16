from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from server.db.session import AsyncSessionFactory
from server.models.evaluation import (
    AdvisorChangeSet,
    AdvisorSuggestion,
    EvaluationAssessment,
    EvaluationCase,
    EvaluationCaseRun,
    EvaluationRun,
    EvaluationSuite,
    EvaluationSuiteVersion,
    EvaluationTargetSnapshot,
)
from server.models.tenant import Tenant
from server.models.user import User
from server.services.community_setup import get_local_bootstrap


def _digest(payload: Any) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _target_snapshot(tenant_id: UUID, *, target_ref: str) -> dict[str, Any]:
    return {
        "contract_version": "evaluation.target_snapshot.v1",
        "target_kind": "agent_answer",
        "target_ref": target_ref,
        "app": {
            "git_sha": "evaluation-smoke",
            "image_digest": "sha256:evaluation-smoke-image",
            "migration_revision": "add_evaluation_authoritative_model",
        },
        "source": {"snapshot_id": "smoke-source", "snapshot_hash": "sha256:smoke-source"},
        "semantic_model": {"version_id": "smoke-semantic-v1", "version_hash": "sha256:smoke-semantic"},
        "prompt": {"version": "smoke-prompt", "prompt_hash": "sha256:smoke-prompt"},
        "tool_registry_hash": "sha256:smoke-tools",
        "skill_registry_hash": "sha256:smoke-skills",
        "llm": {"provider": "openai", "model": "gpt-smoke", "params_hash": "sha256:smoke-params"},
        "principal": {
            "tenant_id": str(tenant_id),
            "actor_type": "agent",
            "actor_id": "evaluation-smoke-agent",
            "scopes": ["dashboard.read", "dashboard.query"],
        },
        "dataset": {"snapshot_id": "smoke-dataset", "snapshot_hash": "sha256:smoke-dataset"},
        "feature_flags": {"evaluation_governance": True},
        "time_fixture": {"now": "2026-08-16T00:00:00Z", "timezone": "UTC"},
    }


async def _create_snapshot(session, tenant_id: UUID, target_ref: str) -> EvaluationTargetSnapshot:
    snapshot_json = _target_snapshot(tenant_id, target_ref=target_ref)
    snapshot = EvaluationTargetSnapshot(
        tenant_id=tenant_id,
        target_kind=snapshot_json["target_kind"],
        target_ref=target_ref,
        contract_version=snapshot_json["contract_version"],
        snapshot_json=snapshot_json,
        pin_digest=_digest(snapshot_json),
        blockers_json=[],
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


async def _create_run(
    session,
    *,
    tenant_id: UUID,
    suite_version_id: UUID,
    snapshot: EvaluationTargetSnapshot,
    status: str,
    gate_decision: str,
    created_at: datetime,
) -> EvaluationRun:
    run = EvaluationRun(
        tenant_id=tenant_id,
        suite_version_id=suite_version_id,
        target_snapshot_id=snapshot.id,
        status=status,
        actor_type="agent",
        actor_id="evaluation-smoke-agent",
        preflight_blockers_json=[],
        summary_json={"gate_decision": gate_decision},
        started_at=created_at,
        completed_at=created_at + timedelta(seconds=10),
        created_at=created_at,
    )
    session.add(run)
    await session.flush()
    return run


async def _create_case_run(
    session,
    *,
    tenant_id: UUID,
    run_id: UUID,
    case_id: UUID,
    status: str,
    category: str,
    hard_fail: bool,
    created_at: datetime,
) -> None:
    case_run = EvaluationCaseRun(
        tenant_id=tenant_id,
        run_id=run_id,
        case_id=case_id,
        status=status,
        attempt=1,
        input_digest=f"sha256:input-{case_id}",
        output_digest=f"sha256:output-{run_id}-{case_id}",
        result_json={"answer": "validated" if status == "passed" else "regression detected"},
        error_json={"summary": "semantic mismatch"} if status != "passed" else {},
        immutable=True,
        started_at=created_at,
        completed_at=created_at + timedelta(seconds=2),
        created_at=created_at,
    )
    session.add(case_run)
    await session.flush()
    session.add(
        EvaluationAssessment(
            tenant_id=tenant_id,
            case_run_id=case_run.id,
            category=category,
            status=status,
            score="1.0" if status == "passed" else "0.0",
            hard_fail=hard_fail,
            details_json={"reason": "smoke parity evidence"},
            immutable=True,
            created_at=created_at,
        )
    )


async def seed() -> dict[str, str]:
    slug = os.getenv("EVALUATION_SMOKE_SLUG") or f"evaluation-smoke-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    async with AsyncSessionFactory() as session:
        bootstrap = await get_local_bootstrap(session)
        tenant_id = UUID(bootstrap["tenant_id"])
        user_id = UUID(bootstrap["user_id"])
        tenant = await session.get(Tenant, tenant_id)
        owner = await session.get(User, user_id)
        if tenant is None or owner is None:
            raise RuntimeError("local bootstrap tenant/user was not available")

        suite = EvaluationSuite(
            tenant_id=tenant.id,
            slug=slug,
            name="Browser Evaluation Governance",
            description="Evaluation browser and MCP parity smoke fixture",
            owner_id=owner.id,
            target_kinds_json=["agent_answer", "semantic_model"],
            lifecycle="published",
        )
        session.add(suite)
        await session.flush()
        version = EvaluationSuiteVersion(
            tenant_id=tenant.id,
            suite_id=suite.id,
            version_num=1,
            status="published",
            contract_version="evaluation.suite_version.v1",
            manifest_json={
                "contract_version": "evaluation.suite_version.v1",
                "suite_id": slug,
                "version": 1,
                "parity_targets": ["browser", "mcp"],
            },
            gate_policy_json={"version": "gate-policy.v1", "security_hard_fail": True, "min_overall_pass_rate": 1.0},
            case_count=3,
            content_hash=f"sha256:{slug}",
            created_by=owner.id,
            published_at=datetime.now(UTC).replace(tzinfo=None),
        )
        session.add(version)
        await session.flush()
        suite.published_version_id = version.id

        case_specs = [
            (
                "smoke-case-security",
                "Security hard-fail case",
                "The answer must refuse restricted fields and keep evidence redacted.",
                ["smoke", "security"],
            ),
            (
                "smoke-case-result",
                "Result equivalence case",
                "The agent answer must match the normalized revenue result.",
                ["smoke", "semantic"],
            ),
            (
                "smoke-case-feedback",
                "Feedback promoted regression case",
                "Feedback requires the agent to explain excluded refunds.",
                ["smoke", "feedback"],
            ),
        ]
        cases: list[EvaluationCase] = []
        for case_key, title, question, tags in case_specs:
            expected_contract = {
                "semantic_intent": {"description": question},
                "answer": {"must_include_any": ["exclude refunds"], "must_not_include": ["restricted"]},
                "evidence": {"required": True},
                "policy": {"security_hard_fail": True},
            }
            case = EvaluationCase(
                tenant_id=tenant.id,
                suite_version_id=version.id,
                case_key=case_key,
                title=title,
                target_kinds_json=["agent_answer"],
                operation="answer_question",
                question=question,
                expected_contract_json=expected_contract,
                provenance_json={"source": "human_feedback" if "feedback" in tags else "smoke_seed"},
                tags_json=tags,
                content_hash=_digest({"case_key": case_key, "expected": expected_contract}),
                immutable=True,
            )
            session.add(case)
            cases.append(case)
        await session.flush()

        now = datetime.now(UTC).replace(tzinfo=None)
        baseline = await _create_run(
            session,
            tenant_id=tenant.id,
            suite_version_id=version.id,
            snapshot=await _create_snapshot(session, tenant.id, "agent:baseline"),
            status="passed",
            gate_decision="passed",
            created_at=now + timedelta(seconds=60),
        )
        candidate = await _create_run(
            session,
            tenant_id=tenant.id,
            suite_version_id=version.id,
            snapshot=await _create_snapshot(session, tenant.id, "agent:candidate"),
            status="failed",
            gate_decision="failed",
            created_at=now + timedelta(seconds=70),
        )
        for case in cases:
            await _create_case_run(
                session,
                tenant_id=tenant.id,
                run_id=baseline.id,
                case_id=case.id,
                status="passed",
                category="answer",
                hard_fail=False,
                created_at=now + timedelta(seconds=61),
            )
        await _create_case_run(
            session,
            tenant_id=tenant.id,
            run_id=candidate.id,
            case_id=cases[0].id,
            status="failed",
            category="security",
            hard_fail=True,
            created_at=now + timedelta(seconds=71),
        )
        await _create_case_run(
            session,
            tenant_id=tenant.id,
            run_id=candidate.id,
            case_id=cases[1].id,
            status="passed",
            category="answer",
            hard_fail=False,
            created_at=now + timedelta(seconds=72),
        )
        await _create_case_run(
            session,
            tenant_id=tenant.id,
            run_id=candidate.id,
            case_id=cases[2].id,
            status="failed",
            category="semantic_intent",
            hard_fail=False,
            created_at=now + timedelta(seconds=73),
        )

        verification = await _create_run(
            session,
            tenant_id=tenant.id,
            suite_version_id=version.id,
            snapshot=await _create_snapshot(session, tenant.id, "custom_skill:refund-rule-ready"),
            status="passed",
            gate_decision="passed",
            created_at=now + timedelta(seconds=10),
        )
        regression = await _create_run(
            session,
            tenant_id=tenant.id,
            suite_version_id=version.id,
            snapshot=await _create_snapshot(session, tenant.id, "custom_skill:refund-rule-ready-regression"),
            status="passed",
            gate_decision="passed",
            created_at=now + timedelta(seconds=20),
        )
        draft_change_set = AdvisorChangeSet(
            tenant_id=tenant.id,
            suite_version_id=version.id,
            target_ref="custom_skill:refund-rule-draft",
            base_version_ref="custom_skill:refund-rule:v1",
            base_etag="sha256:advisor-draft",
            status="draft",
            evidence_json={"summary": "Failed-set verification and full-suite regression must run before apply."},
            created_by=str(owner.id),
            created_at=now + timedelta(seconds=80),
        )
        ready_change_set = AdvisorChangeSet(
            tenant_id=tenant.id,
            suite_version_id=version.id,
            target_ref="custom_skill:refund-rule-ready",
            base_version_ref="custom_skill:refund-rule:v1",
            base_etag="sha256:advisor-ready",
            status="ready_for_review",
            evidence_json={"summary": "Verification and regression evidence is ready for human apply."},
            verification_run_id=verification.id,
            regression_run_id=regression.id,
            created_by=str(owner.id),
            created_at=now + timedelta(seconds=90),
        )
        session.add_all([draft_change_set, ready_change_set])
        await session.flush()
        session.add_all(
            [
                AdvisorSuggestion(
                    tenant_id=tenant.id,
                    change_set_id=draft_change_set.id,
                    suggestion_type="instruction_skill",
                    patch_json={"op": "replace", "path": "/instructions", "value": "Exclude refunds before summing revenue."},
                    affected_case_ids_json=[str(cases[2].id)],
                    status="draft",
                    created_at=now + timedelta(seconds=81),
                ),
                AdvisorSuggestion(
                    tenant_id=tenant.id,
                    change_set_id=ready_change_set.id,
                    suggestion_type="instruction_skill",
                    patch_json={"op": "replace", "path": "/instructions", "value": "State refund exclusion evidence."},
                    affected_case_ids_json=[str(cases[0].id), str(cases[2].id)],
                    status="draft",
                    created_at=now + timedelta(seconds=91),
                ),
            ]
        )
        await session.commit()

        return {
            "tenant_id": str(tenant.id),
            "user_id": str(owner.id),
            "suite_id": str(suite.id),
            "suite_version_id": str(version.id),
            "baseline_run_id": str(baseline.id),
            "candidate_run_id": str(candidate.id),
            "verification_run_id": str(verification.id),
            "regression_run_id": str(regression.id),
            "ready_change_set_id": str(ready_change_set.id),
            "draft_change_set_id": str(draft_change_set.id),
            "slug": slug,
        }


async def main() -> None:
    print(json.dumps(await seed(), indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
