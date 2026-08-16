from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.models.evaluation import (
    AdvisorChangeSet,
    AdvisorSuggestion,
    EvaluationArtifact,
    EvaluationCase,
    EvaluationRun,
    PromotionDecision,
)
from server.schemas.standard_response import success_response
from server.services.evaluation import EvaluationService

router = APIRouter()


class EvaluationRouterModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvaluationPreflightRunRequest(EvaluationRouterModel):
    suite_version_id: UUID
    target_snapshot: dict[str, Any]
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)
    actor_type: Literal["human", "agent", "service"] = "agent"
    actor_id: str | None = Field(default=None, min_length=1, max_length=160)


class EvaluationRunLeaseRequest(EvaluationRouterModel):
    worker_id: str = Field(min_length=1, max_length=160)
    lease_seconds: int = Field(default=60, ge=1, le=3600)


class EvaluationArtifactRequest(EvaluationRouterModel):
    artifact_type: str = Field(min_length=1, max_length=80)
    uri: str = Field(min_length=1)
    content: Any


class EvaluationCompleteRunRequest(EvaluationRouterModel):
    worker_id: str = Field(min_length=1, max_length=160)
    case_results: list[dict[str, Any]] = Field(min_length=1)


class EvaluationFeedbackCaseDraftRequest(EvaluationRouterModel):
    suite_version_id: UUID
    question: str | None = Field(default=None, min_length=1)
    tags: list[str] = Field(default_factory=list)


class EvaluationSkillSuggestionAdvisorRequest(EvaluationRouterModel):
    suite_version_id: UUID | None = None
    affected_case_ids: list[UUID] = Field(default_factory=list)


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _run_payload(run: EvaluationRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "tenant_id": str(run.tenant_id),
        "suite_version_id": str(run.suite_version_id),
        "target_snapshot_id": str(run.target_snapshot_id),
        "status": run.status,
        "actor_type": run.actor_type,
        "actor_id": run.actor_id,
        "baseline_run_id": str(run.baseline_run_id) if run.baseline_run_id else None,
        "candidate_label": run.candidate_label,
        "idempotency_key": run.idempotency_key,
        "attempt": run.attempt,
        "lease_holder": run.lease_holder,
        "lease_expires_at": _dt(run.lease_expires_at),
        "heartbeat_at": _dt(run.heartbeat_at),
        "stop_requested": run.stop_requested,
        "preflight_blockers": run.preflight_blockers_json or [],
        "summary": run.summary_json or {},
        "started_at": _dt(run.started_at),
        "completed_at": _dt(run.completed_at),
        "created_at": _dt(run.created_at),
    }


def _artifact_payload(artifact: EvaluationArtifact) -> dict[str, Any]:
    return {
        "id": str(artifact.id),
        "tenant_id": str(artifact.tenant_id),
        "run_id": str(artifact.run_id) if artifact.run_id else None,
        "case_run_id": str(artifact.case_run_id) if artifact.case_run_id else None,
        "artifact_type": artifact.artifact_type,
        "uri": artifact.uri,
        "content_hash": artifact.content_hash,
        "metadata": artifact.metadata_json or {},
        "immutable": artifact.immutable,
        "created_at": _dt(artifact.created_at),
    }


def _promotion_payload(promotion: PromotionDecision) -> dict[str, Any]:
    return {
        "id": str(promotion.id),
        "tenant_id": str(promotion.tenant_id),
        "change_set_id": str(promotion.change_set_id) if promotion.change_set_id else None,
        "verification_run_id": str(promotion.verification_run_id) if promotion.verification_run_id else None,
        "regression_run_id": str(promotion.regression_run_id) if promotion.regression_run_id else None,
        "decision": promotion.decision,
        "decided_by": str(promotion.decided_by) if promotion.decided_by else None,
        "rationale": promotion.rationale,
        "audit": promotion.audit_json or {},
        "created_at": _dt(promotion.created_at),
    }


def _case_payload(case: EvaluationCase) -> dict[str, Any]:
    return {
        "id": str(case.id),
        "tenant_id": str(case.tenant_id),
        "suite_version_id": str(case.suite_version_id),
        "case_key": case.case_key,
        "title": case.title,
        "target_kinds": case.target_kinds_json or [],
        "operation": case.operation,
        "question": case.question,
        "expected_contract": case.expected_contract_json or {},
        "provenance": case.provenance_json or {},
        "tags": case.tags_json or [],
        "content_hash": case.content_hash,
        "immutable": case.immutable,
        "created_at": _dt(case.created_at),
    }


def _advisor_change_set_payload(change_set: AdvisorChangeSet) -> dict[str, Any]:
    return {
        "id": str(change_set.id),
        "tenant_id": str(change_set.tenant_id),
        "suite_version_id": str(change_set.suite_version_id) if change_set.suite_version_id else None,
        "target_ref": change_set.target_ref,
        "base_version_ref": change_set.base_version_ref,
        "base_etag": change_set.base_etag,
        "status": change_set.status,
        "evidence": change_set.evidence_json or {},
        "verification_run_id": str(change_set.verification_run_id) if change_set.verification_run_id else None,
        "regression_run_id": str(change_set.regression_run_id) if change_set.regression_run_id else None,
        "created_by": change_set.created_by,
        "created_at": _dt(change_set.created_at),
    }


def _advisor_suggestion_payload(suggestion: AdvisorSuggestion) -> dict[str, Any]:
    return {
        "id": str(suggestion.id),
        "tenant_id": str(suggestion.tenant_id),
        "change_set_id": str(suggestion.change_set_id),
        "suggestion_type": suggestion.suggestion_type,
        "patch": suggestion.patch_json or {},
        "affected_case_ids": suggestion.affected_case_ids_json or [],
        "status": suggestion.status,
        "created_at": _dt(suggestion.created_at),
    }


