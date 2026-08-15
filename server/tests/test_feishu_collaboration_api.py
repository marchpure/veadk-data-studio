from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from server.collaboration.feishu.client import FeishuApiClient
from server.collaboration.models import CollaborationInstallation

pytestmark = pytest.mark.asyncio


async def test_feishu_config_empty_state_is_not_an_http_error(test_client):
    resp = await test_client.get("/api/collaboration/installations/feishu")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"] is None
    assert body["message"] == "Feishu not configured"


async def test_feishu_config_api_masks_secret_and_supports_health(test_client, test_session, monkeypatch):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-a", "tenant_name": "Acme"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": "tenant-a",
            "external_tenant_name": "Acme",
        }

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)

    resp = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_a", "app_secret": "secret", "connection_mode": "websocket"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["app_id"] == "cli_a"
    assert "secret" not in str(data).lower()
    assert data["bot_external_id"] == "ou_bot"
    assert data["connection_mode"] == "websocket"

    rows = (await test_session.execute(select(CollaborationInstallation))).scalars().all()
    assert len(rows) == 1
    assert rows[0].credentials_encrypted != "secret"

    health = await test_client.get(f"/api/collaboration/installations/{data['id']}/health")
    assert health.status_code == 200
    assert health.json()["data"]["health_status"] == "configured"


async def test_feishu_config_update_can_reuse_existing_secret(test_client, test_session, monkeypatch):
    probes: list[tuple[str, str]] = []

    async def fake_probe(self):
        probes.append((self.app_id, self.app_secret))
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": f"tenant-{self.app_id}"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{self.app_id}",
            "external_tenant_name": "Acme",
        }

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)

    missing_secret = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_missing", "connection_mode": "websocket"},
    )
    assert missing_secret.status_code == 400

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_a", "app_secret": "secret-a", "connection_mode": "websocket"},
    )
    assert create.status_code == 200

    update = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_a", "connection_mode": "webhook"},
    )
    assert update.status_code == 200
    data = update.json()["data"]
    assert data["connection_mode"] == "webhook"
    assert "secret-a" not in str(data)
    assert probes == [("cli_a", "secret-a"), ("cli_a", "secret-a")]

    rows = (await test_session.execute(select(CollaborationInstallation))).scalars().all()
    assert len(rows) == 1


async def test_feishu_test_message_uses_real_client_contract(test_client, test_session, monkeypatch):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-b"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    sent = {}

    async def fake_send(self, *, receive_id_type, receive_id, text, root_id=None):
        sent.update(
            {
                "receive_id_type": receive_id_type,
                "receive_id": receive_id,
                "text": text,
                "root_id": root_id,
            }
        )
        return {"message_id": "om_sent"}

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "send_text_message", fake_send)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_b", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]

    resp = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/test-message",
        json={"chat_id": "oc_chat", "text": "ping", "root_id": "om_root"},
    )

    assert resp.status_code == 200
    assert sent == {
        "receive_id_type": "chat_id",
        "receive_id": "oc_chat",
        "text": "ping",
        "root_id": "om_root",
    }
