from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from server.auth.dependencies import AuthContext, get_current_auth_context
from server.auth.scopes import Scope
from server.auth.tenant_context import get_tenant_id
from server.data_workshop.adapters.openconnector import OpenConnectorClient, OpenConnectorError
from server.data_workshop.launch_sessions import launch_sessions
from server.schemas.standard_response import success_response


async def require_workshop_member(
    auth: AuthContext = Depends(get_current_auth_context()),
) -> AuthContext:
    if not auth.has_scope(Scope.CONNECTION_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Connection read permission required")
    return auth


async def require_workshop_admin(
    auth: AuthContext = Depends(get_current_auth_context()),
) -> AuthContext:
    if not auth.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return auth


router = APIRouter(prefix="/v1", dependencies=[Depends(require_workshop_member)])
console_router = APIRouter(prefix="/oc")

LAUNCH_COOKIE = "dw_oc_launch"
READ_ONLY_TESTS = {
    "health": ("GET", "/v1/mcp/status"),
    "identity": ("GET", "/v1/identity-provider"),
    "tools_list": ("POST", "/v1/mcp/tests/tools-list"),
    "list_connections": ("POST", "/v1/mcp/tests/read-only"),
}
SENSITIVE_KEYS = {
    "access_token",
    "admin_token",
    "api_key",
    "authorization",
    "client_secret",
    "credential",
    "credentials",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
}


def get_openconnector_client() -> OpenConnectorClient:
    return OpenConnectorClient()


def _tenant() -> str:
    tenant_id = get_tenant_id()
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant context required")
    return str(tenant_id)


def _unwrap(data: Any) -> Any:
    if isinstance(data, dict) and "data" in data and ("success" in data or "ok" in data):
        data = data["data"]
    return _remove_sensitive_fields(data)


def _remove_sensitive_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _remove_sensitive_fields(item)
            for key, item in value.items()
            if key.lower().replace("-", "_") not in SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [_remove_sensitive_fields(item) for item in value]
    return value


def _raise_upstream(error: OpenConnectorError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": "OPENCONNECTOR_ERROR", "message": str(error), "upstream_status": error.status_code},
    )


def _https_url(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise OpenConnectorError(f"OpenConnector {field_name} is missing", status_code=502)
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise OpenConnectorError(f"OpenConnector {field_name} must be an HTTPS URL", status_code=502)
    return value


def _public_docs_config(config: Any, identity: Any) -> dict[str, Any]:
    if not isinstance(config, dict) or not isinstance(identity, dict):
        raise OpenConnectorError("OpenConnector returned invalid connection documentation metadata")

    endpoint = _https_url(config.get("endpoint"), "MCP endpoint")
    public_mcp: dict[str, Any] = {
        "endpoint": endpoint,
        "protocol": str(config.get("protocol") or "MCP Streamable HTTP"),
        "workbuddy_config": {
            "name": "Data Workshop",
            "transport": "streamable-http",
            "url": endpoint,
            "auth": "oauth",
        },
        "generic_config": {
            "mcpServers": {
                "data-workshop": {
                    "url": endpoint,
                    "transport": "streamable-http",
                    "authentication": "oauth",
                }
            }
        },
        "sdk_languages": [
            language
            for language in config.get("sdk_languages", [])
            if isinstance(language, str) and language in {"Python", "TypeScript"}
        ],
    }
    for source_key in ("api_reference_url", "openapi_url"):
        if config.get(source_key):
            public_mcp[source_key] = _https_url(config[source_key], source_key)

    public_identity = {
        key: identity[key]
        for key in ("status", "issuer", "audience", "user_pool_ref", "jwks_status", "jwks_last_refresh_at")
        if key in identity
    }
    return {"mcp": public_mcp, "identity": public_identity}


class GrantPayload(BaseModel):
    connection_id: str
    subject_type: Literal["user", "group"]
    subject_id: str
    subject_display_snapshot: str
    role_id: Literal["reader", "operator", "custom"]
    effect: Literal["allow", "deny"] = "allow"
    action_scope: list[str] = Field(default_factory=list)
    version: int | None = None


class PreviewPayload(BaseModel):
    connection_id: str | None = None
    subject_id: str


class ReadOnlyTestPayload(BaseModel):
    operation: Literal["health", "identity", "tools_list", "list_connections"]
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("/bootstrap")
async def bootstrap():
    client = get_openconnector_client()
    return success_response(
        data={
            "openconnector_configured": client.configured,
            "navigation": ["home", "connections", "knowledge", "skill", "sessions"],
        },
        message="Data Workshop bootstrap retrieved",
    )


@router.post("/openconnector/launch-sessions")
async def create_launch_session(
    response: Response,
    auth: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    if not client.configured:
        raise HTTPException(
            status_code=503,
            detail={"code": "OPENCONNECTOR_NOT_CONFIGURED", "message": "OpenConnector is not configured"},
        )
    session_id, session = launch_sessions.create(str(auth.tenant_id), str(auth.user_id))
    response.set_cookie(
        key=LAUNCH_COOKIE,
        value=session_id,
        max_age=launch_sessions.ttl_seconds,
        expires=launch_sessions.ttl_seconds,
        path="/oc",
        secure=True,
        httponly=True,
        samesite="strict",
    )
    return success_response(
        data={"launch_url": "/oc/?embed=studio", "expires_at": session.expires_at},
        message="Launch session created",
    )


@router.get("/connections")
async def list_connections(search: str | None = Query(default=None)):
    client = get_openconnector_client()
    try:
        return success_response(
            data=_unwrap(await client.request("GET", "/v1/connections", params={"search": search}, tenant_id=_tenant()))
        )
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.get("/providers")
async def list_providers():
    client = get_openconnector_client()
    try:
        return success_response(data=_unwrap(await client.request("GET", "/v1/providers", tenant_id=_tenant())))
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.get("/connections/{connection_id}")
async def get_connection(connection_id: str):
    client = get_openconnector_client()
    try:
        return success_response(
            data=_unwrap(await client.request("GET", f"/v1/connections/{connection_id}", tenant_id=_tenant()))
        )
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.get("/connections/{connection_id}/actions")
async def get_connection_actions(connection_id: str):
    client = get_openconnector_client()
    try:
        data = await client.request(
            "GET", "/v1/actions", params={"connection_id": connection_id}, tenant_id=_tenant()
        )
        return success_response(data=_unwrap(data))
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.get("/connections/{connection_id}/access")
async def get_connection_access(
    connection_id: str,
    _: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    try:
        grants = await client.request(
            "GET", "/v1/access-grants", params={"connection_id": connection_id}, tenant_id=_tenant()
        )
        return success_response(data=_unwrap(grants))
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.get("/identity/subjects")
async def search_subjects(
    query: str = Query(default=""),
    subject_type: Literal["user", "group", "all"] = Query(default="all"),
    _: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    try:
        data = await client.request(
            "GET",
            "/v1/identity/subjects",
            params={"query": query, "subject_type": subject_type},
            tenant_id=_tenant(),
        )
        return success_response(data=_unwrap(data))
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.post("/access-grants")
async def create_access_grant(
    payload: GrantPayload,
    _: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    try:
        data = await client.request(
            "POST", "/v1/access-grants", json=payload.model_dump(exclude_none=True), tenant_id=_tenant()
        )
        return success_response(data=_unwrap(data), message="Access grant created")
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.patch("/access-grants/{grant_id}")
async def update_access_grant(
    grant_id: str,
    payload: GrantPayload,
    _: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    try:
        data = await client.request(
            "PATCH",
            f"/v1/access-grants/{grant_id}",
            json=payload.model_dump(exclude_none=True),
            tenant_id=_tenant(),
        )
        return success_response(data=_unwrap(data), message="Access grant updated")
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.post("/access-grants/{grant_id}:revoke")
async def revoke_access_grant(
    grant_id: str,
    _: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    try:
        data = await client.request("POST", f"/v1/access-grants/{grant_id}:revoke", tenant_id=_tenant())
        return success_response(data=_unwrap(data), message="Access grant revoked")
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.post("/access:preview")
async def preview_access(
    payload: PreviewPayload,
    _: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    try:
        data = await client.request(
            "POST", "/v1/access:preview", json=payload.model_dump(exclude_none=True), tenant_id=_tenant()
        )
        return success_response(data=_unwrap(data), message="Access preview calculated")
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.get("/access/audit")
async def get_access_audit(
    connection_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=100),
    _: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    try:
        data = await client.request(
            "GET",
            "/v1/access/audit",
            params={"connection_id": connection_id, "limit": limit},
            tenant_id=_tenant(),
        )
        return success_response(data=_unwrap(data))
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.get("/connection-docs/config")
async def get_connection_docs_config():
    client = get_openconnector_client()
    try:
        config = _unwrap(await client.request("GET", "/v1/mcp/config", tenant_id=_tenant()))
        identity = _unwrap(await client.request("GET", "/v1/identity-provider", tenant_id=_tenant()))
        return success_response(data=_public_docs_config(config, identity))
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.get("/connection-docs/status")
async def get_connection_docs_status():
    client = get_openconnector_client()
    try:
        return success_response(data=_unwrap(await client.request("GET", "/v1/mcp/status", tenant_id=_tenant())))
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.post("/connection-docs/read-only-tests")
async def run_read_only_test(payload: ReadOnlyTestPayload):
    client = get_openconnector_client()
    method, path = READ_ONLY_TESTS[payload.operation]
    body = None
    if method == "POST":
        body = {"operation": payload.operation, "arguments": payload.arguments}
    try:
        result = await client.request(method, path, json=body, tenant_id=_tenant())
        return success_response(data=_unwrap(result), message="Read-only test completed")
    except OpenConnectorError as error:
        _raise_upstream(error)


@console_router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_openconnector_console(
    request: Request,
    path: str,
    launch_session: str | None = Cookie(default=None, alias=LAUNCH_COOKIE),
):
    session = launch_sessions.get(launch_session)
    if session is None:
        raise HTTPException(status_code=401, detail="A valid Data Workshop launch session is required")
    client = get_openconnector_client()
    try:
        upstream = await client.proxy(
            request.method,
            path,
            query=request.scope.get("query_string", b""),
            body=await request.body(),
            content_type=request.headers.get("content-type"),
            tenant_id=session.tenant_id,
        )
    except OpenConnectorError as error:
        _raise_upstream(error)

    excluded = {
        "connection",
        "content-encoding",
        "content-length",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "set-cookie",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
    headers = {key: value for key, value in upstream.headers.items() if key.lower() not in excluded}
    if "location" in headers:
        try:
            headers["location"] = client.public_proxy_location(headers["location"])
        except OpenConnectorError as error:
            _raise_upstream(error)
    return Response(content=upstream.content, status_code=upstream.status_code, headers=headers)
