from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.schemas.assets import AssetDescribeRequest, AssetDescriptor, AssetSearchRequest, AssetSearchResponse
from server.schemas.standard_response import StandardResponse, success_response
from server.services.assets import AssetService

router = APIRouter()
asset_service = AssetService()


@router.post("/assets/search", response_model=StandardResponse[AssetSearchResponse])
async def search_assets(
    payload: AssetSearchRequest,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    items = await asset_service.search_assets(
        session=session,
        tenant_id=auth.tenant_id,
        notebook_id=payload.notebook_id,
        query=payload.query,
        asset_types=list(payload.asset_types),
        publish_states=list(payload.publish_states),
        limit=payload.limit,
    )
    return success_response(
        data={"items": items, "total": len(items)},
        message="Asset search completed",
    )


@router.post("/assets/describe", response_model=StandardResponse[AssetDescriptor])
async def describe_asset(
    payload: AssetDescribeRequest,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    item = await asset_service.describe_asset(
        session=session,
        tenant_id=auth.tenant_id,
        asset_type=payload.asset_type,
        asset_id=payload.asset_id,
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return success_response(data=item, message="Asset described")
