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
        responses = {
            "/v1/providers": [{"id": "oracle", "name": "Oracle"}],
            "/v1/connections": [{"id": "oracle-prod", "name": "Oracle Production"}],
            "/v1/mcp/config": {
                "endpoint": "https://connector.example.com/mcp",
                "admin_token": "must-not-leak",
                "client_secret": "must-not-leak",
            },
            "/v1/identity-provider": {"status": "ready", "issuer": "https://identity.example.com"},
            "/v1/mcp/status": {"status": "healthy"},
            "/v1/mcp/tests/tools-list": {"tools": [{"name": "list_connections"}]},
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
    original_tenant = api._tenant
    api._tenant = lambda: "tenant-a"
    try:
        yield TestClient(app)
    finally:
        api._tenant = original_tenant


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
    assert fake_client.calls[-1][1] == "/v1/providers"


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
                        "name": "Oracle",
                        "credentials": {"password": "hidden"},
                        "metadata": {"api_key": "hidden", "region": "cn-beijing"},
                    }
                ]
            }
        return await original_request(method, path, **kwargs)

    fake_client.request = response_with_secrets
    response = client.get("/api/v1/connections")

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["metadata"] == {"region": "cn-beijing"}
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
        ("health", "GET", "/v1/mcp/status"),
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
    secure_client = TestClient(app, base_url="https://testserver")

    launch = secure_client.post("/api/v1/openconnector/launch-sessions")
    response = secure_client.get("/oc/actions?embed=studio")

    assert launch.status_code == 200
    assert response.status_code == 200
    assert response.text == "<html>console</html>"
    assert fake_client.calls[-1][0:2] == ("GET", "actions")
    assert fake_client.calls[-1][2]["query"] == b"embed=studio"
    assert "test-admin-token" not in response.text
    assert "content-encoding" not in response.headers
    assert "set-cookie" not in response.headers


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
    monkeypatch.setattr(api, "_tenant", lambda: "tenant-a")
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
