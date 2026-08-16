from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.conversation_evaluation import ConversationEvaluation
from server.models.custom_skill import CustomSkill
from server.models.evaluation import (
    AdvisorChangeSet,
    AdvisorSuggestion,
    EvaluationCase,
    EvaluationSuite,
    EvaluationSuiteVersion,
)
from server.models.notebooks import Notebook
from server.models.skill_suggestion import SkillSuggestion
from server.models.tenant import Tenant
from server.models.user import User

pytestmark = pytest.mark.asyncio


async def _community(test_session: AsyncSession) -> tuple[Tenant, User]:
    tenant = (await test_session.execute(select(Tenant).where(Tenant.slug == "community"))).scalar_one()
    owner = await test_session.get(User, tenant.owner_id)
    assert owner is not None
    return tenant, owner


async def _seed_draft_suite_version(test_session: AsyncSession, tenant: Tenant, owner: User) -> EvaluationSuiteVersion:
    suite = EvaluationSuite(
        tenant_id=tenant.id,
        slug=f"feedback-suite-{uuid4()}",
        name="Feedback suite",
        description="Suite for feedback promotion",
        owner_id=owner.id,
        lifecycle="draft",
    )
    test_session.add(suite)
    await test_session.flush()
    version = EvaluationSuiteVersion(
        tenant_id=tenant.id,
        suite_id=suite.id,
        version_num=1,
        status="draft",
        contract_version="evaluation.suite_version.v1",
        manifest_json={"contract_version": "evaluation.suite_version.v1", "suite_id": "feedback", "version": 1},
        gate_policy_json={"version": "gate-policy.v1", "security_hard_fail": True},
        case_count=0,
        content_hash="sha256:draft-feedback",
        created_by=owner.id,
    )
    test_session.add(version)
    await test_session.commit()
    return version


async def _seed_notebook(test_session: AsyncSession, tenant: Tenant, owner: User) -> Notebook:
    notebook = Notebook(
        tenant_id=tenant.id,
        created_by=owner.id,
        notebook_name="Feedback notebook",
    )
    test_session.add(notebook)
    await test_session.commit()
    return notebook


async def _seed_case(test_session: AsyncSession, tenant_id: UUID, suite_version_id: UUID) -> EvaluationCase:
    case = EvaluationCase(
        tenant_id=tenant_id,
        suite_version_id=suite_version_id,
        case_key="seeded-case",
        title="Seeded affected case",
        target_kinds_json=["agent_answer"],
        operation="answer_question",
        question="Seeded question",
        expected_contract_json={"answer": {"must_include_any": ["safe"]}},
        provenance_json={"source": "manual"},
        tags_json=["seeded"],
        content_hash="sha256:seeded-case",
        immutable=False,
    )
    test_session.add(case)
    await test_session.commit()
    return case


