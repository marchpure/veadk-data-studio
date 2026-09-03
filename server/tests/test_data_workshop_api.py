from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.data_workshop import api
from server.data_workshop.adapters.openconnector import OpenConnectorClient, OpenConnectorError
from server.data_workshop.launch_sessions import LaunchSessionStore


class FakeOpenConnector:
    configured = True

    def __init__(self):
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        if path == "/v1/connections":
            raise OpenConnectorError("OpenConnector rejected the request", status_code=404)
        if method == "POST" and path == "/v1/access-grants":
            payload = kwargs["json"]
            return {
                "id": "grant-created",
                **payload,
                "createdAt": "2026-09-04T00:00:00Z",
                "updatedAt": "2026-09-04T00:00:00Z",
            }
        responses = {
            "/v1/providers": [
                {
                    "service": "oracle",
                    "displayName": "Oracle",
                    "categories": [{"id": "data", "displayName": "Data"}],
                    "scenario": "database",
                    "authTypes": ["custom_credential"],
                }
            ],
            "/v1/apps": [
                {
                    "id": "oracle-prod",
                    "service": "oracle",
                    "status": "active",
                    "alias": "production",
                    "authType": "custom_credential",
                    "displayName": "Oracle Production",
                    "accountLabel": "Oracle Production",
                    "isDefault": True,
                    "scopes": [],
                }
            ],
            "/v1/actions": [
                {
                    "id": "oracle.query_rows",
                    "service": "oracle",
                    "name": "query_rows",
                    "description": "Query rows",
                }
            ],
            "/v1/access-grants": [
                {
                    "id": "grant-1",
                    "subjectType": "group",
                    "subject": "finance",
                    "connectionId": "oracle-prod",
                    "role": "reader",
                    "effect": "allow",
                    "customActions": [],
                    "createdAt": "2026-09-04T00:00:00Z",
                    "updatedAt": "2026-09-04T00:00:00Z",
                }
            ],
            "/v1/mcp/config": {
                "endpoint": "https://connector.example.com/mcp",
                "admin_token": "must-not-leak",
                "client_secret": "must-not-leak",
            },
            "/v1/identity-provider": {
                "issuer": "https://identity.example.com",
                "audience": "data-workshop",
                "jwksUri": "https://identity.example.com/jwks",
                "userPoolRef": "dw-users",
                "subjectClaim": "sub",
                "groupsClaim": "groups",
            },
            "/v1/identity/subjects": [
                {
                    "issuer": "https://identity.example.com",
                    "audience": "data-workshop",
                    "userPoolRef": "dw-users",
                    "sub": "alice",
                    "groups": ["finance"],
                }
            ],
            "/v1/health": {"ok": True, "runtime": "openconnector"},
            "/v1/mcp/status": {"status": "healthy"},
            "/v1/mcp/tests/tools-list": {"tools": [{"name": "list_connections"}]},
        }
        if path == "/v1/access:preview":
            action_id = kwargs["json"]["actionId"]
            return {
                "subject": kwargs["json"]["subject"],
                "connectionId": "oracle-prod",
                "actionId": action_id,
                "decision": {
                    "allowed": True,
                    "checks": [{"source": "access_grant", "outcome": "allow_match", "grantId": "grant-1"}],
                },
                "policyVersion": 1,
            }
        return responses.get(path, {"ok": True})

    async def proxy(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        self.calls.append((method, path, kwargs))
        return SimpleNamespace(
            status_code=200,
            content=b"<html>console</html>",
            headers=httpx.Headers(
                {
                    "content-type": "text/html",
                    "content-encoding": "gzip",
                    "set-cookie": "upstream=forbidden",
                }
            ),
        )


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeOpenConnector:
    fake = FakeOpenConnector()
    monkeypatch.setattr(api, "get_openconnector_client", lambda: fake)
    return fake


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    app.include_router(api.console_router)
    admin = SimpleNamespace(
        tenant_id="tenant-a",
        user_id="user-admin",
        is_admin=True,
        has_scope=lambda _: True,
    )

    app.dependency_overrides[api.require_workshop_member] = lambda: admin
    app.dependency_overrides[api.require_workshop_admin] = lambda: admin
    yield TestClient(app)


def test_adapter_only_accepts_versioned_control_plane_paths() -> None:
    adapter = OpenConnectorClient(base_url="https://connector.example.com", admin_token="secret")
    with pytest.raises(ValueError, match="/v1"):
        adapter._url("/api/connections")


@pytest.mark.asyncio
async def test_console_proxy_rejects_absolute_url_path() -> None:
    adapter = OpenConnectorClient(base_url="https://connector.example.com", admin_token="secret")

    with pytest.raises(OpenConnectorError, match="Invalid"):
        await adapter.proxy(
            "GET",
            "https://attacker.example/collect",
            query=b"",
            body=b"",
            content_type=None,
            tenant_id="tenant-a",
        )


def test_console_proxy_rewrites_same_upstream_redirect_and_rejects_other_hosts() -> None:
    adapter = OpenConnectorClient(base_url="https://connector.example.com", admin_token="secret")

    assert adapter.public_proxy_location("/login?next=%2Factions") == "/oc/login?next=%2Factions"
    assert adapter.public_proxy_location("https://connector.example.com/login") == "/oc/login"
    with pytest.raises(OpenConnectorError, match="unsafe redirect"):
        adapter.public_proxy_location("https://attacker.example/collect")


def test_console_proxy_rewrites_root_relative_assets_and_api_paths() -> None:
    source = (
        b'<script src="/assets/app.js"></script><a href="/docs">Docs</a>'
        b'<script>fetch("/api/providers");fetch("/v1/actions");location="/oauth/start"</script>'
    )

    rewritten = api._rewrite_console_content(source, "text/html; charset=utf-8").decode()

    assert 'src="/oc/assets/app.js"' in rewritten
    assert 'href="/oc/docs"' in rewritten
    assert 'fetch("/oc/api/providers")' in rewritten
    assert 'fetch("/oc/v1/actions")' in rewritten
    assert 'location="/oc/oauth/start"' in rewritten
    assert api._rewrite_console_content(b"\x89PNG", "image/png") == b"\x89PNG"


def test_docs_aggregates_only_non_sensitive_v1_metadata(client: TestClient, fake_client: FakeOpenConnector) -> None:
    response = client.get("/api/v1/connection-docs/config")

    assert response.status_code == 200
    assert response.json()["data"]["mcp"]["endpoint"] == "https://connector.example.com/mcp"
    assert [call[1] for call in fake_client.calls] == ["/v1/mcp/config", "/v1/identity-provider"]
    assert "secret" not in response.text.lower()
    assert "token" not in response.text.lower()
    assert response.json()["data"]["mcp"]["workbuddy_config"]["auth"] == "oauth"
    assert all(call[2]["tenant_id"] == "tenant-a" for call in fake_client.calls)


def test_docs_rejects_non_https_endpoint(client: TestClient, fake_client: FakeOpenConnector) -> None:
    original_request = fake_client.request

    async def insecure_request(method: str, path: str, **kwargs: Any) -> Any:
        if path == "/v1/mcp/config":
            return {"endpoint": "http://connector.example.com/mcp"}
        return await original_request(method, path, **kwargs)

    fake_client.request = insecure_request
    response = client.get("/api/v1/connection-docs/config")

    assert response.status_code == 502
    assert "HTTPS" in response.json()["detail"]["message"]


def test_provider_catalog_uses_v1_upstream(client: TestClient, fake_client: FakeOpenConnector) -> None:
    response = client.get("/api/v1/providers")

    assert response.status_code == 200
    assert response.json()["data"][0]["name"] == "Oracle"
    assert response.json()["data"][0]["id"] == "oracle"
    assert fake_client.calls[-1][1] == "/v1/providers"


def test_identity_status_exposes_only_operational_metadata(
    client: TestClient,
    fake_client: FakeOpenConnector,
) -> None:
    response = client.get("/api/v1/identity-provider")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "ready",
        "user_pool_ref": "dw-users",
        "jwks_status": None,
        "jwks_last_refresh_at": None,
    }
    assert fake_client.calls[-1][1] == "/v1/identity-provider"


