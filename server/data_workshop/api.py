from __future__ import annotations

import os
import re
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from server.auth.dependencies import AuthContext, get_current_auth_context
from server.auth.scopes import Scope
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


router = APIRouter(prefix="/v1")
console_router = APIRouter(prefix="/oc")

LAUNCH_COOKIE = "dw_oc_launch"
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
CONSOLE_TEXT_TYPES = ("text/", "application/javascript", "application/json")
CONSOLE_ROOT_PATH = re.compile(
    r"""(?P<prefix>["'(=:,\s])/(?P<path>api|assets|docs|oauth|openapi\.json|v1)(?P<suffix>[/?"'])"""
)


def get_openconnector_client() -> OpenConnectorClient:
    return OpenConnectorClient()


def _backend_mode() -> Literal["REAL", "TEST"]:
    return "TEST" if os.getenv("DATA_WORKSHOP_BACKEND_MODE", "REAL").strip().upper() == "TEST" else "REAL"


def _scoped_success(
    data: Any,
    upstream_scope: Literal["admin", "runtime", "public", "admin+public"],
    message: str = "Operation completed successfully",
) -> JSONResponse:
    return JSONResponse(
        success_response(data=data, message=message),
        headers={"X-Data-Workshop-Upstream-Scope": upstream_scope},
    )


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
    if not isinstance(config, dict):
        raise OpenConnectorError("OpenConnector returned invalid connection documentation metadata")
    if identity is None:
        identity = {}
    if not isinstance(identity, dict):
        raise OpenConnectorError("OpenConnector returned invalid identity metadata")

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

    jwks_status = identity.get("jwksStatus") or identity.get("jwks_status")
    identity_configured = bool(identity.get("issuer") and (identity.get("jwksUri") or identity.get("jwks_uri")))
    identity_ready = identity_configured and jwks_status in {"healthy", "ready"}
    public_identity = {
        "status": "ready" if identity_ready else "unverified" if identity_configured else "unconfigured",
        "issuer": identity.get("issuer"),
        "audience": [identity["audience"]] if isinstance(identity.get("audience"), str) else identity.get("audience"),
        "user_pool_ref": identity.get("userPoolRef") or identity.get("user_pool_ref"),
        "jwks_status": jwks_status or (
            "verification required" if identity.get("jwksUri") or identity.get("jwks_uri") else "unconfigured"
        ),
        "jwks_last_refresh_at": identity.get("jwksLastRefreshAt") or identity.get("jwks_last_refresh_at"),
    }
    return {"mcp": public_mcp, "identity": public_identity}


def _docs_config(client: OpenConnectorClient, identity: Any, openapi: Any) -> dict[str, Any]:
    if not isinstance(openapi, dict) or not str(openapi.get("openapi") or "").startswith("3."):
        raise OpenConnectorError("OpenConnector returned invalid OpenAPI metadata")
    endpoint = urljoin(f"{client.public_url}/", "mcp")
    return _public_docs_config(
        {
            "endpoint": endpoint,
            "protocol": "MCP Streamable HTTP",
            "api_reference_url": urljoin(f"{client.public_url}/", "docs"),
            "openapi_url": urljoin(f"{client.public_url}/", "openapi.json"),
            "sdk_languages": ["Python", "TypeScript"],
        },
        identity,
    )


def _runtime_test_bearer() -> str:
    test_token = os.getenv("OPENCONNECTOR_TEST_RUNTIME_TOKEN", "").strip()
    if test_token:
        return test_token
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "CONTROLLED_USER_NOT_CONFIGURED",
            "message": "只读测试器尚未配置受控用户凭据，请联系管理员后重试",
        },
    )


def _items(data: Any) -> list[dict[str, Any]]:
    unwrapped = _unwrap(data)
    if isinstance(unwrapped, list):
        return [item for item in unwrapped if isinstance(item, dict)]
    if isinstance(unwrapped, dict) and isinstance(unwrapped.get("items"), list):
        return [item for item in unwrapped["items"] if isinstance(item, dict)]
    return []


def _connection_view(connection: dict[str, Any]) -> dict[str, Any]:
    status = connection.get("status")
    if status == "active":
        status = "ready"
    elif status == "disconnected":
        status = "disabled"
    return {
        "id": str(connection.get("id") or ""),
        "name": str(
            connection.get("displayName")
            or (connection.get("profile") or {}).get("displayName")
            or connection.get("connectionName")
            or connection.get("alias")
            or ""
        ),
        "provider": str(connection.get("service") or ""),
        "description": connection.get("accountLabel") or (connection.get("profile") or {}).get("accountId"),
        "status": status or ("ready" if connection.get("configured") else "pending"),
        "action_count": connection.get("actionCount"),
        "updated_at": connection.get("updatedAt"),
    }