def _service_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    if "not found" in detail:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if "leased by this worker" in detail or "case results do not match" in detail or "immutable" in detail:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


@router.post("/evaluation/runs/preflight", status_code=status.HTTP_202_ACCEPTED)
async def create_evaluation_preflight_run(
    payload: EvaluationPreflightRunRequest,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_QUERY)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        run = await EvaluationService(session).create_preflight_run(
            tenant_id=auth.tenant_id,
            suite_version_id=payload.suite_version_id,
            target_snapshot_payload=payload.target_snapshot,
            actor_id=payload.actor_id or str(auth.user_id),
            idempotency_key=payload.idempotency_key,
            actor_type=payload.actor_type,
        )
    except ValueError as exc:
        raise _service_error(exc) from exc
    return success_response(data=_run_payload(run), message="Evaluation preflight run created")


@router.post("/evaluation/runs/claim")
async def claim_evaluation_run(
    payload: EvaluationRunLeaseRequest,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_QUERY)),
    session: AsyncSession = Depends(get_async_session),
):
    run = await EvaluationService(session).claim_next_run(
        tenant_id=auth.tenant_id,
        worker_id=payload.worker_id,
        lease_seconds=payload.lease_seconds,
    )
    return success_response(data=_run_payload(run) if run else None, message="Evaluation run claim checked")


@router.post("/evaluation/runs/{run_id}/heartbeat")
async def heartbeat_evaluation_run(
    run_id: UUID,
    payload: EvaluationRunLeaseRequest,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_QUERY)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        run = await EvaluationService(session).heartbeat_run(
            tenant_id=auth.tenant_id,
            run_id=run_id,
            worker_id=payload.worker_id,
            lease_seconds=payload.lease_seconds,
        )
    except ValueError as exc:
        raise _service_error(exc) from exc
    return success_response(data=_run_payload(run), message="Evaluation run heartbeat recorded")


@router.post("/evaluation/runs/{run_id}/stop")
async def request_evaluation_run_stop(
    run_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_QUERY)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        run = await EvaluationService(session).request_run_stop(
            tenant_id=auth.tenant_id,
            run_id=run_id,
            actor_id=str(auth.user_id),
        )
    except ValueError as exc:
        raise _service_error(exc) from exc
    return success_response(data=_run_payload(run), message="Evaluation run stop requested")


@router.post("/evaluation/runs/{run_id}/artifacts", status_code=status.HTTP_201_CREATED)
async def record_evaluation_run_artifact(
    run_id: UUID,
    payload: EvaluationArtifactRequest,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_QUERY)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        artifact = await EvaluationService(session).record_run_artifact(
            tenant_id=auth.tenant_id,
            run_id=run_id,
            artifact_type=payload.artifact_type,
            uri=payload.uri,
            content=payload.content,
        )
    except ValueError as exc:
        raise _service_error(exc) from exc
    return success_response(data=_artifact_payload(artifact), message="Evaluation run artifact recorded")


@router.post("/evaluation/runs/{run_id}/complete")
async def complete_evaluation_run(
    run_id: UUID,
    payload: EvaluationCompleteRunRequest,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_QUERY)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        run = await EvaluationService(session).complete_run_with_case_results(
            tenant_id=auth.tenant_id,
            run_id=run_id,
            worker_id=payload.worker_id,
            case_results=payload.case_results,
        )
    except ValueError as exc:
        raise _service_error(exc) from exc
    return success_response(data=_run_payload(run), message="Evaluation run completed")


@router.post("/evaluation/advisor-change-sets/{change_set_id}/promotion-decision")
async def decide_evaluation_promotion(
    change_set_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_PUBLISH)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        promotion = await EvaluationService(session).decide_promotion(
            tenant_id=auth.tenant_id,
            change_set_id=change_set_id,
            actor_id=str(auth.user_id),
        )
    except ValueError as exc:
        raise _service_error(exc) from exc
    return success_response(data=_promotion_payload(promotion), message="Evaluation promotion decision recorded")


@router.post("/evaluation/feedback/conversation-evaluations/{evaluation_id}/case-draft")
async def create_case_draft_from_conversation_evaluation(
    evaluation_id: UUID,
    payload: EvaluationFeedbackCaseDraftRequest,
    response: Response,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_EDIT)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        case, created = await EvaluationService(session).promote_conversation_evaluation_to_case_draft(
            tenant_id=auth.tenant_id,
            evaluation_id=evaluation_id,
            suite_version_id=payload.suite_version_id,
            question=payload.question,
            tags=payload.tags,
            actor_id=str(auth.user_id),
        )
    except ValueError as exc:
        raise _service_error(exc) from exc
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return success_response(
        data={"case": _case_payload(case), "created": created},
        message="Evaluation case draft created from feedback",
    )


@router.post("/evaluation/skill-suggestions/{suggestion_id}/advisor-change-set")
async def create_advisor_change_set_from_skill_suggestion(
    suggestion_id: UUID,
    payload: EvaluationSkillSuggestionAdvisorRequest,
    response: Response,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_EDIT)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        change_set, suggestions, created = await EvaluationService(session).create_advisor_change_set_from_skill_suggestion(
            tenant_id=auth.tenant_id,
            suggestion_id=suggestion_id,
            suite_version_id=payload.suite_version_id,
            affected_case_ids=payload.affected_case_ids,
            actor_id=str(auth.user_id),
        )
    except ValueError as exc:
        raise _service_error(exc) from exc
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return success_response(
        data={
            "change_set": _advisor_change_set_payload(change_set),
            "advisor_suggestions": [_advisor_suggestion_payload(suggestion) for suggestion in suggestions],
            "created": created,
        },
        message="Advisor change set created from skill suggestion",
    )
