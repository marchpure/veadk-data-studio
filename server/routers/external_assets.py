from __future__ import annotations

import re
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.mcp_keys import MCPKeyContext, require_mcp_key
from server.db.session import get_async_session
from server.schemas.assets import AssetDescriptor
from server.schemas.standard_response import StandardResponse, success_response
from server.services.assets import AssetService
from server.services.dashboard import DashboardService
from server.services.semantic_model_service import SemanticModelService
from server.tools.sql import validate_sql_query

router = APIRouter(prefix="/external", tags=["external-assets"])
asset_service = AssetService()

ExternalAssetType = Literal["dashboard", "semantic_model"]
WRITE_SQL_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|MERGE|REPLACE|GRANT|REVOKE|CALL|COPY|VACUUM|OPTIMIZE)\b",
    re.IGNORECASE,
)


class ExternalAssetListResponse(BaseModel):
    items: list[AssetDescriptor]
    total: int
    next_cursor: str | None = None


class ExternalAssetQueryRequest(BaseModel):
    filters: dict[str, Any] = Field(default_factory=dict)
    data_view_ids: list[str] | None = None
    mode: Literal["live", "pinned_snapshot"] = "live"
    correlation_id: str | None = None
    idempotency_key: str | None = None
    metric: str | None = None
    dimension: str | None = None
    grain: str | None = None
    time_range: dict[str, Any] | None = None
    limit: int = Field(default=100, ge=1, le=5000)
    timeout: int = Field(default=30, ge=1, le=300)
    query: str | None = None


@router.get("/assets", response_model=StandardResponse[ExternalAssetListResponse])
async def list_external_assets(
    types: str = Query(default="dashboard,semantic_model"),
    query: str = "",
    limit: int = Query(default=20, ge=1),
    cursor: str | None = None,
    principal: MCPKeyContext = Depends(require_mcp_key),
    session: AsyncSession = Depends(get_async_session),
):
    requested_types = _parse_asset_types(types)
    if cursor:
        try:
            start = int(cursor)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cursor")
    else:
        start = 0
    page_limit = min(limit, 100)
    items = await asset_service.search_assets(
        session=session,
        tenant_id=principal.tenant_id,
        notebook_id=None,
        query=query,
        asset_types=requested_types,
        publish_states=["published"],
        limit=10_000,
    )
    page = items[start : start + page_limit]
    next_cursor = str(start + page_limit) if start + page_limit < len(items) else None
    return success_response(
        data={"items": page, "total": len(items), "next_cursor": next_cursor},
        message="External asset list completed",
    )


@router.get("/assets/{asset_type}/{asset_id}", response_model=StandardResponse[AssetDescriptor])
async def get_external_asset(
    asset_type: str,
    asset_id: str,
    principal: MCPKeyContext = Depends(require_mcp_key),
    session: AsyncSession = Depends(get_async_session),
):
    checked_type = _ensure_external_asset_type(asset_type)
    item = await _published_asset_or_404(
        session=session,
        tenant_id=principal.tenant_id,
        asset_type=checked_type,
        asset_id=asset_id,
    )
    return success_response(data=item, message="External asset described")


@router.post("/assets/{asset_type}/{asset_id}/query", response_model=StandardResponse[dict[str, Any]])
async def query_external_asset(
    asset_type: str,
    asset_id: str,
    payload: ExternalAssetQueryRequest,
    principal: MCPKeyContext = Depends(require_mcp_key),
    session: AsyncSession = Depends(get_async_session),
):
    checked_type = _ensure_external_asset_type(asset_type)
    item = await _published_asset_or_404(
        session=session,
        tenant_id=principal.tenant_id,
        asset_type=checked_type,
        asset_id=asset_id,
    )
    _assert_read_only_payload(payload)
    if checked_type == "dashboard":
        parsed_id = _parse_uuid_or_400(asset_id)
        try:
            result = await DashboardService().query_dashboard(
                session=session,
                tenant_id=principal.tenant_id,
                asset_id=parsed_id,
                actor_id=str(principal.key_id),
                actor_type="service",
                filters=payload.filters,
                data_view_ids=payload.data_view_ids,
                mode=payload.mode,
                correlation_id=payload.correlation_id,
                idempotency_key=payload.idempotency_key,
            )
        except HTTPException as error:
            raise _externalize_not_found(error)
        return success_response(data=result, message="External dashboard query executed")

    request = {
        "metric": payload.metric,
        "dimension": payload.dimension or "",
        "grain": payload.grain or "",
        "limit": payload.limit,
        "timeout": payload.timeout,
        "filters": payload.filters,
    }
    if payload.time_range:
        request["time_range"] = payload.time_range
    try:
        result = await SemanticModelService.run_query_metric(
            session=session,
            tenant_id=principal.tenant_id,
            slug=item["capabilities"]["slug"],
            request=request,
            user_id=principal.user_id,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return success_response(data=result, message="External semantic model query executed")


def _parse_asset_types(types: str) -> list[str]:
    requested = [asset_type.strip() for asset_type in types.split(",") if asset_type.strip()]
    unsupported = sorted(set(requested) - {"dashboard", "semantic_model"})
    if unsupported:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported asset type")
    return requested or ["dashboard", "semantic_model"]


def _ensure_external_asset_type(asset_type: str) -> ExternalAssetType:
    if asset_type not in {"dashboard", "semantic_model"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported asset type")
    return cast(ExternalAssetType, asset_type)


async def _published_asset_or_404(
    *,
    session: AsyncSession,
    tenant_id: UUID,
    asset_type: str,
    asset_id: str,
) -> dict[str, Any]:
    item = await asset_service.describe_asset(
        session=session,
        tenant_id=tenant_id,
        asset_type=asset_type,
        asset_id=asset_id,
    )
    if item is None or item.get("publish_state") != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return item


def _assert_read_only_payload(payload: ExternalAssetQueryRequest) -> None:
    if payload.query:
        try:
            validate_sql_query(payload.query)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error))
    encoded = " ".join(_flatten_strings(payload.model_dump(mode="json")))
    if WRITE_SQL_PATTERN.search(encoded):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Write operations are not allowed")


def _flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in _flatten_strings(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _flatten_strings(child)]
    return []


def _parse_uuid_or_400(value: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid asset ID")


def _externalize_not_found(error: HTTPException) -> HTTPException:
    if error.status_code in {status.HTTP_404_NOT_FOUND, status.HTTP_409_CONFLICT}:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return error