def _provider_view(provider: dict[str, Any]) -> dict[str, Any]:
    categories = provider.get("categories")
    category = ""
    if isinstance(categories, list) and categories:
        first = categories[0]
        category = str(first.get("displayName") or first.get("id") or "") if isinstance(first, dict) else str(first)
    return {
        "id": str(provider.get("service") or provider.get("id") or ""),
        "name": str(provider.get("displayName") or provider.get("name") or provider.get("service") or ""),
        "category": category or str(provider.get("category") or ""),
        "description": str(provider.get("description") or provider.get("scenario") or ""),
        "color": provider.get("color"),
        "available": bool(provider.get("available", True)),
    }


def _connection_matches(connection: dict[str, Any], connection_id: str) -> bool:
    return str(connection.get("id") or "") == connection_id


def _is_read_action(action: dict[str, Any]) -> bool:
    name = str(action.get("name") or action.get("id") or "").lower()
    return name.startswith(
        (
            "get",
            "list",
            "read",
            "search",
            "find",
            "query",
            "describe",
            "retrieve",
            "fetch",
            "lookup",
            "export",
            "download",
            "count",
            "inspect",
            "preview",
        )
    )


def _action_view(action: dict[str, Any]) -> dict[str, Any]:
    read_only = bool(action.get("readOnly", action.get("read_only", _is_read_action(action))))
    return {
        "id": str(action.get("id") or ""),
        "name": str(action.get("name") or action.get("id") or ""),
        "description": action.get("description"),
        "risk": str(action.get("risk") or ("low" if read_only else "high")),
        "read_only": read_only,
    }


def _decision_reasons(decision: dict[str, Any]) -> list[dict[str, Any]]:
    effect = "allow" if decision.get("allowed") else "deny"
    return [
        {
            "grant_id": str(check.get("grantId") or ""),
            "source": str(check.get("reason") or check.get("source") or check.get("outcome") or ""),
            "effect": effect,
        }
        for check in decision.get("checks", [])
        if isinstance(check, dict)
    ]


