from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.schemas.standard_response import success_response
from server.serializers.evaluation import (
    advisor_change_set_payload,
    advisor_suggestion_payload,
    evaluation_artifact_payload,
    evaluation_case_payload,
    evaluation_run_payload,
    promotion_payload,
)
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
    return success_response(data=evaluation_run_payload(run), message="Evaluation preflight run created")


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
    return success_response(data=evaluation_run_payload(run) if run else None, message="Evaluation run claim checked")


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
    return success_response(data=evaluation_run_payload(run), message="Evaluation run heartbeat recorded")


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
    return success_response(data=evaluation_run_payload(run), message="Evaluation run stop requested")


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
    return success_response(data=evaluation_artifact_payload(artifact), message="Evaluation run artifact recorded")


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
    return success_response(data=evaluation_run_payload(run), message="Evaluation run completed")


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
    return success_response(data=promotion_payload(promotion), message="Evaluation promotion decision recorded")


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
        data={"case": evaluation_case_payload(case), "created": created},
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
            "change_set": advisor_change_set_payload(change_set),
            "advisor_suggestions": [advisor_suggestion_payload(suggestion) for suggestion in suggestions],
            "created": created,
        },
        message="Advisor change set created from skill suggestion",
    )