def test_unconfigured_identity_is_explicit_not_an_upstream_error(
    client: TestClient,
    fake_client: FakeOpenConnector,
) -> None:
    original_request = fake_client.request

    async def no_identity(method: str, path: str, **kwargs: Any) -> Any:
        if path == "/v1/identity-provider":
            return None
        return await original_request(method, path, **kwargs)

    fake_client.request = no_identity

    status_response = client.get("/api/v1/identity-provider")
    docs_response = client.get("/api/v1/connection-docs/config")

    assert status_response.status_code == 200
    assert status_response.json()["data"]["status"] == "unconfigured"
    assert docs_response.status_code == 200
    assert docs_response.json()["data"]["identity"]["status"] == "unconfigured"


def test_connections_and_actions_translate_w1_runtime_contract(
    client: TestClient,
    fake_client: FakeOpenConnector,
) -> None:
    connections = client.get("/api/v1/connections")
    actions = client.get("/api/v1/connections/oracle-prod/actions")

    assert connections.json()["data"][0] == {
        "id": "oracle-prod",
        "name": "Oracle Production",
        "provider": "oracle",
        "description": "Oracle Production",
        "status": "ready",
        "action_count": None,
        "updated_at": None,
    }
    assert actions.json()["data"][0]["read_only"] is True
    assert actions.json()["data"][0]["risk"] == "low"
    assert [call[1] for call in fake_client.calls] == [
        "/v1/connections",
        "/v1/apps",
        "/v1/connections",
        "/v1/apps",
        "/v1/actions",
    ]
    assert fake_client.calls[-1][2]["params"] == {"service": "oracle"}


