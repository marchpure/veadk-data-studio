from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.conversation_evaluation import ConversationEvaluation
from server.models.custom_skill import CustomSkill
from server.models.evaluation import (
    AdvisorChangeSet,
    AdvisorSuggestion,
    EvaluationArtifact,
    EvaluationCase,
    EvaluationRun,
    EvaluationSuiteVersion,
    PromotionDecision,
)
from server.models.notebooks import Notebook
from server.models.skill_suggestion import SkillSuggestion
from server.repositories.evaluation import EvaluationRepository
from server.schemas.evaluation import EvaluationTargetSnapshot
from server.utils.error_sanitizer import sanitize_error_payload


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

    async def decide_promotion(
        self,
        *,
        tenant_id: str | UUID,
        change_set_id: str | UUID,
        actor_id: str,
    ) -> PromotionDecision:
        change_set = await self._repo.get_change_set(tenant_id=tenant_id, change_set_id=change_set_id)
        if change_set is None:
            raise ValueError("advisor change set not found")
        verification_run = await self._repo.get_run(
            tenant_id=tenant_id,
            run_id=change_set.verification_run_id,
        )
        regression_run = await self._repo.get_run(
            tenant_id=tenant_id,
            run_id=change_set.regression_run_id,
        )
        verification_gate = self._run_gate_decision(verification_run)
        regression_gate = self._run_gate_decision(regression_run)
        accepted = verification_gate == "passed" and regression_gate == "passed"
        decision = "accepted" if accepted else "rejected"
        change_set.status = "promoted" if accepted else "rejected"
        audit_json = {
            "verification_gate": verification_gate,
            "regression_gate": regression_gate,
            "target_ref": change_set.target_ref,
            "base_version_ref": change_set.base_version_ref,
            "actor_id": actor_id,
        }
        promotion = await self._repo.create_promotion_decision(
            tenant_id=tenant_id,
            change_set_id=change_set.id,
            verification_run_id=change_set.verification_run_id,
            regression_run_id=change_set.regression_run_id,
            decision=decision,
            decided_by=self._optional_uuid(actor_id),
            rationale=(
                "Verification and regression gates passed."
                if accepted
                else "Promotion blocked until verification and regression gates both pass."
            ),
            audit_json=audit_json,
        )
        await self._repo.create_audit_event(
            tenant_id=tenant_id,
            suite_id=None,
            suite_version_id=change_set.suite_version_id,
            run_id=None,
            actor_type="human",
            actor_id=actor_id,
            action="evaluation.promotion.decide",
            outcome=decision,
            details_json=audit_json,
        )
        await self._session.commit()
        await self._session.refresh(promotion)
        return promotion

    async def promote_conversation_evaluation_to_case_draft(
        self,
        *,
        tenant_id: str | UUID,
        evaluation_id: str | UUID,
        suite_version_id: str | UUID,
        question: str | None,
        tags: list[str],
        actor_id: str,
    ) -> tuple[EvaluationCase, bool]:
        suite_version = await self._require_suite_version(
            tenant_id=tenant_id,
            suite_version_id=suite_version_id,
        )
        if suite_version.status == "published":
            raise ValueError("published evaluation suite version manifest is immutable")

        evaluation = await self._get_conversation_evaluation(tenant_id=tenant_id, evaluation_id=evaluation_id)
        if evaluation.verdict not in {"mistake", "ambiguous"}:
            raise ValueError("only mistake or ambiguous conversation evaluations can become case drafts")
        case_key = f"legacy-conversation-evaluation-{evaluation.id}"
        existing = await self._repo.get_case_by_key(
            tenant_id=tenant_id,
            suite_version_id=suite_version.id,
            case_key=case_key,
        )
        if existing is not None:
            return existing, False

        notebook = await self._session.get(Notebook, evaluation.notebook_id)
        findings = sanitize_error_payload(evaluation.findings or {})
        feedback_question = (question or findings.get("question") or findings.get("description") or "").strip()
        if not feedback_question:
            feedback_question = f"Regression from conversation evaluation {evaluation.id}"
        correction = (findings.get("correction") or "").strip()
        summary = (findings.get("summary") or findings.get("description") or "").strip()
        expected_contract = {
            "semantic_intent": {
                "description": summary,
            },
            "answer": {
                "must_include_any": [correction] if correction else [],
                "must_include_all": [],
                "must_not_include": [],
                "refusal_allowed": False,
                "clarification_allowed": evaluation.verdict == "ambiguous",
            },
            "evidence": {
                "required": True,
                "lineage_refs": [str(evaluation.notebook_id)],
            },
            "policy": {
                "required_scopes": [],
                "forbidden_fields": [],
                "expected_decision": None,
                "security_hard_fail": True,
            },
            "feedback": {
                "taxonomy": findings.get("taxonomy"),
                "missed_instruction": findings.get("missed_instruction"),
                "description": findings.get("description") or summary,
                "findings": findings,
            },
        }
        provenance = {
            "source": "legacy_conversation_evaluation",
            "feedback_id": str(evaluation.id),
            "trace_id": findings.get("trace_id"),
            "principal": findings.get("principal") or {},
            "created_at": evaluation.evaluated_at.isoformat() if evaluation.evaluated_at else None,
        }
        case_tags = sorted({*tags, "legacy_conversation_evaluation", f"verdict:{evaluation.verdict}"})
        case = await self._repo.create_case(
            tenant_id=tenant_id,
            suite_version_id=suite_version.id,
            case_key=case_key,
            title=(summary or f"Conversation feedback {evaluation.verdict}")[:255],
            target_kinds_json=["agent_answer"],
            operation="answer_question",
            question=feedback_question,
            expected_contract_json=expected_contract,
            provenance_json=provenance,
            tags_json=case_tags,
            content_hash=self._digest(
                {
                    "case_key": case_key,
                    "question": feedback_question,
                    "expected": expected_contract,
                    "provenance": provenance,
                    "tags": case_tags,
                }
            ),
            immutable=False,
        )
        suite_version.case_count += 1
        suite_version.manifest_json = {
            **(suite_version.manifest_json or {}),
            "last_feedback_case_draft_id": str(case.id),
            "last_feedback_notebook_id": str(evaluation.notebook_id),
            "last_feedback_notebook_name": notebook.notebook_name if notebook else None,
        }
        suite_version.content_hash = self._digest(suite_version.manifest_json)
        await self._repo.create_audit_event(
            tenant_id=tenant_id,
            suite_id=suite_version.suite_id,
            suite_version_id=suite_version.id,
            run_id=None,
            actor_type="human",
            actor_id=actor_id,
            action="evaluation.feedback.promote_to_case",
            outcome="draft_created",
            details_json={
                "legacy_conversation_evaluation_id": str(evaluation.id),
                "case_id": str(case.id),
                "verdict": evaluation.verdict,
            },
        )
        await self._session.commit()
        await self._session.refresh(case)
        return case, True

    async def create_advisor_change_set_from_skill_suggestion(
        self,
        *,
        tenant_id: str | UUID,
        suggestion_id: str | UUID,
        suite_version_id: str | UUID | None,
        affected_case_ids: list[str | UUID],
        actor_id: str,
    ) -> tuple[AdvisorChangeSet, list[AdvisorSuggestion], bool]:
        suite_version = None
        if suite_version_id is not None:
            suite_version = await self._require_suite_version(
                tenant_id=tenant_id,
                suite_version_id=suite_version_id,
            )
        suggestion = await self._get_skill_suggestion(tenant_id=tenant_id, suggestion_id=suggestion_id)
        target_ref, base_version_ref, base_etag, patch = await self._advisor_target_and_patch(
            tenant_id=tenant_id,
            suggestion=suggestion,
        )
        existing = await self._repo.get_change_set_for_legacy_skill_suggestion(
            tenant_id=tenant_id,
            suite_version_id=suite_version.id if suite_version else None,
            suggestion_id=suggestion.id,
            target_ref=target_ref,
        )
        if existing is not None:
            advisor_suggestions = await self._repo.list_advisor_suggestions_for_change_set(
                tenant_id=tenant_id,
                change_set_id=existing.id,
            )
            return existing, advisor_suggestions, False

        affected_ids = await self._validate_affected_cases(
            tenant_id=tenant_id,
            suite_version=suite_version,
            affected_case_ids=affected_case_ids,
        )
        evidence = sanitize_error_payload(
            {
                "legacy_skill_suggestion_id": str(suggestion.id),
                "legacy_status": suggestion.status,
                "title": suggestion.title,
                "rationale": suggestion.rationale,
                "confidence": suggestion.confidence,
                "evidence": suggestion.evidence or {},
                "source": suggestion.source or {},
                "created_at": suggestion.created_at.isoformat() if suggestion.created_at else None,
            }
        )
        change_set = await self._repo.create_advisor_change_set(
            tenant_id=tenant_id,
            suite_version_id=suite_version.id if suite_version else None,
            target_ref=target_ref,
            base_version_ref=base_version_ref,
            base_etag=base_etag,
            status="draft",
            evidence_json=evidence,
            created_by=actor_id,
        )
        advisor_suggestion = await self._repo.create_advisor_suggestion(
            tenant_id=tenant_id,
            change_set_id=change_set.id,
            suggestion_type=self._advisor_suggestion_type(suggestion),
            patch_json=sanitize_error_payload(patch),
            affected_case_ids_json=[str(case_id) for case_id in affected_ids],
            status="draft",
        )
        await self._repo.create_audit_event(
            tenant_id=tenant_id,
            suite_id=suite_version.suite_id if suite_version else None,
            suite_version_id=suite_version.id if suite_version else None,
            run_id=None,
            actor_type="human",
            actor_id=actor_id,
            action="evaluation.advisor.change_set.create",
            outcome="draft_created",
            details_json={
                "legacy_skill_suggestion_id": str(suggestion.id),
                "change_set_id": str(change_set.id),
                "target_ref": target_ref,
                "affected_case_ids": [str(case_id) for case_id in affected_ids],
            },
        )
        await self._session.commit()
        await self._session.refresh(change_set)
        await self._session.refresh(advisor_suggestion)
        return change_set, [advisor_suggestion], True

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

    async def _get_conversation_evaluation(
        self,
        *,
        tenant_id: str | UUID,
        evaluation_id: str | UUID,
    ) -> ConversationEvaluation:
        result = await self._session.execute(
            select(ConversationEvaluation).where(
                ConversationEvaluation.tenant_id == tenant_id,
                ConversationEvaluation.id == evaluation_id,
            )
        )
        evaluation = result.scalar_one_or_none()
        if evaluation is None:
            raise ValueError("conversation evaluation not found")
        return evaluation

    async def _get_skill_suggestion(
        self,
        *,
        tenant_id: str | UUID,
        suggestion_id: str | UUID,
    ) -> SkillSuggestion:
        result = await self._session.execute(
            select(SkillSuggestion).where(
                SkillSuggestion.tenant_id == tenant_id,
                SkillSuggestion.id == suggestion_id,
            )
        )
        suggestion = result.scalar_one_or_none()
        if suggestion is None:
            raise ValueError("skill suggestion not found")
        return suggestion

    async def _advisor_target_and_patch(
        self,
        *,
        tenant_id: str | UUID,
        suggestion: SkillSuggestion,
    ) -> tuple[str, str, str, dict[str, Any]]:
        if suggestion.suggestion_type not in {"edit", "new_skill", "clarification"}:
            raise ValueError("unsupported advisor suggestion type")
        if suggestion.suggestion_type == "edit":
            if suggestion.skill_id is None:
                raise ValueError("edit suggestion has no target skill")
            skill = await self._session.get(CustomSkill, suggestion.skill_id)
            if skill is None or str(skill.tenant_id) != str(tenant_id):
                raise ValueError("target skill not found")
            target_ref = f"custom_skill:{skill.id}"
            base_payload = {
                "id": str(skill.id),
                "name": skill.name,
                "description": skill.description,
                "instructions": skill.instructions,
                "updated_at": skill.updated_at.isoformat() if skill.updated_at else None,
            }
            base_version_ref = f"{target_ref}:current"
            patch = {
                "op": "replace",
                "path": "/instructions",
                "value": suggestion.proposed_instructions or (suggestion.patch or {}).get("after") or "",
                "legacy_patch": suggestion.patch or {},
            }
            return target_ref, base_version_ref, self._digest(base_payload), patch
        target_ref = f"custom_skill:new:{suggestion.id}"
        patch = {
            "op": "create",
            "path": "/custom_skills",
            "value": {
                "name": suggestion.title[:100],
                "description": suggestion.rationale[:500],
                "instructions": suggestion.proposed_instructions or suggestion.title,
            },
        }
        return target_ref, f"{target_ref}:draft", self._digest({"suggestion_id": str(suggestion.id)}), patch

    async def _validate_affected_cases(
        self,
        *,
        tenant_id: str | UUID,
        suite_version: EvaluationSuiteVersion | None,
        affected_case_ids: list[str | UUID],
    ) -> list[str | UUID]:
        if suite_version is None or not affected_case_ids:
            return affected_case_ids
        cases = await self._repo.list_cases_by_ids(
            tenant_id=tenant_id,
            suite_version_id=suite_version.id,
            case_ids=affected_case_ids,
        )
        found = {str(case.id) for case in cases}
        missing = sorted(str(case_id) for case_id in affected_case_ids if str(case_id) not in found)
        if missing:
            raise ValueError(f"affected cases not found in suite version: {missing}")
        return affected_case_ids

    @staticmethod
    def _advisor_suggestion_type(suggestion: SkillSuggestion) -> str:
        if suggestion.suggestion_type in {"edit", "new_skill", "clarification"}:
            return "instruction_skill"
        return str(suggestion.suggestion_type)

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
    def _run_gate_decision(run: EvaluationRun | None) -> str:
        if run is None:
            return "missing"
        summary = run.summary_json or {}
        gate_decision = summary.get("gate_decision")
        if gate_decision in {"passed", "failed", "canceled", "blocked"}:
            return str(gate_decision)
        if run.status == "passed":
            return "passed"
        return "failed"

    @staticmethod
    def _optional_uuid(value: str | UUID) -> UUID | None:
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except ValueError:
            return None

    @staticmethod
    def _digest(payload: Any) -> str:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()
