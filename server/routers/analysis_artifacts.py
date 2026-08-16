from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_any_scope, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.schemas.analysis_artifacts import (
    AnalysisArtifactCreate,
    AnalysisArtifactListResponse,
    AnalysisArtifactRead,
    AnalysisArtifactRenderResponse,
    AnalysisArtifactRunResponse,
    AnalysisArtifactUpdate,
)
from server.schemas.standard_response import StandardResponse, success_response
from server.services.analysis_artifacts import AnalysisArtifactService

router = APIRouter()
artifact_service = AnalysisArtifactService()


def _artifact_payload(artifact) -> dict:
    return {
        "id": artifact.id,
        "notebook_id": artifact.notebook_id,
        "name": artifact.name,
        "objective": artifact.objective,
        "definition_json": artifact.definition_json,
        "version": artifact.version,
        "status": artifact.status,
        "latest_result_snapshot_id": artifact.latest_result_snapshot_id,
        "created_by": artifact.created_by,
        "created_at": artifact.created_at,
        "updated_at": artifact.updated_at,
    }


@router.post("/analysis-artifacts", response_model=StandardResponse[AnalysisArtifactRead], status_code=status.HTTP_201_CREATED)
async def create_analysis_artifact(
    payload: AnalysisArtifactCreate,
    auth: AuthContext = Depends(require_scope(Scope.NOTEBOOK_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        artifact = await artifact_service.create_artifact(
            session=session,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            notebook_id=payload.notebook_id,
            name=payload.name,
            objective=payload.objective,
            definition=payload.definition,
            status=payload.status,
        )
        return success_response(data=_artifact_payload(artifact), message="Analysis artifact created")
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.get("/analysis-artifacts", response_model=StandardResponse[AnalysisArtifactListResponse])
async def list_analysis_artifacts(
    notebook_id: UUID | None = Query(default=None),
    auth: AuthContext = Depends(require_scope(Scope.NOTEBOOK_READ_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    artifacts = await artifact_service.list_artifacts(
        session=session,
        tenant_id=auth.tenant_id,
        notebook_id=notebook_id,
    )
    return success_response(
        data={"items": [_artifact_payload(item) for item in artifacts], "total": len(artifacts)},
        message="Retrieved analysis artifacts",
    )


@router.get("/analysis-artifacts/{artifact_id}", response_model=StandardResponse[AnalysisArtifactRead])
async def get_analysis_artifact(
    artifact_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.NOTEBOOK_READ_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    artifact = await artifact_service.get_artifact(session=session, tenant_id=auth.tenant_id, artifact_id=artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis artifact not found")
    return success_response(data=_artifact_payload(artifact), message="Retrieved analysis artifact")


@router.patch("/analysis-artifacts/{artifact_id}", response_model=StandardResponse[AnalysisArtifactRead])
async def update_analysis_artifact(
    artifact_id: UUID,
    payload: AnalysisArtifactUpdate,
    auth: AuthContext = Depends(require_any_scope(Scope.NOTEBOOK_UPDATE, Scope.NOTEBOOK_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    artifact = await artifact_service.get_artifact(session=session, tenant_id=auth.tenant_id, artifact_id=artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis artifact not found")
    artifact = await artifact_service.update_artifact(
        session=session,
        artifact=artifact,
        name=payload.name,
        objective=payload.objective,
        definition=payload.definition,
        status=payload.status,
    )
    return success_response(data=_artifact_payload(artifact), message="Analysis artifact updated")


@router.post("/analysis-artifacts/{artifact_id}/runs", response_model=StandardResponse[AnalysisArtifactRunResponse])
async def run_analysis_artifact(
    artifact_id: UUID,
    auth: AuthContext = Depends(require_any_scope(Scope.NOTEBOOK_UPDATE, Scope.NOTEBOOK_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    artifact = await artifact_service.get_artifact(session=session, tenant_id=auth.tenant_id, artifact_id=artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis artifact not found")
    return success_response(data=artifact_service.run_preflight(artifact), message="Analysis artifact run preflight completed")


@router.get("/analysis-artifacts/{artifact_id}/render", response_model=StandardResponse[AnalysisArtifactRenderResponse])
async def render_analysis_artifact(
    artifact_id: UUID,
    format: str = Query(default="markdown", pattern="^(markdown|html)$"),
    auth: AuthContext = Depends(require_scope(Scope.NOTEBOOK_READ_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    artifact = await artifact_service.get_artifact(session=session, tenant_id=auth.tenant_id, artifact_id=artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis artifact not found")
    content = artifact_service.render_html(artifact) if format == "html" else artifact_service.render_markdown(artifact)
    return success_response(
        data={"artifact_id": artifact.id, "format": format, "content": content},
        message="Rendered analysis artifact",
    )


@router.post("/analysis-artifacts/{artifact_id}/publish", response_model=StandardResponse[AnalysisArtifactRead])
async def publish_analysis_artifact(
    artifact_id: UUID,
    auth: AuthContext = Depends(require_any_scope(Scope.NOTEBOOK_UPDATE, Scope.NOTEBOOK_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    artifact = await artifact_service.get_artifact(session=session, tenant_id=auth.tenant_id, artifact_id=artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis artifact not found")
    artifact = await artifact_service.update_artifact(session=session, artifact=artifact, status="published")
    return success_response(data=_artifact_payload(artifact), message="Analysis artifact published")
