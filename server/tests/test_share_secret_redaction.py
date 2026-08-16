from __future__ import annotations

import pytest
from sqlalchemy import select

from server.models.notebooks import Notebook
from server.models.settings import Setting
from server.models.tenant import Tenant

pytestmark = pytest.mark.asyncio


SENSITIVE_KEYS = {"password", "verifier", "token", "raw_token"}
SENSITIVE_VALUES = {
    "plain-dashboard-password",
    "plain-json-password",
    "argon2id-verifier",
    "raw-share-token",
}


def _assert_no_share_secret(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            assert key.lower() not in SENSITIVE_KEYS
            _assert_no_share_secret(child)
        return
    if isinstance(value, list):
        for child in value:
            _assert_no_share_secret(child)
        return
    if isinstance(value, str):
        assert value not in SENSITIVE_VALUES


async def _seed_notebook_and_worker_key(test_session) -> str:
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None

    notebook = Notebook(
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        notebook_name="Governed sharing redaction",
        description="Verifies share manage endpoints do not return credentials.",
    )
    test_session.add(notebook)
    test_session.add(
        Setting(
            tenant_id=tenant.id,
            user_id=None,
            setting_key="api_key",
            setting_value="worker-api-key",
            is_encrypted=False,
        )
    )
    await test_session.commit()
    return str(notebook.id)


class _WorkerResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class _WorkerClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, **kwargs) -> _WorkerResponse:
        if url.endswith("/api/html/notebook-404"):
            return _WorkerResponse(404, {})
        if "/api/html/" in url:
            return _WorkerResponse(
                200,
                {
                    "created_at": "2026-08-16T13:00:00Z",
                    "updated_at": "2026-08-16T13:05:00Z",
                    "has_password": True,
                    "password": "plain-dashboard-password",
                    "verifier": "argon2id-verifier",
                    "token": "raw-share-token",
                },
            )
        if "/api/notebook/list/" in url:
            return _WorkerResponse(
                200,
                {
                    "shares": [
                        {
                            "id": "json-share-1",
                            "created_at": "2026-08-16T13:01:00Z",
                            "has_password": True,
                            "password": "plain-json-password",
                            "verifier": "argon2id-verifier",
                            "raw_token": "raw-share-token",
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected worker GET {url}")

    async def put(self, url: str, **kwargs) -> _WorkerResponse:
        assert kwargs["json"] == {"password": "rotated-password"}
        return _WorkerResponse(
            200,
            {
                "success": True,
                "has_password": True,
                "password": "plain-json-password",
                "verifier": "argon2id-verifier",
                "token": "raw-share-token",
            },
        )


@pytest.fixture
def share_worker_redaction(monkeypatch):
    monkeypatch.setattr("server.routers.exports.is_feature_enabled", lambda feature: feature == "external_sharing_enabled")
    monkeypatch.setattr("server.routers.exports.get_waitlist_config", lambda: {"worker_url": "https://worker.test"})
    monkeypatch.setattr("server.routers.exports.httpx.AsyncClient", _WorkerClient)


async def test_share_manage_endpoints_redact_worker_secrets(test_client, test_session, share_worker_redaction):
    notebook_id = await _seed_notebook_and_worker_key(test_session)

    share_response = await test_client.get(f"/api/notebooks/{notebook_id}/share")
    assert share_response.status_code == 200
    share_payload = share_response.json()
    _assert_no_share_secret(share_payload)
    assert share_payload["data"]["share"] == {
        "id": notebook_id,
        "share_url": f"https://www.byaan.ai/share/{notebook_id}",
        "created_at": "2026-08-16T13:00:00Z",
        "updated_at": "2026-08-16T13:05:00Z",
        "has_password": True,
    }

    list_response = await test_client.get(f"/api/notebooks/{notebook_id}/shares/notebook")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    _assert_no_share_secret(list_payload)
    assert list_payload["data"]["shares"] == [
        {
            "id": "json-share-1",
            "created_at": "2026-08-16T13:01:00Z",
            "has_password": True,
        }
    ]

    update_response = await test_client.put(
        f"/api/notebooks/{notebook_id}/shares/notebook/json-share-1/password?password=rotated-password"
    )
    assert update_response.status_code == 200
    update_payload = update_response.json()
    _assert_no_share_secret(update_payload)
    assert update_payload["data"] == {"success": True, "has_password": True}