def test_access_grants_translate_w2_runtime_contract(
    client: TestClient,
    fake_client: FakeOpenConnector,
) -> None:
    response = client.get("/api/v1/connections/oracle-prod/access")

    assert response.status_code == 200
    grant = response.json()["data"][0]
    assert grant["connection_id"] == "oracle-prod"
    assert grant["subject_type"] == "group"
    assert grant["subject_id"] == "finance"
    assert grant["subject_display_snapshot"] == "finance"
    assert grant["role_id"] == "reader"
    assert grant["status"] == "active"
    assert [call[1] for call in fake_client.calls] == ["/v1/access-grants", "/v1/identity/subjects"]


def test_grant_write_translates_to_w2_camel_case(client: TestClient, fake_client: FakeOpenConnector) -> None:
    response = client.post(
        "/api/v1/access-grants",
        json={
            "connection_id": "oracle-prod",
            "subject_type": "group",
            "subject_id": "finance",
            "subject_display_snapshot": "Finance",
            "role_id": "reader",
            "effect": "allow",
            "action_scope": [],
        },
    )

    assert response.status_code == 200
    assert fake_client.calls[-1][2]["json"] == {
        "connectionId": "oracle-prod",
        "subjectType": "group",
        "subject": "finance",
        "role": "reader",
        "effect": "allow",
        "customActions": [],
    }
    assert response.json()["data"]["role_id"] == "reader"


def test_access_preview_uses_verified_subject_and_per_action_decisions(
    client: TestClient,
    fake_client: FakeOpenConnector,
) -> None:
    response = client.post(
        "/api/v1/access:preview",
        json={"connection_id": "oracle-prod", "subject_id": "alice"},
    )

    assert response.status_code == 200
    preview = response.json()["data"]
    assert preview["subject"]["id"] == "alice"
    assert [action["id"] for action in preview["connections"][0]["actions"]] == ["oracle.query_rows"]
    preview_call = next(call for call in fake_client.calls if call[1] == "/v1/access:preview")
    assert preview_call[2]["json"]["subject"]["sub"] == "alice"
    assert preview_call[2]["json"]["connectionId"] == "oracle-prod"
    assert preview_call[2]["json"]["actionId"] == "oracle.query_rows"


def test_connection_payload_recursively_removes_secret_fields(
    client: TestClient,
    fake_client: FakeOpenConnector,
) -> None:
    original_request = fake_client.request

    async def response_with_secrets(method: str, path: str, **kwargs: Any) -> Any:
        if path == "/v1/connections":
            return {
                "items": [
                    {
                        "id": "oracle-prod",
                        "displayName": "Oracle",
                        "service": "oracle",
                        "credentials": {"password": "hidden"},
                        "metadata": {"api_key": "hidden", "region": "cn-beijing"},
                    }
                ]
            }
        if path == "/v1/apps":
            return {
                "items": [
                    {
                        "id": "oracle-prod",
                        "displayName": "Oracle",
                        "service": "oracle",
                        "credentials": {"password": "hidden"},
                        "metadata": {"api_key": "hidden", "region": "cn-beijing"},
                    }
                ]
            }
        return await original_request(method, path, **kwargs)

    fake_client.request = response_with_secrets
    response = client.get("/api/v1/connections")

    assert response.status_code == 200
    assert response.json()["data"][0]["name"] == "Oracle"
    assert "hidden" not in response.text


def test_upstream_error_details_are_not_forwarded(client: TestClient, fake_client: FakeOpenConnector) -> None:
    async def rejected(*_: Any, **__: Any) -> Any:
        raise OpenConnectorError(
            "OpenConnector rejected the request",
            status_code=403,
            detail={"authorization": "Bearer sensitive", "message": "token=sensitive"},
        )

    fake_client.request = rejected
    response = client.get("/api/v1/connections")

    assert response.status_code == 403
    assert "sensitive" not in response.text


@pytest.mark.parametrize(
    ("operation", "method", "path"),
    [
        ("health", "GET", "/v1/health"),
        ("identity", "GET", "/v1/identity-provider"),
        ("tools_list", "POST", "/v1/mcp/tests/tools-list"),
        ("list_connections", "POST", "/v1/mcp/tests/read-only"),
    ],
)
def test_read_only_tester_maps_to_fixed_allowlist(
    client: TestClient,
    fake_client: FakeOpenConnector,
    operation: str,
    method: str,
    path: str,
) -> None:
    response = client.post(
        "/api/v1/connection-docs/read-only-tests",
        json={"operation": operation, "arguments": {"ignored_path": "/v1/access-grants"}},
    )

    assert response.status_code == 200
    assert fake_client.calls[-1][0:2] == (method, path)
    if method == "POST":
        assert fake_client.calls[-1][2]["json"]["operation"] == operation
        assert fake_client.calls[-1][2]["json"]["arguments"] == {}


