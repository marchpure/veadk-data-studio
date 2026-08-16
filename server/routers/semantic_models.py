from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_any_scope, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.schemas.standard_response import success_response
from server.services.semantic_model_service import SemanticModelService

router = APIRouter()


async def _list_models(auth: AuthContext, session: AsyncSession, message: str):
    models = await SemanticModelService.list_models(session, auth.tenant_id)
    return success_response(data={"items": models, "total": len(models)}, message=message)


async def _get_model(model_slug: str, auth: AuthContext, session: AsyncSession, message: str):
    model = await SemanticModelService.load_model(session, auth.tenant_id, model_slug)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Semantic model not found")
    return success_response(data=SemanticModelService.model_to_payload(model), message=message)


@router.get("/data-models")
async def list_data_models(
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    return await _list_models(auth, session, "Retrieved Data Models")


@router.get("/data-models/{model_slug}")
async def get_data_model(
    model_slug: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    return await _get_model(model_slug, auth, session, "Retrieved Data Model")


@router.post("/data-models/{model_slug}/validate")
async def validate_data_model(
    model_slug: str,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    model = await SemanticModelService.validate_model(session, auth.tenant_id, model_slug, auth.user_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data Model not found")
    return success_response(data=model, message="Data Model validated")


@router.post("/data-models/{model_slug}/publish")
async def publish_data_model(
    model_slug: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        model = await SemanticModelService.publish_model(session, auth.tenant_id, model_slug, auth.user_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data Model not found")
    return success_response(data=model, message="Data Model published")


@router.post("/data-models/{model_slug}/mcp/query_metric")
async def query_data_model_metric(
    model_slug: str,
    payload: dict[str, Any],
    auth: AuthContext = Depends(require_scope(Scope.QUERY_EXECUTE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        result = await SemanticModelService.run_query_metric(session, auth.tenant_id, model_slug, payload, auth.user_id)
    except RuntimeError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data Model not found")
    return success_response(data=result, message="Semantic metric query executed")


@router.get("/semantic-models")
async def list_semantic_models(
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    return await _list_models(auth, session, "Retrieved semantic models")


@router.get("/semantic-models/{model_slug}")
async def get_semantic_model(
    model_slug: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    return await _get_model(model_slug, auth, session, "Retrieved semantic model")
