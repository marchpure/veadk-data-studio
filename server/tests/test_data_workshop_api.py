from __future__ import annotations

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
            "/v1/mcp/config": {"endpoint": "https://connector.example.com/mcp"},
            "/v1/identity-provider": {"status": "ready", "issuer": "https://identity.example.com"},
            "/v1/mcp/status": {"status": "healthy"},
            "/v1/mcp/tests/tools-list": {"tools": [{"name": "list_connections"}]},
        }
        return responses.get(path, {"ok": True})

    async def proxy(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        self.calls.append((method, path, kwargs))
        return httpx.Response(200, text="<html>console</html>", headers={"content-type": "text/html"})


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
    return TestClient(app)


def test_adapter_only_accepts_versioned_control_plane_paths() -> None:
    adapter = OpenConnectorClient(base_url="https://connector.example.com", admin_token="secret")
    with pytest.raises(ValueError, match="/v1"):
        adapter._url("/api/connections")


def test_docs_aggregates_only_non_sensitive_v1_metadata(client: TestClient, fake_client: FakeOpenConnector) -> None:
    response = client.get("/api/data-workshop/v1/connection-docs/config")

    assert response.status_code == 200
    assert response.json()["data"]["mcp"]["endpoint"] == "https://connector.example.com/mcp"
    assert [call[1] for call in fake_client.calls] == ["/v1/mcp/config", "/v1/identity-provider"]
    assert "secret" not in response.text.lower()
    assert "token" not in response.text.lower()


def test_provider_catalog_uses_v1_upstream(client: TestClient, fake_client: FakeOpenConnector) -> None:
    response = client.get("/api/data-workshop/v1/providers")

    assert response.status_code == 200
    assert response.json()["data"][0]["name"] == "Oracle"
    assert fake_client.calls[-1][1] == "/v1/providers"


def test_read_only_tester_maps_to_fixed_allowlist(client: TestClient, fake_client: FakeOpenConnector) -> None:
    response = client.post(
        "/api/data-workshop/v1/connection-docs/read-only-tests",
        json={"operation": "tools_list", "arguments": {"ignored_path": "/v1/access-grants"}},
    )

    assert response.status_code == 200
    assert fake_client.calls[-1][0:2] == ("POST", "/v1/mcp/tests/tools-list")
    assert fake_client.calls[-1][2]["json"]["operation"] == "tools_list"


def test_launch_session_cookie_is_short_lived_http_only_secure_and_strict(
    client: TestClient,
    fake_client: FakeOpenConnector,
) -> None:
    response = client.post("/api/data-workshop/v1/openconnector/launch-sessions")

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

    launch = secure_client.post("/api/data-workshop/v1/openconnector/launch-sessions")
    response = secure_client.get("/oc/actions?embed=studio")

    assert launch.status_code == 200
    assert response.status_code == 200
    assert response.text == "<html>console</html>"
    assert fake_client.calls[-1][0:2] == ("GET", "actions")
    assert fake_client.calls[-1][2]["query"] == b"embed=studio"
    assert "test-admin-token" not in response.text


def test_launch_session_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 1_000
    monkeypatch.setattr("server.data_workshop.launch_sessions.time.time", lambda: now)
    store = LaunchSessionStore(ttl_seconds=5)
    session_id, _ = store.create()
    assert store.valid(session_id)

    now = 1_006
    assert not store.valid(session_id)


def test_unconfigured_upstream_returns_recoverable_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class Unconfigured:
        configured = False

        async def request(self, *_: Any, **__: Any) -> Any:
            raise OpenConnectorError("OpenConnector is not configured", status_code=503)

    monkeypatch.setattr(api, "get_openconnector_client", Unconfigured)
    response = client.get("/api/data-workshop/v1/connections")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "OPENCONNECTOR_ERROR"