def test_launch_session_cookie_is_short_lived_http_only_secure_and_strict(
    client: TestClient,
    fake_client: FakeOpenConnector,
) -> None:
    response = client.post("/api/v1/openconnector/launch-sessions")

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "dw_oc_launch=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/oc" in cookie
    assert "max-age=300" in cookie.lower()
    assert "token" not in response.text.lower()
    assert response.json()["data"]["launch_url"] == "/oc/?embed=studio"


def test_console_proxy_rejects_missing_launch_session(client: TestClient, fake_client: FakeOpenConnector) -> None:
    response = client.get("/oc/?embed=studio")

    assert response.status_code == 401
    assert fake_client.calls == []


def test_console_proxy_uses_secure_launch_cookie_without_exposing_admin_token(
    fake_client: FakeOpenConnector,
) -> None:
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    app.include_router(api.console_router)
    admin = SimpleNamespace(
        tenant_id="tenant-a",
        user_id="user-admin",
        is_admin=True,
        has_scope=lambda _: True,
    )

    app.dependency_overrides[api.require_workshop_member] = lambda: admin
    app.dependency_overrides[api.require_workshop_admin] = lambda: admin
    secure_client = TestClient(app, base_url="https://testserver")

    launch = secure_client.post("/api/v1/openconnector/launch-sessions")
    response = secure_client.get("/oc/actions?embed=studio")

    assert launch.status_code == 200
    assert response.status_code == 200
    assert response.text == "<html>console</html>"
    assert fake_client.calls[-1][0:2] == ("GET", "actions")
    assert fake_client.calls[-1][2]["query"] == b"embed=studio"
    assert fake_client.calls[-1][2]["tenant_id"] == "tenant-a"
    assert "test-admin-token" not in response.text
    assert "content-encoding" not in response.headers
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_console_proxy_filters_sensitive_query_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class RecordingClient:
        async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            captured.update(method=method, url=url, headers=kwargs["headers"])
            return httpx.Response(200, text="ok")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: Any):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: RecordingClient())
    adapter = OpenConnectorClient(base_url="https://connector.example.com", admin_token="server-secret")

    await adapter.proxy(
        "GET",
        "actions",
        query=b"embed=studio&token=browser-secret&filter=recent",
        body=b"",
        content_type=None,
        tenant_id="tenant-a",
    )

    assert captured["url"] == "https://connector.example.com/actions?embed=studio&filter=recent"
    assert captured["headers"]["X-Forwarded-Prefix"] == "/oc"
    assert captured["headers"]["X-Tenant-ID"] == "tenant-a"
    assert captured["headers"]["Authorization"] == "Bearer server-secret"


def test_read_only_tester_rejects_unknown_operation(client: TestClient) -> None:
    response = client.post(
        "/api/v1/connection-docs/read-only-tests",
        json={"operation": "execute_action", "arguments": {}},
    )

    assert response.status_code == 422


def test_launch_session_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 1_000
    monkeypatch.setattr("server.data_workshop.launch_sessions.time.time", lambda: now)
    store = LaunchSessionStore(ttl_seconds=5)
    session_id, session = store.create("tenant-a", "user-admin")
    assert store.get(session_id) == session

    now = 1_006
    assert store.get(session_id) is None


def test_unconfigured_upstream_returns_recoverable_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class Unconfigured:
        configured = False

        async def request(self, *_: Any, **__: Any) -> Any:
            raise OpenConnectorError("OpenConnector is not configured", status_code=503)

    monkeypatch.setattr(api, "get_openconnector_client", Unconfigured)
    response = client.get("/api/v1/connections")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "OPENCONNECTOR_ERROR"


def test_admin_operations_reject_non_admin(fake_client: FakeOpenConnector, monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    member = SimpleNamespace(
        tenant_id="tenant-a",
        user_id="user-member",
        is_admin=False,
        has_scope=lambda _: True,
    )
    app.dependency_overrides[api.require_workshop_member] = lambda: member
    app.dependency_overrides[api.get_current_auth_context()] = lambda: member
    member_client = TestClient(app)

    launch = member_client.post("/api/v1/openconnector/launch-sessions")
    create = member_client.post(
        "/api/v1/access-grants",
        json={
            "connection_id": "oracle-prod",
            "subject_type": "group",
            "subject_id": "finance",
            "subject_display_snapshot": "Finance",
            "role_id": "reader",
        },
    )
    access = member_client.get("/api/v1/connections/oracle-prod/access")

    assert launch.status_code == 403
    assert create.status_code == 403
    assert access.status_code == 403
    assert fake_client.calls == []
