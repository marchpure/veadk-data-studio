from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_any_scope, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.schemas.semantic_models import (
    ExplorePatch,
    McpQueryRequest,
    MetricPatch,
    PublishNotesRequest,
    RawSqlFallbackRequest,
    RelationshipPatch,
    SaveExploreArtifactRequest,
    SemanticModelCreateRequest,
    SuggestionActionRequest,
)
from server.schemas.standard_response import success_response
from server.services.semantic_model_service import SemanticModelService

router = APIRouter()


def _require_model_editor(auth: AuthContext) -> None:
    if not (
        auth.has_scope(Scope.DATASET_UPDATE)
        or auth.has_scope(Scope.DATASET_UPDATE_OWN)
        or auth.has_scope(Scope.TENANT_UPDATE)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Data Model editor permission required")


def _require_publisher(auth: AuthContext) -> None:
    if not auth.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners and admins can publish Data Models")


@router.get("/data-models")
async def list_data_models(
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    models = await SemanticModelService.list_models(session, auth.tenant_id, auth.user_id)
    return success_response(data={"items": models, "total": len(models)}, message="Retrieved Data Models")


@router.get("/data-models/profiles")
async def list_data_model_profiles(
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    profiles = await SemanticModelService.get_profiles(session, auth.tenant_id, auth.user_id)
    return success_response(data={"items": profiles, "total": len(profiles)}, message="Retrieved datasource profiles")


@router.get("/datasources/{datasource_id}/profile")
async def get_datasource_profile(
    datasource_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    profiles = await SemanticModelService.get_profiles(session, auth.tenant_id, auth.user_id)
    profile = next((item for item in profiles if item["id"] == datasource_id), None)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Datasource profile not found")
    return success_response(data=profile, message="Retrieved datasource profile")


@router.post("/data-models/generation-jobs")
async def create_generation_job(
    payload: SemanticModelCreateRequest,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_model_editor(auth)
    job = await SemanticModelService.create_generation_job(
        session,
        auth.tenant_id,
        auth.user_id,
        {
            "datasource_id": payload.datasource_id,
            "domain": payload.domain,
            "selected_tables": payload.selected_tables,
            "business_questions": payload.business_questions,
        },
    )
    return success_response(data=SemanticModelService.job_to_payload(job), message="Generation job created")


@router.get("/data-models/generation-jobs/{job_id}")
async def get_generation_job(
    job_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    job = await SemanticModelService.advance_generation_job(session, auth.tenant_id, job_id, auth.user_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation job not found")
    return success_response(data=SemanticModelService.job_to_payload(job), message="Generation job status")


@router.post("/data-models/generation-jobs/{job_id}/advance")
async def advance_generation_job(
    job_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_model_editor(auth)
    job = await SemanticModelService.advance_generation_job(session, auth.tenant_id, job_id, auth.user_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation job not found")
    return success_response(data=SemanticModelService.job_to_payload(job), message="Generation job advanced")


@router.get("/data-models/{model_id}")
async def get_data_model(
    model_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    model = await SemanticModelService.get_model(session, auth.tenant_id, model_id, auth.user_id)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data Model not found")
    return success_response(data=model, message="Retrieved Data Model")


@router.patch("/data-models/{model_id}/relationships/{relationship_id}")
async def update_relationship(
    model_id: str,
    relationship_id: str,
    payload: RelationshipPatch,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_model_editor(auth)
    model = await SemanticModelService.update_relationship(
        session, auth.tenant_id, model_id, relationship_id, payload.model_dump(exclude_unset=True), auth.user_id
    )
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relationship not found")
    return success_response(data=model, message="Relationship updated")


@router.post("/data-models/{model_id}/relationships/{relationship_id}/fix-fanout")
async def fix_fanout_relationship(
    model_id: str,
    relationship_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_model_editor(auth)
    model = await SemanticModelService.fix_fanout_relationship(session, auth.tenant_id, model_id, relationship_id, auth.user_id)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relationship not found")
    return success_response(data=model, message="Fanout relationship fixed")


@router.post("/data-models/{model_id}/relationships/{relationship_id}/reject")
async def reject_relationship(
    model_id: str,
    relationship_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_model_editor(auth)
    model = await SemanticModelService.reject_relationship(session, auth.tenant_id, model_id, relationship_id, auth.user_id)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relationship not found")
    return success_response(data=model, message="Relationship rejected")


@router.patch("/data-models/{model_id}/metrics/{metric_id}")
async def update_metric(
    model_id: str,
    metric_id: str,
    payload: MetricPatch,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_model_editor(auth)
    model = await SemanticModelService.update_metric(
        session, auth.tenant_id, model_id, metric_id, payload.model_dump(exclude_unset=True), auth.user_id
    )
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metric not found")
    return success_response(data=model, message="Metric compiled and previewed")


@router.patch("/data-models/{model_id}/explore")
async def update_explore(
    model_id: str,
    payload: ExplorePatch,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    model = await SemanticModelService.update_explore(
        session, auth.tenant_id, model_id, payload.model_dump(exclude_unset=True), auth.user_id
    )
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data Model not found")
    return success_response(data=model, message="Explore state updated")


@router.post("/data-models/{model_id}/explore/artifacts")
async def save_explore_artifact(
    model_id: str,
    payload: SaveExploreArtifactRequest,
    auth: AuthContext = Depends(require_any_scope(Scope.QUERY_CREATE, Scope.QUERY_EXECUTE)),
    session: AsyncSession = Depends(get_async_session),
):
    model = await SemanticModelService.save_explore_artifact(session, auth.tenant_id, model_id, payload.kind, auth.user_id)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data Model not found")
    return success_response(data=model, message="Explore artifact saved")


@router.post("/data-models/{model_id}/suggestions/{suggestion_id}")
async def suggestion_action(
    model_id: str,
    suggestion_id: str,
    payload: SuggestionActionRequest,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_model_editor(auth)
    model = await SemanticModelService.suggestion_action(session, auth.tenant_id, model_id, suggestion_id, payload.action, auth.user_id)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")
    return success_response(data=model, message="Suggestion updated")


@router.post("/data-models/{model_id}/validate")
async def validate_model(
    model_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_model_editor(auth)
    model = await SemanticModelService.validate_model(session, auth.tenant_id, model_id, auth.user_id)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data Model not found")
    return success_response(data=model, message="Data Model validated")


@router.post("/data-models/{model_id}/review/open")
async def open_review(
    model_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_model_editor(auth)
    model = await SemanticModelService.update_review(session, auth.tenant_id, model_id, {"opened": True}, auth.user_id)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data Model not found")
    return success_response(data=model, message="Review opened")


@router.post("/data-models/{model_id}/review/mark")
async def mark_reviewed(
    model_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_model_editor(auth)
    model = await SemanticModelService.update_review(session, auth.tenant_id, model_id, {"opened": True, "reviewed": True}, auth.user_id)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data Model not found")
    return success_response(data=model, message="Review marked")


@router.patch("/data-models/{model_id}/review/notes")
async def update_publish_notes(
    model_id: str,
    payload: PublishNotesRequest,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_model_editor(auth)
    model = await SemanticModelService.update_review(session, auth.tenant_id, model_id, {"publishNotes": payload.notes}, auth.user_id)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data Model not found")
    return success_response(data=model, message="Publish notes updated")


@router.post("/data-models/{model_id}/publish")
async def publish_model(
    model_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_publisher(auth)
    model = await SemanticModelService.publish_model(session, auth.tenant_id, model_id, auth.user_id)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data Model not found")
    return success_response(data=model, message="Data Model published")


@router.patch("/data-models/{model_id}/mcp/raw-sql-fallback")
async def set_raw_sql_fallback(
    model_id: str,
    payload: RawSqlFallbackRequest,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_publisher(auth)
    model = await SemanticModelService.set_raw_sql_fallback(session, auth.tenant_id, model_id, payload.enabled, auth.user_id)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data Model not found")
    return success_response(data=model, message="MCP policy updated")


@router.post("/data-models/{model_id}/mcp/query_metric")
async def run_mcp_query_metric(
    model_id: str,
    payload: McpQueryRequest,
    auth: AuthContext = Depends(require_scope(Scope.QUERY_EXECUTE)),
    session: AsyncSession = Depends(get_async_session),
):
    model = await SemanticModelService.run_mcp_query(
        session, auth.tenant_id, model_id, payload.model_dump(exclude_unset=True), auth.user_id
    )
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data Model not found")
    return success_response(data=model, message="MCP query_metric executed")
