from __future__ import annotations

import logging

import pytest
from sqlalchemy import select

from server.models.notebooks import Notebook
from server.models.settings import Setting
from server.models.sharing import SharingCompatibilityLink, SharingGrant, SharingSecret
from server.models.tenant import Tenant

pytestmark = pytest.mark.asyncio


SENSITIVE_KEYS = {"password", "verifier", "token", "raw_token"}
SENSITIVE_VALUES = {
    "plain-dashboard-password",
    "plain-json-password",
    "argon2id-verifier",
    "raw-share-token",
    "worker-password",
    "worker-verifier",
    "worker-token",
    "worker-credential",
    "select * from other_tenant.secret_orders",
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

    async def post(self, url: str, **kwargs) -> _WorkerResponse:
        if url.endswith("/api/html"):
            assert kwargs["json"]["id"]
            return _WorkerResponse(200, {"is_new": True, "has_password": bool(kwargs["json"].get("password"))})
        if url.endswith("/api/notebook"):
            assert kwargs["json"]["notebook_id"]
            return _WorkerResponse(200, {"id": "json-share-created", "has_password": bool(kwargs["json"].get("password"))})
        raise AssertionError(f"Unexpected worker POST {url}")

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

    async def delete(self, url: str, **kwargs) -> _WorkerResponse:
        if "/api/html/" in url or "/api/notebook/" in url:
            return _WorkerResponse(200, {"success": True})
        raise AssertionError(f"Unexpected worker DELETE {url}")


class _FailingWorkerClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, **kwargs) -> _WorkerResponse:
        return _WorkerResponse(
            500,
            {
                "password": "worker-password",
                "verifier": "worker-verifier",
                "token": "worker-token",
                "credential": "worker-credential",
                "sql": "select * from other_tenant.secret_orders",
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


async def test_worker_backed_notebook_shares_write_canonical_grants_without_plain_secret(
    test_client,
    test_session,
    share_worker_redaction,
    monkeypatch,
):
    notebook_id = await _seed_notebook_and_worker_key(test_session)

    async def fake_generate_compiled_html(**_kwargs):
        return "<html>safe</html>"

    async def fake_export_notebook(*_args, **_kwargs):
        class Export:
            def model_dump(self):
                return {"notebook": {"id": notebook_id}}

        return Export()

    monkeypatch.setattr(
        "server.routers.exports.CompiledHtmlExportService.generate_compiled_html",
        fake_generate_compiled_html,
    )
    monkeypatch.setattr("server.routers.exports.NotebookExportService.export_notebook", fake_export_notebook)

    html_response = await test_client.post(f"/api/notebooks/{notebook_id}/share?password=worker-password")
    json_response = await test_client.post(
        f"/api/notebooks/{notebook_id}/share/notebook",
        json={"password": "plain-json-password"},
    )
    rotate_response = await test_client.put(
        f"/api/notebooks/{notebook_id}/shares/notebook/json-share-created/password?password=rotated-password"
    )

    assert html_response.status_code == 200
    assert json_response.status_code == 200
    assert rotate_response.status_code == 200
    links = (
        await test_session.execute(
            select(SharingCompatibilityLink).where(
                SharingCompatibilityLink.legacy_surface.in_(["html_notebook_share", "json_notebook_share"])
            )
        )
    ).scalars().all()
    assert {link.legacy_surface for link in links} == {"html_notebook_share", "json_notebook_share"}
    grants = (
        await test_session.execute(select(SharingGrant).where(SharingGrant.object_type == "notebook"))
    ).scalars().all()
    assert len(grants) == 2
    assert {grant.channel for grant in grants} == {"worker"}
    assert all(grant.status == "active" for grant in grants)
    secrets = (await test_session.execute(select(SharingSecret))).scalars().all()
    assert len([secret for secret in secrets if secret.status == "active"]) == 2
    serialized = "\n".join(f"{secret.salt}:{secret.verifier_hash}" for secret in secrets)
    assert "worker-password" not in serialized
    assert "plain-json-password" not in serialized
    assert "rotated-password" not in serialized

    delete_html = await test_client.delete(f"/api/notebooks/{notebook_id}/share")
    delete_json = await test_client.delete(f"/api/notebooks/{notebook_id}/shares/notebook/json-share-created")
    assert delete_html.status_code == 200
    assert delete_json.status_code == 200
    revoked_statuses = (
        await test_session.execute(select(SharingGrant.status).where(SharingGrant.object_type == "notebook"))
    ).scalars().all()
    assert set(revoked_statuses) == {"revoked"}


async def test_share_worker_errors_do_not_leak_secrets_to_response_or_logs(
    test_client,
    test_session,
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
):
    notebook_id = await _seed_notebook_and_worker_key(test_session)

    async def fake_generate_compiled_html(**_kwargs):
        return "<html>safe</html>"

    monkeypatch.setattr("server.routers.exports.is_feature_enabled", lambda feature: feature == "external_sharing_enabled")
    monkeypatch.setattr("server.routers.exports.get_waitlist_config", lambda: {"worker_url": "https://worker.test"})
    monkeypatch.setattr("server.routers.exports.httpx.AsyncClient", _FailingWorkerClient)
    monkeypatch.setattr(
        "server.routers.exports.CompiledHtmlExportService.generate_compiled_html",
        fake_generate_compiled_html,
    )

    caplog.set_level(logging.ERROR)
    response = await test_client.post(f"/api/notebooks/{notebook_id}/share?password=worker-password")

    assert response.status_code == 500
    payload = response.json()
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    _assert_no_share_secret(payload)
    _assert_no_share_secret(log_text)
    assert "Failed to create share link" in payload["message"]
    assert "[REDACTED]" in log_text
