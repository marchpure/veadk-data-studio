from __future__ import annotations

import html

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.schemas.source_connections import (
    FeishuAdminConfigRequest,
    SourceConnectionCreate,
    SourceResourceQuickLocateRequest,
)
from server.schemas.standard_response import StandardResponse, success_response
from server.services.source_connections import SourceConnectionService
from server.services.source_connectors import (
    ConnectorError,
    FeishuAdminConfigService,
    FeishuOAuthStateStore,
    feishu_callback_url,
)

router = APIRouter()
source_connection_service = SourceConnectionService()


def _http_error(error: Exception) -> HTTPException:
    message = str(error)
    if isinstance(error, ConnectorError):
        if error.code in {"admin_config_required", "missing_token", "unsupported_provider"}:
            code = status.HTTP_400_BAD_REQUEST
        elif error.code in {"needs_authorization", "permission_lost", "reauthorization_required"}:
            code = status.HTTP_403_FORBIDDEN
        else:
            code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return HTTPException(status_code=code, detail={"code": error.code, "message": message})
    code = status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail=message)


def _require_admin(auth: AuthContext) -> None:
    if not auth.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")


def _oauth_callback_html(*, state: str | None, status_value: str, message: str, connection_id: str | None = None) -> str:
    safe_status = html.escape(status_value)
    safe_message = html.escape(message)
    safe_connection_id = html.escape(connection_id or "")
    payload = {
        "type": "byaan:feishu-oauth",
        "state": state or "",
        "status": status_value,
        "connectionId": connection_id,
        "message": message,
    }
    import json

    payload_json = json.dumps(payload, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Feishu authorization {safe_status}</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #111; color: #f4f4f5; display: grid; place-items: center; min-height: 100vh; }}
    main {{ width: min(520px, calc(100vw - 32px)); border: 1px solid #3f3f46; border-radius: 10px; padding: 24px; background: #18181b; }}
    h1 {{ font-size: 20px; margin: 0 0 8px; }}
    p {{ color: #a1a1aa; line-height: 1.6; }}
    code {{ color: #fb923c; word-break: break-all; }}
    button {{ border: 1px solid #52525b; background: #27272a; color: #fff; border-radius: 8px; padding: 9px 12px; cursor: pointer; }}
  </style>
</head>
<body>
  <main>
    <h1>{'飞书授权已完成' if status_value == 'connected' else '飞书授权未完成'}</h1>
    <p>{safe_message}</p>
    <p>状态：<code>{safe_status}</code>{' · Connection: <code>' + safe_connection_id + '</code>' if connection_id else ''}</p>
    <button onclick="window.close()">关闭窗口</button>
  </main>
  <script>
    const payload = {payload_json};
    try {{
      if (window.opener) {{
        window.opener.postMessage(payload, window.location.origin);
      }}
    }} catch (error) {{}}
    setTimeout(() => window.close(), payload.status === "connected" ? 1200 : 5000);
  </script>
</body>
</html>"""


@router.get("/connector-definitions", response_model=StandardResponse[dict])
async def list_connector_definitions(
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
):
    items = source_connection_service.list_connector_definitions()
    return success_response(data={"items": items, "total": len(items)}, message="Retrieved connector definitions")


@router.post("/source-connections", response_model=StandardResponse[dict], status_code=status.HTTP_201_CREATED)
async def create_source_connection(
    payload: SourceConnectionCreate,
    auth: AuthContext = Depends(require_scope(Scope.CONNECTION_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        connection = await source_connection_service.create_connection(
            session=session,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            payload=payload,
        )
        return success_response(data=source_connection_service.connection_payload(connection), message="Source connection created")
    except (ValueError, ConnectorError) as error:
        raise _http_error(error)


@router.get("/source-connections", response_model=StandardResponse[dict])
async def list_source_connections(
    provider: str | None = Query(default=None),
    auth: AuthContext = Depends(require_scope(Scope.CONNECTION_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    connections = await source_connection_service.list_connections(
        session=session,
        tenant_id=auth.tenant_id,
        provider=provider,
    )
    items = [source_connection_service.connection_payload(connection) for connection in connections]
    return success_response(data={"items": items, "total": len(items)}, message="Retrieved source connections")


@router.post("/source-connections/{connection_id}/refresh", response_model=StandardResponse[dict])
async def refresh_source_connection(
    connection_id: str,
    auth: AuthContext = Depends(require_scope(Scope.CONNECTION_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        connection = await source_connection_service.refresh_connection(
            session=session,
            tenant_id=auth.tenant_id,
            connection_id=connection_id,
        )
        return success_response(data=source_connection_service.connection_payload(connection), message="Source connection refreshed")
    except (ValueError, ConnectorError) as error:
        raise _http_error(error)


@router.delete("/source-connections/{connection_id}", response_model=StandardResponse[dict])
async def delete_source_connection(
    connection_id: str,
    auth: AuthContext = Depends(require_scope(Scope.CONNECTION_DELETE)),
    session: AsyncSession = Depends(get_async_session),
):
    ok, resource_count = await source_connection_service.delete_connection(
        session=session,
        tenant_id=auth.tenant_id,
        connection_id=connection_id,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source connection not found")
    return success_response(
        data={"deleted": True, "affected_resource_count": resource_count},
        message="Source connection disconnected",
    )


@router.get("/source-connections/feishu/status", response_model=StandardResponse[dict])
async def feishu_status(
    auth: AuthContext = Depends(require_scope(Scope.CONNECTION_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    data = await source_connection_service.feishu_status(
        session=session,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
    )
    return success_response(data=data, message="Retrieved Feishu connector status")


@router.get("/source-connections/feishu/admin-config", response_model=StandardResponse[dict])
async def get_feishu_admin_config(
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_admin(auth)
    data = await FeishuAdminConfigService.status(session=session, include_admin_details=True)
    data["generated_redirect_uri"] = feishu_callback_url()
    return success_response(data=data, message="Retrieved Feishu config status")


@router.post("/source-connections/feishu/admin-config", response_model=StandardResponse[dict])
async def save_feishu_admin_config(
    payload: FeishuAdminConfigRequest,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_admin(auth)
    await FeishuAdminConfigService.save_config(
        session=session,
        app_id=payload.app_id,
        app_secret=payload.app_secret,
        redirect_uri=payload.redirect_uri,
        scopes=payload.scopes,
    )
    await session.commit()
    return success_response(
        data=await FeishuAdminConfigService.status(session=session, include_admin_details=True),
        message="Saved Feishu config",
    )


@router.post("/source-connections/feishu/admin-config/validate", response_model=StandardResponse[dict])
async def validate_feishu_admin_config(
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_admin(auth)
    data = await FeishuAdminConfigService.validate_config(session=session)
    return success_response(data=data, message="Validated Feishu config")


@router.post("/source-connections/feishu/oauth/start", response_model=StandardResponse[dict])
async def feishu_oauth_start(
    auth: AuthContext = Depends(require_scope(Scope.CONNECTION_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        data = await source_connection_service.feishu_oauth_start(
            session=session,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
        )
        return success_response(data=data, message="Started Feishu OAuth")
    except ConnectorError as error:
        raise _http_error(error)


@router.get("/source-connections/feishu/oauth/callback", response_class=HTMLResponse)
async def feishu_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    session: AsyncSession = Depends(get_async_session),
):
    if not state:
        return HTMLResponse(
            _oauth_callback_html(state=None, status_value="state_expired", message="Missing OAuth state."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if error:
        flow = await FeishuOAuthStateStore.consume(session=session, state=state)
        await FeishuOAuthStateStore.mark_error(
            session=session,
            flow=flow,
            code="authorization_declined",
            message=error_description or error,
        )
        await session.commit()
        return HTMLResponse(
            _oauth_callback_html(
                state=state,
                status_value="authorization_declined",
                message=error_description or "Feishu authorization was declined.",
            )
        )
    if not code:
        flow = await FeishuOAuthStateStore.consume(session=session, state=state)
        await FeishuOAuthStateStore.mark_error(
            session=session,
            flow=flow,
            code="oauth_error",
            message="Missing OAuth code.",
        )
        await session.commit()
        return HTMLResponse(
            _oauth_callback_html(state=state, status_value="oauth_error", message="Missing OAuth code."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        connection = await source_connection_service.feishu_oauth_callback(session=session, code=code, state=state)
        return HTMLResponse(
            _oauth_callback_html(
                state=state,
                status_value="connected",
                message="授权成功，资源选择器会自动刷新。",
                connection_id=str(connection.id),
            )
        )
    except ConnectorError as error:
        return HTMLResponse(
            _oauth_callback_html(state=state, status_value=error.code, message=str(error)),
            status_code=status.HTTP_400_BAD_REQUEST,
        )


@router.get("/source-connections/feishu/oauth/result", response_model=StandardResponse[dict])
async def feishu_oauth_result(
    state: str = Query(..., min_length=1),
    auth: AuthContext = Depends(require_scope(Scope.CONNECTION_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    data = await source_connection_service.feishu_oauth_result(
        session=session,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        state=state,
    )
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "state_not_found", "message": "OAuth state not found"})
    return success_response(data=data, message="Retrieved Feishu OAuth result")


@router.get("/source-connections/{connection_id}/resources", response_model=StandardResponse[dict])
async def list_source_connection_resources(
    connection_id: str,
    provider: str | None = Query(default=None),
    scope: str = Query(default="recent"),
    parent_token: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    query: str | None = Query(default=None),
    page_token: str | None = Query(default=None),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        data = await source_connection_service.list_resources(
            session=session,
            tenant_id=auth.tenant_id,
            connection_id=connection_id,
            scope=scope,
            parent_token=parent_token,
            resource_type=resource_type,
            query=query,
            page_token=page_token,
            page_size=page_size,
        )
        if provider:
            data["provider"] = provider
        return success_response(data=data, message="Retrieved source connection resources")
    except (ValueError, ConnectorError) as error:
        raise _http_error(error)


@router.post("/source-connections/{connection_id}/resources/locate", response_model=StandardResponse[dict])
async def locate_source_connection_resource(
    connection_id: str,
    payload: SourceResourceQuickLocateRequest,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        data = await source_connection_service.locate_resource_from_url(
            session=session,
            tenant_id=auth.tenant_id,
            connection_id=connection_id,
            url=str(payload.url),
        )
        return success_response(data=data, message="Located source connection resource")
    except (ValueError, ConnectorError) as error:
        raise _http_error(error)


@router.get("/source-connections/{connection_id}/resources/{external_id:path}/children", response_model=StandardResponse[dict])
async def list_source_connection_resource_children(
    connection_id: str,
    external_id: str,
    resource_type: str | None = Query(default=None),
    page_token: str | None = Query(default=None),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        data = await source_connection_service.list_resources(
            session=session,
            tenant_id=auth.tenant_id,
            connection_id=connection_id,
            scope="children",
            parent_token=external_id,
            resource_type=resource_type,
            query=None,
            page_token=page_token,
            page_size=page_size,
        )
        return success_response(data=data, message="Retrieved child resources")
    except (ValueError, ConnectorError) as error:
        raise _http_error(error)