def _grant_view(grant: dict[str, Any], subjects: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    subject_id = str(grant.get("subject") or grant.get("subject_id") or "")
    subject = (subjects or {}).get(subject_id)
    revoked = grant.get("revokedAt") or grant.get("revoked_at")
    return {
        "id": str(grant.get("id") or ""),
        "connection_id": str(grant.get("connectionId") or grant.get("connection_id") or ""),
        "subject_type": str(grant.get("subjectType") or grant.get("subject_type") or "user"),
        "subject_id": subject_id,
        "subject_display_snapshot": str(
            grant.get("subjectDisplaySnapshot")
            or grant.get("subject_display_snapshot")
            or (subject or {}).get("display_name")
            or subject_id
        ),
        "role_id": str(grant.get("role") or grant.get("role_id") or "custom"),
        "effect": str(grant.get("effect") or "allow"),
        "action_scope": list(grant.get("customActions") or grant.get("action_scope") or []),
        "status": "revoked" if revoked else str(grant.get("status") or "active"),
        "updated_at": grant.get("updatedAt") or grant.get("updated_at"),
        "updated_by": grant.get("updatedBy") or grant.get("updated_by"),
        "version": grant.get("version"),
    }


def _subject_views(subjects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for subject in subjects:
        sub = str(subject.get("sub") or subject.get("id") or "")
        if sub:
            result[("user", sub)] = {
                "id": sub,
                "type": "user",
                "display_name": str(subject.get("displayName") or subject.get("display_name") or sub),
                "secondary_text": subject.get("email") or subject.get("userPoolRef"),
                "_runtime_subject": subject,
            }
        for group in subject.get("groups") or []:
            group_id = str(group)
            result[("group", group_id)] = {
                "id": group_id,
                "type": "group",
                "display_name": group_id,
                "secondary_text": "Identity 用户组",
            }
    return list(result.values())


def _public_subject(subject: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in subject.items() if not key.startswith("_")}


def _grant_input(payload: GrantPayload, *, partial: bool = False) -> dict[str, Any]:
    if partial:
        return {
            "role": payload.role_id,
            "effect": payload.effect,
            "customActions": payload.action_scope if payload.role_id == "custom" else [],
        }
    return {
        "connectionId": payload.connection_id,
        "subjectType": payload.subject_type,
        "subject": payload.subject_id,
        "role": payload.role_id,
        "effect": payload.effect,
        "customActions": payload.action_scope if payload.role_id == "custom" else [],
    }


def _audit_view(event: dict[str, Any]) -> dict[str, Any]:
    decision = event.get("decision") if isinstance(event.get("decision"), dict) else {}
    subject = event.get("subject") if isinstance(event.get("subject"), dict) else {}
    return {
        "id": str(event.get("id") or ""),
        "event_type": str(decision.get("code") or ("Access allowed" if decision.get("allowed") else "Access denied")),
        "subject_display": subject.get("displayName") or subject.get("sub"),
        "action_name": event.get("actionId"),
        "decision": "allow" if decision.get("allowed") else "deny",
        "created_at": event.get("createdAt"),
        "request_id": event.get("requestId"),
    }


def _rewrite_console_content(content: bytes, content_type: str) -> bytes:
    if not any(content_type.lower().startswith(prefix) for prefix in CONSOLE_TEXT_TYPES):
        return content
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    return CONSOLE_ROOT_PATH.sub(
        lambda match: f"{match.group('prefix')}/oc/{match.group('path')}{match.group('suffix')}",
        text,
    ).encode()


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


@router.get("/bootstrap")
async def bootstrap(auth: AuthContext = Depends(require_workshop_member)):
    client = get_openconnector_client()
    return success_response(
        data={
            "backend_mode": _backend_mode(),
            "openconnector_configured": client.configured,
            "navigation": ["home", "connections", "knowledge", "skill", "sessions"],
            "tenant_id": str(auth.tenant_id),
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
async def list_connections(
    search: str | None = Query(default=None),
    auth: AuthContext = Depends(require_workshop_member),
):
    client = get_openconnector_client()
    try:
        connections = [_connection_view(connection) for connection in await _list_apps(client, str(auth.tenant_id))]
        if search:
            needle = search.casefold()
            connections = [
                connection
                for connection in connections
                if needle in f"{connection['name']} {connection['provider']}".casefold()
            ]
        return _scoped_success(connections, "admin")
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.get("/providers")
async def list_providers(auth: AuthContext = Depends(require_workshop_member)):
    client = get_openconnector_client()
    try:
        providers = _items(await client.request_admin("GET", "/api/providers", tenant_id=str(auth.tenant_id)))
        return _scoped_success([_provider_view(provider) for provider in providers], "admin")
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.get("/connections/{connection_id}")
async def get_connection(
    connection_id: str,
    auth: AuthContext = Depends(require_workshop_member),
):
    client = get_openconnector_client()
    try:
        connections = await _list_apps(client, str(auth.tenant_id))
        connection = next((item for item in connections if _connection_matches(item, connection_id)), None)
        if connection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
        return _scoped_success(_connection_view(connection), "admin")
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.get("/connections/{connection_id}/actions")
async def get_connection_actions(
    connection_id: str,
    auth: AuthContext = Depends(require_workshop_member),
):
    client = get_openconnector_client()
    try:
        connections = await _list_apps(client, str(auth.tenant_id))
        connection = next((item for item in connections if _connection_matches(item, connection_id)), None)
        if connection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
        actions = _items(
            await client.request_admin(
                "GET",
                "/api/actions",
                tenant_id=str(auth.tenant_id),
            )
        )
        actions = [action for action in actions if action.get("service") == connection.get("service")]
        return _scoped_success([_action_view(action) for action in actions], "admin")
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.get("/connections/{connection_id}/access")
async def get_connection_access(
    connection_id: str,
    auth: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    try:
        tenant_id = str(auth.tenant_id)
        grants, subjects = await _access_records(client, tenant_id)
        subject_map = {subject["id"]: subject for subject in _subject_views(subjects)}
        return _scoped_success(
            data=[
                _grant_view(grant, subject_map)
                for grant in grants
                if str(grant.get("connectionId") or grant.get("connection_id")) == connection_id
            ],
            upstream_scope="admin",
        )
    except OpenConnectorError as error:
        _raise_upstream(error)


async def _list_apps(client: OpenConnectorClient, tenant_id: str) -> list[dict[str, Any]]:
    return _items(await client.request_admin("GET", "/api/connections", tenant_id=tenant_id))


@router.get("/identity/subjects")
async def search_subjects(
    query: str = Query(default=""),
    subject_type: Literal["user", "group", "all"] = Query(default="all"),
    auth: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    try:
        subjects = _subject_views(
            _items(
                await client.request_admin(
                    "GET",
                    "/api/identity/subjects",
                    tenant_id=str(auth.tenant_id),
                )
            )
        )
        needle = query.strip().casefold()
        data = [
            {key: value for key, value in subject.items() if not key.startswith("_")}
            for subject in subjects
            if (subject_type == "all" or subject["type"] == subject_type)
            and (
                not needle
                or needle in str(subject["display_name"]).casefold()
                or needle in str(subject["id"]).casefold()
                or needle in str(subject.get("secondary_text") or "").casefold()
            )
        ]
        return _scoped_success(data, "admin")
    except OpenConnectorError as error:
        _raise_upstream(error)


async def _access_records(
    client: OpenConnectorClient,
    tenant_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grants = _items(
        await client.request_admin(
            "GET",
            "/api/access-grants",
            tenant_id=tenant_id,
        )
    )
    subjects = _items(await client.request_admin("GET", "/api/identity/subjects", tenant_id=tenant_id))
    return grants, subjects


@router.get("/identity-provider")
async def get_identity_provider(
    auth: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    try:
        identity = _unwrap(await client.request_admin("GET", "/api/identity-provider", tenant_id=str(auth.tenant_id)))
        if identity is None:
            identity = {}
        if not isinstance(identity, dict):
            raise OpenConnectorError("OpenConnector returned invalid identity metadata")
        jwks_status = identity.get("jwksStatus") or identity.get("jwks_status")
        identity_configured = bool(identity.get("issuer") and (identity.get("jwksUri") or identity.get("jwks_uri")))
        identity_ready = identity_configured and jwks_status in {"healthy", "ready"}
        return _scoped_success(
            data={
                "status": "ready" if identity_ready else "unverified" if identity_configured else "unconfigured",
                "user_pool_ref": identity.get("userPoolRef") or identity.get("user_pool_ref"),
                "jwks_status": jwks_status or (
                    "verification required"
                    if identity.get("jwksUri") or identity.get("jwks_uri")
                    else "unconfigured"
                ),
                "jwks_last_refresh_at": identity.get("jwksLastRefreshAt") or identity.get("jwks_last_refresh_at"),
            },
            upstream_scope="admin",
        )
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.post("/access-grants")
async def create_access_grant(
    payload: GrantPayload,
    auth: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    try:
        data = await client.request_admin(
            "POST",
            "/api/access-grants",
            json=_grant_input(payload),
            tenant_id=str(auth.tenant_id),
        )
        created = _unwrap(data)
        if not isinstance(created, dict):
            raise OpenConnectorError("OpenConnector returned an invalid AccessGrant")
        return _scoped_success(_grant_view(created), "admin", message="Access grant created")
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.patch("/access-grants/{grant_id}")
async def update_access_grant(
    grant_id: str,
    payload: GrantPayload,
    auth: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    try:
        data = await client.request_admin(
            "PATCH",
            f"/api/access-grants/{grant_id}",
            json=_grant_input(payload, partial=True),
            tenant_id=str(auth.tenant_id),
        )
        updated = _unwrap(data)
        if not isinstance(updated, dict):
            raise OpenConnectorError("OpenConnector returned an invalid AccessGrant")
        return _scoped_success(_grant_view(updated), "admin", message="Access grant updated")
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.post("/access-grants/{grant_id}:revoke")
async def revoke_access_grant(
    grant_id: str,
    auth: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    try:
        data = await client.request_admin(
            "POST",
            f"/api/access-grants/{grant_id}/revoke",
            tenant_id=str(auth.tenant_id),
        )
        revoked = _unwrap(data)
        if not isinstance(revoked, dict):
            raise OpenConnectorError("OpenConnector returned an invalid AccessGrant")
        return _scoped_success(_grant_view(revoked), "admin", message="Access grant revoked")
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.post("/access:preview")
async def preview_access(
    payload: PreviewPayload,
    auth: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    try:
        tenant_id = str(auth.tenant_id)
        subjects = _subject_views(
            _items(await client.request_admin("GET", "/api/identity/subjects", tenant_id=tenant_id))
        )
        subject_view = next(
            (subject for subject in subjects if subject["type"] == "user" and subject["id"] == payload.subject_id),
            None,
        )
        if subject_view is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Identity subject not found")
        runtime_subject = subject_view.get("_runtime_subject")
        connections = await _list_apps(client, tenant_id)
        selected_connections = [
            connection
            for connection in connections
            if payload.connection_id is None or str(connection.get("id")) == payload.connection_id
        ]
        preview_connections = []
        for connection in selected_connections:
            action_items = _items(
                await client.request_admin(
                    "GET",
                    "/api/actions",
                    tenant_id=tenant_id,
                )
            )
            action_items = [action for action in action_items if action.get("service") == connection.get("service")]
            allowed_actions = []
            reasons: list[dict[str, Any]] = []
            for action in action_items:
                result = _unwrap(
                    await client.request_admin(
                        "POST",
                        "/api/access/preview",
                        json={
                            "subject": runtime_subject,
                            "connectionId": connection.get("id"),
                            "actionId": action.get("id"),
                        },
                        tenant_id=tenant_id,
                    )
                )
                decision = result.get("decision", {}) if isinstance(result, dict) else {}
                if decision.get("allowed"):
                    allowed_actions.append(_action_view(action))
                reasons.extend(_decision_reasons(decision))
            preview_connections.append(
                {
                    "connection_id": str(connection.get("id") or ""),
                    "connection_name": _connection_view(connection)["name"],
                    "actions": allowed_actions,
                    "reasons": reasons,
                }
            )
        public_subject = _public_subject(subject_view)
        return _scoped_success(
            data={"subject": public_subject, "connections": preview_connections},
            upstream_scope="admin",
            message="Access preview calculated",
        )
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.get("/access/audit")
async def get_access_audit(
    connection_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=100),
    auth: AuthContext = Depends(require_workshop_admin),
):
    client = get_openconnector_client()
    try:
        data = _items(
            await client.request_admin(
                "GET",
                "/api/access/audit",
                params={"limit": limit},
                tenant_id=str(auth.tenant_id),
            )
        )
        events = []
        for event in data:
            event_connection_id = event.get("connectionId") or event.get("connection_id")
            if connection_id and event_connection_id != connection_id:
                continue
            events.append(_audit_view(event))
        return _scoped_success(events, "admin")
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.get("/connection-docs/config")
async def get_connection_docs_config(
    auth: AuthContext = Depends(require_workshop_member),
):
    client = get_openconnector_client()
    try:
        tenant_id = str(auth.tenant_id)
        identity = _unwrap(await client.request_admin("GET", "/api/identity-provider", tenant_id=tenant_id))
        openapi = _unwrap(await client.request_admin("GET", "/openapi.json", tenant_id=tenant_id))
        return _scoped_success(
            {**_docs_config(client, identity, openapi), "backend_mode": _backend_mode()},
            "admin",
        )
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.get("/connection-docs/status")
async def get_connection_docs_status(
    auth: AuthContext = Depends(require_workshop_member),
):
    client = get_openconnector_client()
    try:
        health = _unwrap(await client.request_public("GET", "/health"))
        identity = _unwrap(
            await client.request_admin("GET", "/api/identity-provider", tenant_id=str(auth.tenant_id))
        )
        process_healthy = isinstance(health, dict) and bool(health.get("ok"))
        identity_configured = isinstance(identity, dict) and bool(
            identity.get("issuer") and (identity.get("jwksUri") or identity.get("jwks_uri"))
        )
        jwks_status = identity.get("jwksStatus") or identity.get("jwks_status") if isinstance(identity, dict) else None
        identity_ready = identity_configured and jwks_status in {"healthy", "ready"}
        return _scoped_success(
            data={
                "status": "healthy" if process_healthy and identity_ready else "degraded" if process_healthy else "unavailable",
                "protocol": "streamable-http",
                "backend_mode": _backend_mode(),
                "identity_status": "ready" if identity_ready else "unverified" if identity_configured else "unconfigured",
            },
            upstream_scope="admin+public",
        )
    except OpenConnectorError as error:
        _raise_upstream(error)


@router.post("/connection-docs/read-only-tests")
async def run_read_only_test(
    payload: ReadOnlyTestPayload,
    request: Request,
    auth: AuthContext = Depends(require_workshop_member),
):
    client = get_openconnector_client()
    try:
        if payload.operation == "health":
            result = await client.request_public("GET", "/health")
        elif payload.operation == "identity":
            result = await client.request_admin(
                "GET",
                "/api/identity-provider",
                tenant_id=str(auth.tenant_id),
            )
        else:
            method = "tools/list" if payload.operation == "tools_list" else "tools/call"
            params = {} if payload.operation == "tools_list" else {"name": "list_connections", "arguments": {}}
            result = await client.request_runtime(
                "POST",
                "/mcp",
                bearer_token=_runtime_test_bearer(),
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                tenant_id=str(auth.tenant_id),
            )
        scope = "public" if payload.operation == "health" else "admin" if payload.operation == "identity" else "runtime"
        return _scoped_success(_unwrap(result), scope, message="Read-only test completed")
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
    content_type = headers.get("content-type", "")
    content = _rewrite_console_content(upstream.content, content_type)
    return Response(content=content, status_code=upstream.status_code, headers=headers)