async def test_legacy_conversation_evaluation_promotes_to_redacted_case_draft_idempotently(
    test_client,
    test_session: AsyncSession,
) -> None:
    tenant, owner = await _community(test_session)
    suite_version = await _seed_draft_suite_version(test_session, tenant, owner)
    suite_version_id = suite_version.id
    notebook = await _seed_notebook(test_session, tenant, owner)
    evaluation = ConversationEvaluation(
        tenant_id=tenant.id,
        notebook_id=notebook.id,
        trigger="manual",
        verdict="mistake",
        findings={
            "taxonomy": "wrong_answer",
            "missed_instruction": "exclude refunds",
            "summary": "The assistant included refund rows.",
            "description": "User corrected the revenue answer.",
            "correction": "Revenue should exclude refunds.",
            "trace_id": "trace-123",
            "principal": {"actor_id": str(owner.id), "token": "raw-token"},
            "sql": "select * from restricted_table",
        },
    )
    test_session.add(evaluation)
    await test_session.commit()

    response = await test_client.post(
        f"/api/evaluation/feedback/conversation-evaluations/{evaluation.id}/case-draft",
        json={
            "suite_version_id": str(suite_version.id),
            "question": "What revenue did the assistant miss?",
            "tags": ["feedback", "revenue"],
        },
    )

    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["created"] is True
    case = payload["case"]
    assert case["case_key"] == f"legacy-conversation-evaluation-{evaluation.id}"
    assert case["target_kinds"] == ["agent_answer"]
    assert case["provenance"]["source"] == "legacy_conversation_evaluation"
    assert case["provenance"]["feedback_id"] == str(evaluation.id)
    assert case["provenance"]["trace_id"] == "trace-123"
    assert case["expected_contract"]["answer"]["must_include_any"] == ["Revenue should exclude refunds."]
    assert "feedback" in case["tags"]
    assert "verdict:mistake" in case["tags"]
    assert "raw-token" not in json.dumps(payload)
    assert "restricted_table" not in json.dumps(payload)

    repeated = await test_client.post(
        f"/api/evaluation/feedback/conversation-evaluations/{evaluation.id}/case-draft",
        json={"suite_version_id": str(suite_version.id), "question": "Ignored on idempotent retry"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["created"] is False
    assert repeated.json()["data"]["case"]["id"] == case["id"]

    cases = (
        await test_session.execute(
            select(EvaluationCase).where(EvaluationCase.suite_version_id == suite_version_id)
        )
    ).scalars().all()
    assert len(cases) == 1
    test_session.expire_all()
    refreshed_version = await test_session.get(EvaluationSuiteVersion, suite_version_id)
    assert refreshed_version is not None and refreshed_version.case_count == 1


async def test_skill_suggestion_creates_draft_only_advisor_change_set_with_redacted_evidence(
    test_client,
    test_session: AsyncSession,
) -> None:
    tenant, owner = await _community(test_session)
    suite_version = await _seed_draft_suite_version(test_session, tenant, owner)
    affected_case = await _seed_case(test_session, tenant.id, suite_version.id)
    skill = CustomSkill(
        tenant_id=tenant.id,
        created_by=owner.id,
        name="Revenue rules",
        description="Rules for revenue answers",
        instructions="Original instructions",
        scope="org",
    )
    test_session.add(skill)
    await test_session.flush()
    suggestion = SkillSuggestion(
        tenant_id=tenant.id,
        skill_id=skill.id,
        suggestion_type="edit",
        title="Exclude refunds",
        rationale="The answer was wrong when refunds were included.",
        confidence="high",
        evidence={"summary": "Refunds caused the miss", "token": "raw-token"},
        patch={"section": "instructions", "before": "Original", "after": "Include token=raw-token"},
        proposed_instructions="Always exclude refund rows. password=plain-password",
        source={"origin": "app", "trace_id": "trace-456"},
        status="pending",
    )
    test_session.add(suggestion)
    await test_session.commit()

    response = await test_client.post(
        f"/api/evaluation/skill-suggestions/{suggestion.id}/advisor-change-set",
        json={
            "suite_version_id": str(suite_version.id),
            "affected_case_ids": [str(affected_case.id)],
        },
    )

    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["created"] is True
    change_set = payload["change_set"]
    assert change_set["target_ref"] == f"custom_skill:{skill.id}"
    assert change_set["base_version_ref"] == f"custom_skill:{skill.id}:current"
    assert change_set["base_etag"].startswith("sha256:")
    assert change_set["status"] == "draft"
    assert change_set["evidence"]["legacy_skill_suggestion_id"] == str(suggestion.id)
    assert payload["advisor_suggestions"][0]["suggestion_type"] == "instruction_skill"
    assert payload["advisor_suggestions"][0]["affected_case_ids"] == [str(affected_case.id)]
    assert payload["advisor_suggestions"][0]["patch"]["op"] == "replace"
    assert payload["advisor_suggestions"][0]["patch"]["path"] == "/instructions"
    assert "raw-token" not in json.dumps(payload)
    assert "plain-password" not in json.dumps(payload)

    refreshed_suggestion = await test_session.get(SkillSuggestion, suggestion.id)
    refreshed_skill = await test_session.get(CustomSkill, skill.id)
    assert refreshed_suggestion is not None and refreshed_suggestion.status == "pending"
    assert refreshed_skill is not None and refreshed_skill.instructions == "Original instructions"

    repeated = await test_client.post(
        f"/api/evaluation/skill-suggestions/{suggestion.id}/advisor-change-set",
        json={"suite_version_id": str(suite_version.id)},
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["created"] is False
    assert repeated.json()["data"]["change_set"]["id"] == change_set["id"]

    change_sets = (await test_session.execute(select(AdvisorChangeSet))).scalars().all()
    advisor_suggestions = (await test_session.execute(select(AdvisorSuggestion))).scalars().all()
    assert len(change_sets) == 1
    assert len(advisor_suggestions) == 1
