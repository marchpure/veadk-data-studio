from __future__ import annotations

import hashlib
import json
import time
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.collaboration.feishu.client import FeishuApiClient, FeishuApiError, safe_feishu_error_message
from server.collaboration.feishu.simulator import FeishuWebhookSimulator
from server.collaboration.models import (
    CollaborationConversation,
    CollaborationDeliveryTarget,
    CollaborationEventLog,
    CollaborationInstallation,
    CollaborationResponseRef,
    ExternalIdentity,
)
from server.models.llm_connections import LLMConnection
from server.models.notebooks import Notebook
from server.models.tenant import Tenant
from server.models.tenant_member import TenantMember
from server.models.user import User

pytestmark = pytest.mark.asyncio


def _encrypted_feishu_callback(payload: dict, encrypt_key: str, *, nonce: str = "nonce-1") -> tuple[bytes, dict[str, str]]:
    token = str(payload.get("token") or payload.get("header", {}).get("token") or "verify-token")
    callback = FeishuWebhookSimulator(
        verification_token=token,
        encrypt_key=encrypt_key,
        now=time.time(),
    ).signed_callback(payload, nonce=nonce)
    return callback.raw_body, callback.headers


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
    assert health.json()["data"]["admin_state"] == "admin_authorization_pending"


async def test_feishu_api_exposes_admin_state_for_ui_statuses(test_client, test_session, monkeypatch):
    missing = await test_client.get("/api/collaboration/installations/feishu")
    assert missing.status_code == 404

    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-admin-state", "tenant_name": "Acme"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": "tenant-admin-state",
            "external_tenant_name": "Acme",
        }

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_admin_state", "app_secret": "secret", "connection_mode": "websocket"},
    )
    assert create.status_code == 200
    assert create.json()["data"]["admin_state"] == "admin_authorization_pending"
    installation_id = create.json()["data"]["id"]
    installation = (
        await test_session.execute(select(CollaborationInstallation).where(CollaborationInstallation.id == installation_id))
    ).scalar_one()
    target = CollaborationDeliveryTarget(
        installation_id=installation.id,
        target_type="group",
        external_target_id="oc_needs_rebind",
        normalized_root_id="__root__",
        display_name="Needs rebind",
        is_verified=False,
        config_json={"is_enabled": False, "status": "needs_rebind"},
    )
    test_session.add(target)
    installation.health_status = "needs_reauth"
    installation.is_active = False
    await test_session.commit()

    health = await test_client.get(f"/api/collaboration/installations/{installation_id}/health")
    targets = await test_client.get(f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets")

    assert health.status_code == 200
    assert health.json()["data"]["admin_state"] == "needs_reauth"
    assert targets.status_code == 200
    assert targets.json()["data"]["items"][0]["is_enabled"] is False
    assert targets.json()["data"]["items"][0]["is_verified"] is False
    assert targets.json()["data"]["items"][0]["status"] == "needs_rebind"
    assert targets.json()["data"]["items"][0]["source"] is None


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
        json={"app_id": "cli_a", "connection_mode": "websocket"},
    )
    assert update.status_code == 200
    data = update.json()["data"]
    assert data["connection_mode"] == "websocket"
    assert "secret-a" not in str(data)
    assert probes == [("cli_a", "secret-a"), ("cli_a", "secret-a")]

    rows = (await test_session.execute(select(CollaborationInstallation))).scalars().all()
    assert len(rows) == 1


async def test_feishu_config_accepts_callback_secret_fields_without_returning_them(test_client, test_session, monkeypatch):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-callback"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": "tenant-callback",
            "external_tenant_name": "Acme",
        }

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={
            "app_id": "cli_callback",
            "app_secret": "secret-a",
            "connection_mode": "websocket",
            "verification_token": "verify-token",
            "encrypt_key": "encrypt-key",
        },
    )

    assert create.status_code == 200
    data = create.json()["data"]
    rendered = str(data)
    assert "secret-a" not in rendered
    assert "verify-token" not in rendered
    assert "encrypt-key" not in rendered
    assert data["callback"]["verification_token_configured"] is True
    assert data["callback"]["encrypt_key_configured"] is True

    installation = (await test_session.execute(select(CollaborationInstallation))).scalar_one()
    assert "verify-token" not in installation.credentials_encrypted
    assert "encrypt-key" not in installation.credentials_encrypted


async def test_feishu_config_exposes_websocket_event_subscription_readiness(test_client, monkeypatch):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-subscription"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": "tenant-subscription",
            "external_tenant_name": "Acme",
            "tenant_token_expires_at": "2026-08-14T12:00:00",
        }

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_subscription", "app_secret": "secret", "connection_mode": "websocket"},
    )

    assert create.status_code == 200
    installation = create.json()["data"]
    event_subscription = installation["event_subscription"]
    assert event_subscription["mode"] == "websocket"
    assert event_subscription["required_event_types"] == ["im.message.receive_v1"]
    assert event_subscription["remote_status"] == "manual_developer_console_check_required"
    assert event_subscription["first_event_observed_at"] is None
    assert event_subscription["last_event_observed_at"] is None
    assert event_subscription["ready"] is False
    assert "publish" in event_subscription["operator_action"].lower()

    health = await test_client.get(f"/api/collaboration/installations/{installation['id']}/health")
    assert health.status_code == 200
    assert health.json()["data"]["event_subscription"] == event_subscription


async def test_feishu_config_rejects_default_llm_connection_from_another_tenant(
    test_client,
    test_session,
    monkeypatch,
):
    probe_calls = 0

    async def fake_probe(self):
        nonlocal probe_calls
        probe_calls += 1
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-foreign-llm"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": "tenant-foreign-llm",
            "external_tenant_name": "Acme",
        }

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)

    outsider_user = User(
        id=uuid4(),
        email=f"foreign-llm-owner-{uuid4().hex[:8]}@test.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    test_session.add(outsider_user)
    await test_session.flush()
    outsider_tenant = Tenant(
        id=uuid4(),
        name="Foreign LLM Tenant",
        slug=f"foreign-llm-{uuid4().hex[:8]}",
        owner_id=outsider_user.id,
    )
    test_session.add(outsider_tenant)
    await test_session.flush()
    foreign_llm = LLMConnection(
        tenant_id=outsider_tenant.id,
        created_by=outsider_user.id,
        type="openai",
        name="Foreign tenant LLM",
        config="{}",
    )
    test_session.add(foreign_llm)
    await test_session.commit()

    resp = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={
            "app_id": "cli_foreign_llm",
            "app_secret": "secret",
            "connection_mode": "websocket",
            "default_llm_connection_id": str(foreign_llm.id),
        },
    )

    assert resp.status_code == 400
    assert "current tenant" in resp.json()["message"]
    assert "secret" not in str(resp.json())
    assert probe_calls == 0
    assert (await test_session.execute(select(CollaborationInstallation))).scalars().all() == []


async def test_feishu_webhook_ingress_is_not_exposed_and_mode_is_rejected(test_client, monkeypatch):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-a"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": "tenant-a",
            "external_tenant_name": "Acme",
        }

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_a", "app_secret": "secret-a", "connection_mode": "webhook"},
    )
    assert create.status_code == 400
    assert "Webhook mode is disabled" in create.json()["message"]
    assert "secret-a" not in str(create.json())

    event_ingress = await test_client.post(
        "/api/collaboration/feishu/events/public-id",
        json={"event": {"event_id": "evt_unsafe"}},
    )
    assert event_ingress.status_code == 404


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

    async def fake_list_chats(self):
        return [{"chat_id": "oc_chat", "name": "Feishu E2E Test", "chat_type": "group"}]

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
    monkeypatch.setattr(FeishuApiClient, "list_chats", fake_list_chats)
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
    target = (await test_session.execute(select(CollaborationDeliveryTarget))).scalar_one()
    assert target.target_type == "topic_group"
    assert target.external_target_id == "oc_chat"
    assert target.external_root_id == "om_root"
    assert target.display_name == "Feishu E2E Test"
    assert target.is_verified is True


async def test_feishu_delivery_target_binding_requires_visible_chat_and_can_pause_resume_unbind(
    test_client,
    test_session,
    monkeypatch,
):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-targets"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    async def fake_list_chats(self):
        return [{"chat_id": "oc_allowed", "name": "Allowed Group", "chat_type": "group"}]

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", fake_list_chats)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_targets", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]

    rejected = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_unknown"},
    )
    assert rejected.status_code == 400

    bound = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_allowed"},
    )
    assert bound.status_code == 200
    target = bound.json()["data"]
    assert target["chat_id"] == "oc_allowed"
    assert target["display_name"] == "Allowed Group"
    assert target["is_verified"] is True
    assert target["is_enabled"] is True

    listed = await test_client.get(f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets")
    assert listed.status_code == 200
    assert listed.json()["data"]["items"][0]["id"] == target["id"]

    paused = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets/{target['id']}/pause"
    )
    assert paused.status_code == 200
    assert paused.json()["data"]["is_enabled"] is False

    resumed = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets/{target['id']}/resume"
    )
    assert resumed.status_code == 200
    assert resumed.json()["data"]["is_enabled"] is True

    unbound = await test_client.delete(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets/{target['id']}"
    )
    assert unbound.status_code == 200
    assert unbound.json()["data"]["is_enabled"] is False
    assert unbound.json()["data"]["is_verified"] is False

    db_target = (await test_session.execute(select(CollaborationDeliveryTarget))).scalar_one()
    assert db_target.config_json["source"] == "admin_binding"


async def test_feishu_delivery_target_binding_matches_chat_type_and_root(
    test_client,
    test_session,
    monkeypatch,
):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-target-types"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    async def fake_list_chats(self):
        return [
            {"chat_id": "oc_topic", "name": "Topic Group", "chat_type": "group"},
            {"chat_id": "oc_private", "name": "Private Chat", "chat_type": "p2p"},
        ]

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", fake_list_chats)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_target_types", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]

    topic = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_topic", "root_id": "om_root", "target_type": "topic_group"},
    )
    private = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_private", "target_type": "p2p"},
    )
    mismatched_topic = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_topic", "root_id": "om_other", "target_type": "group"},
    )
    private_with_root = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_private", "root_id": "om_not_valid", "target_type": "p2p"},
    )
    invalid_type = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_topic", "target_type": "workspace"},
    )

    assert topic.status_code == 200
    assert topic.json()["data"]["target_type"] == "topic_group"
    assert topic.json()["data"]["root_id"] == "om_root"
    assert private.status_code == 200
    assert private.json()["data"]["target_type"] == "p2p"
    assert private.json()["data"]["root_id"] is None
    assert mismatched_topic.status_code == 400
    assert "target_type" in mismatched_topic.json()["message"]
    assert private_with_root.status_code == 400
    assert "root_id" in private_with_root.json()["message"]
    assert invalid_type.status_code == 400
    assert "target_type" in invalid_type.json()["message"]

    targets = (await test_session.execute(select(CollaborationDeliveryTarget))).scalars().all()
    assert {(target.target_type, target.external_target_id, target.external_root_id) for target in targets} == {
        ("topic_group", "oc_topic", "om_root"),
        ("p2p", "oc_private", None),
    }


async def test_feishu_delivery_target_resume_requires_chat_still_visible(
    test_client,
    test_session,
    monkeypatch,
):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-target-resume"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    visible_chats = [{"chat_id": "oc_visible_then_removed", "name": "Visible Then Removed", "chat_type": "group"}]

    async def fake_list_chats(self):
        return visible_chats

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", fake_list_chats)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_target_resume", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]

    bound = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_visible_then_removed"},
    )
    target_id = bound.json()["data"]["id"]

    paused = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets/{target_id}/pause"
    )
    assert paused.status_code == 200

    visible_chats.clear()
    resumed = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets/{target_id}/resume"
    )

    assert resumed.status_code == 400
    assert "not visible to the Feishu bot" in resumed.json()["message"]
    target = (await test_session.execute(select(CollaborationDeliveryTarget))).scalar_one()
    assert target.is_verified is False
    assert target.config_json["is_enabled"] is False
    assert target.config_json["status"] == "needs_rebind"


async def test_feishu_disconnect_revokes_local_delivery_targets_but_preserves_audit_history(
    test_client,
    test_session,
    monkeypatch,
):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-disconnect"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    async def fake_list_chats(self):
        return [{"chat_id": "oc_disconnect", "name": "Disconnect Group", "chat_type": "group"}]

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", fake_list_chats)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_disconnect", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]
    bound = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_disconnect"},
    )
    target_id = bound.json()["data"]["id"]
    test_session.add(
        CollaborationEventLog(
            installation_id=installation_id,
            platform="feishu",
            external_event_id="evt_disconnect_preserved",
            event_type="message",
            external_chat_id="oc_disconnect",
            external_user_id="ou_user",
            processing_status="completed",
            attempt_count=1,
        )
    )
    await test_session.commit()

    disconnected = await test_client.delete(f"/api/collaboration/installations/{installation_id}")

    assert disconnected.status_code == 200
    installation = (
        await test_session.execute(select(CollaborationInstallation).where(CollaborationInstallation.id == installation_id))
    ).scalar_one()
    assert installation.is_active is False
    assert installation.health_status == "disconnected"
    assert installation.config_json["disconnect_policy"]["delivery_targets"] == "revoked"
    assert installation.config_json["disconnect_policy"]["history"] == "preserved"

    target = (
        await test_session.execute(select(CollaborationDeliveryTarget).where(CollaborationDeliveryTarget.id == target_id))
    ).scalar_one()
    assert target.is_verified is False
    assert target.config_json["is_enabled"] is False
    assert target.config_json["status"] == "revoked_on_disconnect"
    assert target.config_json["disconnected_at"]

    events = (await test_session.execute(select(CollaborationEventLog))).scalars().all()
    assert len(events) == 1
    assert events[0].external_event_id == "evt_disconnect_preserved"


async def test_feishu_test_message_rejects_unknown_chat_without_sending(test_client, monkeypatch):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-b"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    async def fake_list_chats(self):
        return [{"chat_id": "oc_known", "name": "Known test group", "chat_type": "group"}]

    async def fake_send(self, *, receive_id_type, receive_id, text, root_id=None):
        raise AssertionError("unknown chat_id must not be sent to Feishu")

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", fake_list_chats)
    monkeypatch.setattr(FeishuApiClient, "send_text_message", fake_send)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_b", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]

    resp = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/test-message",
        json={"chat_id": "oc_unknown", "text": "ping"},
    )

    assert resp.status_code == 400
    assert "not visible to the Feishu bot" in resp.json()["message"]


async def test_feishu_chat_list_uses_openapi_without_requiring_manual_chat_id(test_client, monkeypatch):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-b"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    async def fake_list_chats(self):
        return [
            {"chat_id": "oc_chat_a", "name": "Feishu E2E Test", "chat_type": "group"},
            {"chat_id": "oc_chat_b", "name": "Ops", "chat_type": "group"},
        ]

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", fake_list_chats)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_b", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]

    resp = await test_client.get(f"/api/collaboration/installations/{installation_id}/feishu/chats")

    assert resp.status_code == 200
    assert resp.json()["data"]["items"] == [
        {"chat_id": "oc_chat_a", "name": "Feishu E2E Test", "chat_type": "group"},
        {"chat_id": "oc_chat_b", "name": "Ops", "chat_type": "group"},
    ]


async def test_feishu_chat_list_marks_installation_needs_reauth_on_invalid_token(
    test_client,
    test_session,
    monkeypatch,
):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-b"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    async def failing_list_chats(self):
        raise FeishuApiError("invalid tenant_access_token app_secret=secret", code=99991663)

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", failing_list_chats)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_reauth", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]
    installation = (
        await test_session.execute(select(CollaborationInstallation).where(CollaborationInstallation.id == installation_id))
    ).scalar_one()
    installation.is_active = True
    installation.health_status = "connected"
    await test_session.commit()

    resp = await test_client.get(f"/api/collaboration/installations/{installation_id}/feishu/chats")

    assert resp.status_code == 400
    await test_session.refresh(installation)
    assert installation.health_status == "needs_reauth"
    assert installation.is_active is False
    assert "secret" not in installation.health_error


async def test_feishu_connect_revalidates_credentials_before_starting_websocket(
    test_client,
    test_session,
    monkeypatch,
):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-connect"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_connect_reauth", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]

    async def failing_probe(self):
        raise FeishuApiError("invalid tenant_access_token app_secret=secret Authorization: Bearer tok.abc", code=99991663)

    websocket_started = False

    async def unexpected_connect(_installation_id):
        nonlocal websocket_started
        websocket_started = True
        raise AssertionError("WebSocket consumer must not start when Feishu credentials fail preflight")

    monkeypatch.setattr(FeishuApiClient, "probe", failing_probe)
    monkeypatch.setattr("server.collaboration.installation_service.feishu_ws_manager.connect", unexpected_connect)

    resp = await test_client.post(f"/api/collaboration/installations/{installation_id}/connect")

    assert resp.status_code == 400
    rendered = str(resp.json())
    assert "secret" not in rendered
    assert "tok.abc" not in rendered
    assert websocket_started is False

    installation = (
        await test_session.execute(select(CollaborationInstallation).where(CollaborationInstallation.id == installation_id))
    ).scalar_one()
    assert installation.is_active is False
    assert installation.health_status == "needs_reauth"
    assert "secret" not in installation.health_error
    assert (await test_session.execute(select(CollaborationEventLog))).scalars().all() == []


async def test_feishu_outbound_message_requires_confirmation_and_is_idempotent(
    test_client,
    test_session,
    monkeypatch,
):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-outbound"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    sent: list[dict] = []

    async def fake_list_chats(self):
        return [{"chat_id": "oc_outbound", "name": "Outbound Group", "chat_type": "group"}]

    async def fake_send(self, *, receive_id_type, receive_id, text, root_id=None, request_uuid=None):
        sent.append(
            {
                "receive_id_type": receive_id_type,
                "receive_id": receive_id,
                "text": text,
                "root_id": root_id,
                "request_uuid": request_uuid,
            }
        )
        return {"message_id": f"om_outbound_{len(sent)}"}

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", fake_list_chats)
    monkeypatch.setattr(FeishuApiClient, "send_text_message", fake_send)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_outbound", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]
    bound = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_outbound"},
    )
    target_id = bound.json()["data"]["id"]

    missing_confirmation = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/outbound-message",
        json={"delivery_target_id": target_id, "text": "send this", "idempotency_key": "idem-key-1"},
    )
    assert missing_confirmation.status_code == 400

    first = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/outbound-message",
        json={
            "delivery_target_id": target_id,
            "text": "send this",
            "idempotency_key": "idem-key-1",
            "confirm": True,
        },
    )
    second = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/outbound-message",
        json={
            "delivery_target_id": target_id,
            "text": "send this again",
            "idempotency_key": "idem-key-1",
            "confirm": True,
        },
    )

    assert first.status_code == 200
    assert first.json()["data"]["idempotent"] is False
    assert second.status_code == 200
    assert second.json()["data"]["idempotent"] is True
    assert sent == [
        {
            "receive_id_type": "chat_id",
            "receive_id": "oc_outbound",
            "text": "send this",
            "root_id": None,
            "request_uuid": "feishu-outbound-" + first.json()["data"]["run_id"].rsplit(":", 1)[-1],
        }
    ]
    events = (await test_session.execute(select(CollaborationEventLog))).scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "delivery"
    assert events[0].processing_status == "completed"


async def test_feishu_outbound_message_failure_is_marked_terminal_without_response_ref(
    test_client,
    test_session,
    monkeypatch,
):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-outbound-fail"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    async def fake_list_chats(self):
        return [{"chat_id": "oc_outbound_fail", "name": "Outbound Fail Group", "chat_type": "group"}]

    async def fake_send(self, *, receive_id_type, receive_id, text, root_id=None):
        raise FeishuApiError("send failed app_secret=secret tenant_access_token=t1 Authorization: Bearer tok.abc")

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", fake_list_chats)
    monkeypatch.setattr(FeishuApiClient, "send_text_message", fake_send)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_outbound_fail", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]
    bound = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_outbound_fail"},
    )
    target_id = bound.json()["data"]["id"]

    failed = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/outbound-message",
        json={
            "delivery_target_id": target_id,
            "text": "send this",
            "idempotency_key": "idem-key-failure",
            "confirm": True,
        },
    )

    assert failed.status_code == 400
    rendered = str(failed.json())
    assert "secret" not in rendered
    assert "t1" not in rendered
    assert "tok.abc" not in rendered
    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    assert event.processing_status == "failed_terminal"
    assert "secret" not in event.error_message
    assert (await test_session.execute(select(CollaborationConversation))).scalars().all() == []


async def test_feishu_outbound_message_can_retry_same_idempotency_key_after_terminal_failure(
    test_client,
    test_session,
    monkeypatch,
):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-outbound-retry"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    async def fake_list_chats(self):
        return [{"chat_id": "oc_outbound_retry", "name": "Outbound Retry Group", "chat_type": "group"}]

    attempts: list[dict] = []

    async def flaky_send(self, *, receive_id_type, receive_id, text, root_id=None, request_uuid=None):
        attempts.append(
            {
                "receive_id_type": receive_id_type,
                "receive_id": receive_id,
                "text": text,
                "root_id": root_id,
                "request_uuid": request_uuid,
            }
        )
        if len(attempts) == 1:
            raise FeishuApiError("temporary send failure")
        return {"message_id": "om_outbound_retry"}

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", fake_list_chats)
    monkeypatch.setattr(FeishuApiClient, "send_text_message", flaky_send)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_outbound_retry", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]
    bound = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_outbound_retry"},
    )
    target_id = bound.json()["data"]["id"]
    payload = {
        "delivery_target_id": target_id,
        "text": "retry this",
        "idempotency_key": "idem-key-retry",
        "confirm": True,
    }

    first = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/outbound-message",
        json=payload,
    )
    retry = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/outbound-message",
        json=payload,
    )
    duplicate_after_success = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/outbound-message",
        json={**payload, "text": "must not send a third time"},
    )

    assert first.status_code == 400
    assert retry.status_code == 200
    assert retry.json()["data"] == {
        "idempotent": False,
        "message_id": "om_outbound_retry",
        "run_id": retry.json()["data"]["run_id"],
    }
    assert duplicate_after_success.status_code == 200
    assert duplicate_after_success.json()["data"]["idempotent"] is True
    assert attempts == [
        {
            "receive_id_type": "chat_id",
            "receive_id": "oc_outbound_retry",
            "text": "retry this",
            "root_id": None,
            "request_uuid": "feishu-outbound-" + retry.json()["data"]["run_id"].rsplit(":", 1)[-1],
        },
        {
            "receive_id_type": "chat_id",
            "receive_id": "oc_outbound_retry",
            "text": "retry this",
            "root_id": None,
            "request_uuid": "feishu-outbound-" + retry.json()["data"]["run_id"].rsplit(":", 1)[-1],
        },
    ]
    events = (await test_session.execute(select(CollaborationEventLog))).scalars().all()
    assert len(events) == 1
    assert events[0].processing_status == "completed"
    assert events[0].attempt_count == 2
    refs = (await test_session.execute(select(CollaborationResponseRef))).scalars().all()
    assert len(refs) == 1
    assert refs[0].platform_message_id == "om_outbound_retry"


async def test_feishu_outbound_message_blocks_obvious_sensitive_content_before_sending(
    test_client,
    test_session,
    monkeypatch,
):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-outbound-sensitive"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    sent: list[dict] = []

    async def fake_list_chats(self):
        return [{"chat_id": "oc_sensitive", "name": "Sensitive Guard Group", "chat_type": "group"}]

    async def fake_send(self, *, receive_id_type, receive_id, text, root_id=None):
        sent.append({"receive_id_type": receive_id_type, "receive_id": receive_id, "text": text, "root_id": root_id})
        return {"message_id": "om_should_not_send"}

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", fake_list_chats)
    monkeypatch.setattr(FeishuApiClient, "send_text_message", fake_send)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_outbound_sensitive", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]
    bound = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_sensitive"},
    )
    target_id = bound.json()["data"]["id"]

    blocked = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/outbound-message",
        json={
            "delivery_target_id": target_id,
            "text": "请发到群里：Authorization: Bearer token-value",
            "idempotency_key": "idem-key-sensitive",
            "confirm": True,
        },
    )

    assert blocked.status_code == 400
    assert "sensitive" in blocked.json()["message"].lower()
    assert "token-value" not in str(blocked.json())
    assert sent == []
    assert (await test_session.execute(select(CollaborationEventLog))).scalars().all() == []
    assert (await test_session.execute(select(CollaborationResponseRef))).scalars().all() == []


async def test_feishu_outbound_message_invalidates_target_when_bot_loses_chat_access(
    test_client,
    test_session,
    monkeypatch,
):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-target-invalidated"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    async def fake_list_chats(self):
        return [{"chat_id": "oc_removed", "name": "Removed Bot Group", "chat_type": "group"}]

    async def fake_send(self, *, receive_id_type, receive_id, text, root_id=None, request_uuid=None):
        raise FeishuApiError("chat not found or bot is not in the chat")

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", fake_list_chats)
    monkeypatch.setattr(FeishuApiClient, "send_text_message", fake_send)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_target_invalidated", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]
    bound = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_removed"},
    )
    target_id = bound.json()["data"]["id"]

    failed = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/outbound-message",
        json={
            "delivery_target_id": target_id,
            "text": "safe outbound message",
            "idempotency_key": "idem-key-removed",
            "confirm": True,
        },
    )

    assert failed.status_code == 400
    target = (await test_session.execute(select(CollaborationDeliveryTarget))).scalar_one()
    assert target.is_verified is False
    assert target.config_json["is_enabled"] is False
    assert target.config_json["status"] == "needs_rebind"
    assert "chat not found" in target.config_json["last_error"]
    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    assert event.processing_status == "failed_terminal"


async def test_feishu_outbound_message_revalidates_target_visibility_before_sending(
    test_client,
    test_session,
    monkeypatch,
):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-outbound-revalidate"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    visible_chats = [{"chat_id": "oc_removed_before_send", "name": "Removed Later", "chat_type": "group"}]
    sent: list[dict] = []

    async def fake_list_chats(self):
        return visible_chats

    async def fake_send(self, *, receive_id_type, receive_id, text, root_id=None, request_uuid=None):
        sent.append(
            {
                "receive_id_type": receive_id_type,
                "receive_id": receive_id,
                "text": text,
                "root_id": root_id,
                "request_uuid": request_uuid,
            }
        )
        return {"message_id": "om_should_not_send"}

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", fake_list_chats)
    monkeypatch.setattr(FeishuApiClient, "send_text_message", fake_send)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_outbound_revalidate", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]
    bound = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_removed_before_send"},
    )
    target_id = bound.json()["data"]["id"]
    visible_chats.clear()

    failed = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/outbound-message",
        json={
            "delivery_target_id": target_id,
            "text": "safe outbound message",
            "idempotency_key": "idem-key-pre-send-revalidation",
            "confirm": True,
        },
    )

    assert failed.status_code == 400
    assert "not visible" in failed.json()["message"]
    assert sent == []
    target = (await test_session.execute(select(CollaborationDeliveryTarget))).scalar_one()
    assert target.is_verified is False
    assert target.config_json["is_enabled"] is False
    assert target.config_json["status"] == "needs_rebind"
    events = (await test_session.execute(select(CollaborationEventLog))).scalars().all()
    assert events == []


async def test_feishu_errors_are_sanitized_and_limited(test_client, monkeypatch):
    async def failing_probe(self):
        raise FeishuApiError(
            "upstream failed app_secret=very-secret tenant_access_token=token-value "
            "Authorization: Bearer abc.def " + ("x" * 1000)
        )

    monkeypatch.setattr(FeishuApiClient, "probe", failing_probe)

    resp = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_b", "app_secret": "very-secret", "connection_mode": "websocket"},
    )

    assert resp.status_code == 400
    detail = resp.json()["message"]
    assert "very-secret" not in detail
    assert "token-value" not in detail
    assert "abc.def" not in detail
    assert len(detail) < 600


async def test_feishu_installation_and_health_api_sanitize_persisted_health_error(
    test_client, test_session, monkeypatch
):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-b"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_b", "app_secret": "very-secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]

    installation = (
        await test_session.execute(select(CollaborationInstallation).where(CollaborationInstallation.id == installation_id))
    ).scalar_one()
    installation.health_status = "failed"
    installation.health_error = (
        "connect failed app_secret=very-secret tenant_access_token=t1 Authorization: Bearer tok.abc "
        + ("x" * 1000)
    )
    await test_session.commit()

    installation_resp = await test_client.get("/api/collaboration/installations/feishu")
    health_resp = await test_client.get(f"/api/collaboration/installations/{installation_id}/health")

    assert installation_resp.status_code == 200
    assert health_resp.status_code == 200
    rendered = str([installation_resp.json()["data"], health_resp.json()["data"]])
    assert "very-secret" not in rendered
    assert "t1" not in rendered
    assert "tok.abc" not in rendered
    assert len(installation_resp.json()["data"]["health_error"]) <= 500
    assert len(health_resp.json()["data"]["health_error"]) <= 500


def test_feishu_safe_error_message_redacts_known_secret_values():
    message = safe_feishu_error_message(
        "request failed app_secret=s1 tenant_access_token=t1 Authorization: Bearer tok.abc payload=s2",
        secrets=["s2"],
    )

    assert "s1" not in message
    assert "t1" not in message
    assert "tok.abc" not in message
    assert "s2" not in message


def test_feishu_safe_error_message_redacts_json_and_camel_case_credentials():
    message = safe_feishu_error_message(
        '{"app_secret":"s1","appSecret":"s2","tenant_access_token":"t1","tenantAccessToken":"t2",'
        '"authorization":"Bearer tok.abc"}'
    )

    assert "s1" not in message
    assert "s2" not in message
    assert "t1" not in message
    assert "t2" not in message
    assert "tok.abc" not in message
    assert "app_secret" not in message
    assert "appSecret" not in message


async def test_feishu_recent_events_api_is_tenant_scoped_and_sanitized(test_client, test_session, monkeypatch):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-b"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_b", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]

    test_session.add_all(
        [
            CollaborationEventLog(
                installation_id=installation_id,
                platform="feishu",
                external_event_id="evt_completed",
                event_type="message",
                external_chat_id="oc_chat",
                external_user_id="ou_user",
                processing_status="completed",
                attempt_count=1,
            ),
            CollaborationEventLog(
                installation_id=installation_id,
                platform="feishu",
                external_event_id="evt_failed",
                event_type="message",
                external_chat_id="oc_chat",
                external_user_id="ou_user",
                processing_status="failed_terminal",
                attempt_count=1,
                error_message="upstream app_secret=secret tenant_access_token=t1 Authorization: Bearer tok.abc",
            ),
        ]
    )
    await test_session.commit()

    resp = await test_client.get(f"/api/collaboration/installations/{installation_id}/events?limit=5")

    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert {item["event_id"] for item in items} == {"evt_completed", "evt_failed"}
    rendered = str(items)
    assert "secret" not in rendered
    assert "t1" not in rendered
    assert "tok.abc" not in rendered
    assert all("content" not in item for item in items)


async def test_feishu_recent_events_api_returns_agent_trace_refs(test_client, test_session, monkeypatch):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-b"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_b", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]
    installation = (
        await test_session.execute(select(CollaborationInstallation).where(CollaborationInstallation.id == installation_id))
    ).scalar_one()
    conversation = CollaborationConversation(
        installation_id=installation_id,
        external_chat_id="oc_chat",
        external_root_id="om_root",
        normalized_root_id="om_root",
        external_user_id="ou_user",
        chat_type="topic_group",
        bot_owned=True,
    )
    test_session.add(conversation)
    notebook = Notebook(tenant_id=installation.tenant_id, notebook_name="Feishu trace notebook")
    test_session.add(notebook)
    await test_session.flush()
    test_session.add(
        CollaborationEventLog(
            installation_id=installation_id,
            platform="feishu",
            external_event_id="evt_completed_with_refs",
            event_type="message",
            external_chat_id="oc_chat",
            external_user_id="ou_user",
            processing_status="completed",
            attempt_count=1,
            conversation_id=conversation.id,
            notebook_id=notebook.id,
            run_id="run-trace-1",
        )
    )
    test_session.add(
        CollaborationResponseRef(
            run_id="run-trace-1",
            conversation_id=conversation.id,
            platform_message_id="om_trace_reply",
            sequence=1,
            status="completed",
        )
    )
    await test_session.commit()

    resp = await test_client.get(f"/api/collaboration/installations/{installation_id}/events?limit=5")

    assert resp.status_code == 200
    item = resp.json()["data"]["items"][0]
    assert item["event_id"] == "evt_completed_with_refs"
    assert item["conversation_id"] == str(conversation.id)
    assert item["notebook_id"] == str(notebook.id)
    assert item["run_id"] == "run-trace-1"
    assert item["response_ref"] == {
        "message_id": "om_trace_reply",
        "status": "completed",
        "sequence": 1,
    }
    assert "raw_response" not in str(item)
    assert "content" not in str(item)


async def test_feishu_signed_encrypted_callback_url_verification(test_client, test_session, monkeypatch):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-callback"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={
            "app_id": "cli_callback",
            "app_secret": "secret",
            "connection_mode": "websocket",
            "verification_token": "verify-token",
            "encrypt_key": "encrypt-key",
        },
    )
    installation = (await test_session.execute(select(CollaborationInstallation))).scalar_one()
    body, headers = _encrypted_feishu_callback(
        {"type": "url_verification", "token": "verify-token", "challenge": "challenge-ok"},
        "encrypt-key",
    )

    resp = await test_client.post(
        f"/api/collaboration/feishu/callback/{installation.public_id}",
        content=body,
        headers=headers,
    )

    assert create.status_code == 200
    assert resp.status_code == 200
    assert resp.json() == {"challenge": "challenge-ok"}

    health = await test_client.get(f"/api/collaboration/installations/{installation.id}/health")
    assert health.status_code == 200
    callback = health.json()["data"]["callback"]
    assert callback["url_verification"] == "verified"
    assert callback["last_url_verification_at"]
    assert callback["verification_token_configured"] is True
    assert callback["encrypt_key_configured"] is True


async def test_feishu_signed_callback_replay_is_rejected(test_client, test_session, monkeypatch):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-callback"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    await test_client.post(
        "/api/collaboration/installations/feishu",
        json={
            "app_id": "cli_callback_replay",
            "app_secret": "secret",
            "connection_mode": "websocket",
            "verification_token": "verify-token-replay",
            "encrypt_key": "encrypt-key-replay",
        },
    )
    installation = (await test_session.execute(select(CollaborationInstallation))).scalar_one()
    body, headers = _encrypted_feishu_callback(
        {"type": "url_verification", "token": "verify-token-replay", "challenge": "challenge-ok"},
        "encrypt-key-replay",
    )

    first = await test_client.post(
        f"/api/collaboration/feishu/callback/{installation.public_id}",
        content=body,
        headers=headers,
    )
    replay = await test_client.post(
        f"/api/collaboration/feishu/callback/{installation.public_id}",
        content=body,
        headers=headers,
    )

    assert first.status_code == 200
    assert replay.status_code == 401


async def test_feishu_signed_callback_message_acknowledges_and_dispatches_event(
    test_client,
    test_session,
    test_engine,
    monkeypatch,
):
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-callback"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    dispatched: list[tuple[str, str]] = []

    async def fake_process(session, installation, payload, *, preaccepted_event_log_id=None):
        dispatched.append((str(installation.id), payload["header"]["event_id"], str(preaccepted_event_log_id)))
        return {"status": "completed"}

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr("server.routers.collaboration.process_feishu_event", fake_process)
    monkeypatch.setattr("server.routers.collaboration.AsyncSessionFactory", test_session_factory)
    await test_client.post(
        "/api/collaboration/installations/feishu",
        json={
            "app_id": "cli_callback_message",
            "app_secret": "secret",
            "connection_mode": "websocket",
            "verification_token": "verify-token-message",
            "encrypt_key": "encrypt-key-message",
        },
    )
    installation = (await test_session.execute(select(CollaborationInstallation))).scalar_one()
    installation.is_active = True
    await test_session.commit()
    body, headers = _encrypted_feishu_callback(
        {
            "header": {"event_id": "evt_callback_message", "event_type": "im.message.receive_v1"},
            "token": "verify-token-message",
            "event": {
                "sender": {"sender_id": {"open_id": "ou_callback_message"}},
                "message": {
                    "message_id": "om_callback",
                    "chat_id": "oc_callback_message",
                    "chat_type": "group",
                    "content": "{\"text\":\"hello\"}",
                },
            },
        },
        "encrypt-key-message",
    )

    resp = await test_client.post(
        f"/api/collaboration/feishu/callback/{installation.public_id}",
        content=body,
        headers=headers,
    )

    assert resp.status_code == 200
    assert resp.json() == {"code": 0}
    assert len(dispatched) == 1
    assert dispatched[0][0] == str(installation.id)
    assert dispatched[0][1] == "evt_callback_message"
    assert dispatched[0][2] != "None"


async def test_feishu_signed_callback_persists_event_id_before_async_dispatch_and_dedupes_retry(
    test_client,
    test_session,
    test_engine,
    monkeypatch,
):
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-callback"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    dispatched: list[tuple[str, str, str | None]] = []

    async def fake_process(session, installation, payload, *, preaccepted_event_log_id=None):
        dispatched.append((str(installation.id), payload["header"]["event_id"], str(preaccepted_event_log_id)))
        return {"status": "completed"}

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr("server.routers.collaboration.process_feishu_event", fake_process)
    monkeypatch.setattr("server.routers.collaboration.AsyncSessionFactory", test_session_factory)
    await test_client.post(
        "/api/collaboration/installations/feishu",
        json={
            "app_id": "cli_callback_retry",
            "app_secret": "secret",
            "connection_mode": "websocket",
            "verification_token": "verify-token-retry",
            "encrypt_key": "encrypt-key-retry",
        },
    )
    installation = (await test_session.execute(select(CollaborationInstallation))).scalar_one()
    installation.is_active = True
    await test_session.commit()
    payload = {
        "header": {"event_id": "evt_callback_retry", "event_type": "im.message.receive_v1"},
        "token": "verify-token-retry",
        "event": {
            "sender": {"sender_id": {"open_id": "ou_callback_retry"}},
            "message": {
                "message_id": "om_callback_retry",
                "chat_id": "oc_callback_retry",
                "chat_type": "group",
                "content": "{\"text\":\"hello\"}",
            },
        },
    }
    first_body, first_headers = _encrypted_feishu_callback(payload, "encrypt-key-retry", nonce="nonce-retry-1")
    retry_body, retry_headers = _encrypted_feishu_callback(payload, "encrypt-key-retry", nonce="nonce-retry-2")

    first = await test_client.post(
        f"/api/collaboration/feishu/callback/{installation.public_id}",
        content=first_body,
        headers=first_headers,
    )
    retry = await test_client.post(
        f"/api/collaboration/feishu/callback/{installation.public_id}",
        content=retry_body,
        headers=retry_headers,
    )

    assert first.status_code == 200
    assert retry.status_code == 200
    assert first.json() == {"code": 0}
    assert retry.json() == {"code": 0}
    assert len(dispatched) == 1
    assert dispatched[0][1] == "evt_callback_retry"
    assert dispatched[0][2] != "None"
    events = (await test_session.execute(select(CollaborationEventLog))).scalars().all()
    assert len(events) == 1
    assert events[0].external_event_id == "evt_callback_retry"
    assert events[0].external_chat_id == "oc_callback_retry"
    assert events[0].external_user_id == "ou_callback_retry"


async def test_feishu_signed_callback_unknown_event_type_is_audited_without_dispatch(
    test_client,
    test_session,
    test_engine,
    monkeypatch,
):
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-callback"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    dispatched = False

    async def fake_process(session, installation, payload, *, preaccepted_event_log_id=None):
        nonlocal dispatched
        dispatched = True
        return {"status": "completed"}

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr("server.routers.collaboration.process_feishu_event", fake_process)
    monkeypatch.setattr("server.routers.collaboration.AsyncSessionFactory", test_session_factory)
    await test_client.post(
        "/api/collaboration/installations/feishu",
        json={
            "app_id": "cli_callback_unknown",
            "app_secret": "secret",
            "connection_mode": "websocket",
            "verification_token": "verify-token-unknown",
            "encrypt_key": "encrypt-key-unknown",
        },
    )
    installation = (await test_session.execute(select(CollaborationInstallation))).scalar_one()
    installation.is_active = True
    await test_session.commit()
    payload = {
        "header": {"event_id": "evt_callback_unknown", "event_type": "im.chat.member.user.added_v1"},
        "token": "verify-token-unknown",
        "event": {
            "chat_id": "oc_callback_unknown",
            "operator_id": {"open_id": "ou_callback_operator"},
        },
    }
    body, headers = _encrypted_feishu_callback(payload, "encrypt-key-unknown")

    resp = await test_client.post(
        f"/api/collaboration/feishu/callback/{installation.public_id}",
        content=body,
        headers=headers,
    )

    assert resp.status_code == 200
    assert resp.json() == {"code": 0}
    assert dispatched is False
    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    assert event.external_event_id == "evt_callback_unknown"
    assert event.event_type == "im.chat.member.user.added_v1"
    assert event.external_chat_id == "oc_callback_unknown"
    assert event.external_user_id == "ou_callback_operator"
    assert event.processing_status == "ignored_event_type"
    assert event.error_message == "Feishu callback event type im.chat.member.user.added_v1 is not handled."


async def test_feishu_signed_callback_malformed_message_acknowledges_and_marks_event_failed(
    test_client,
    test_session,
    test_engine,
    monkeypatch,
):
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-callback"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    dispatched = False

    async def fake_process(session, installation, payload, *, preaccepted_event_log_id=None):
        nonlocal dispatched
        dispatched = True
        return {"status": "completed"}

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr("server.routers.collaboration.process_feishu_event", fake_process)
    monkeypatch.setattr("server.routers.collaboration.AsyncSessionFactory", test_session_factory)
    await test_client.post(
        "/api/collaboration/installations/feishu",
        json={
            "app_id": "cli_callback_malformed",
            "app_secret": "secret",
            "connection_mode": "websocket",
            "verification_token": "verify-token-malformed",
            "encrypt_key": "encrypt-key-malformed",
        },
    )
    installation = (await test_session.execute(select(CollaborationInstallation))).scalar_one()
    installation.is_active = True
    await test_session.commit()
    body, headers = _encrypted_feishu_callback(
        {
            "header": {"event_id": "evt_callback_malformed", "event_type": "im.message.receive_v1"},
            "token": "verify-token-malformed",
            "event": {"message": {"content": "{\"text\":\"hello\"}"}},
        },
        "encrypt-key-malformed",
    )

    resp = await test_client.post(
        f"/api/collaboration/feishu/callback/{installation.public_id}",
        content=body,
        headers=headers,
    )

    assert resp.status_code == 200
    assert resp.json() == {"code": 0}
    assert dispatched is False
    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    assert event.external_event_id == "evt_callback_malformed"
    assert event.processing_status == "failed_terminal"
    assert event.attempt_count == 1
    assert event.error_message == "Malformed Feishu message callback: missing message_id, chat_id, sender_external_id"


async def test_feishu_signed_callback_inactive_installation_acknowledges_and_audits_without_dispatch(
    test_client,
    test_session,
    test_engine,
    monkeypatch,
):
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-callback"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    dispatched = False

    async def fake_process(session, installation, payload, *, preaccepted_event_log_id=None):
        nonlocal dispatched
        dispatched = True
        return {"status": "completed"}

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr("server.routers.collaboration.process_feishu_event", fake_process)
    monkeypatch.setattr("server.routers.collaboration.AsyncSessionFactory", test_session_factory)
    await test_client.post(
        "/api/collaboration/installations/feishu",
        json={
            "app_id": "cli_callback_inactive",
            "app_secret": "secret",
            "connection_mode": "websocket",
            "verification_token": "verify-token-inactive",
            "encrypt_key": "encrypt-key-inactive",
        },
    )
    installation = (await test_session.execute(select(CollaborationInstallation))).scalar_one()
    installation.is_active = False
    installation.health_status = "disconnected"
    await test_session.commit()
    body, headers = _encrypted_feishu_callback(
        {
            "header": {"event_id": "evt_callback_inactive", "event_type": "im.message.receive_v1"},
            "token": "verify-token-inactive",
            "event": {
                "sender": {"sender_id": {"open_id": "ou_callback_inactive"}},
                "message": {
                    "message_id": "om_callback_inactive",
                    "chat_id": "oc_callback_inactive",
                    "chat_type": "group",
                    "content": "{\"text\":\"hello\"}",
                },
            },
        },
        "encrypt-key-inactive",
    )

    resp = await test_client.post(
        f"/api/collaboration/feishu/callback/{installation.public_id}",
        content=body,
        headers=headers,
    )

    assert resp.status_code == 200
    assert resp.json() == {"code": 0}
    assert dispatched is False
    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    assert event.external_event_id == "evt_callback_inactive"
    assert event.external_chat_id == "oc_callback_inactive"
    assert event.external_user_id == "ou_callback_inactive"
    assert event.processing_status == "inactive"
    assert event.attempt_count == 0
    assert event.error_message == "Feishu installation is inactive; callback event acknowledged without dispatch."


async def test_feishu_signed_callback_background_failure_marks_preaccepted_event(
    test_client,
    test_session,
    test_engine,
    monkeypatch,
):
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-callback"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    async def failing_process(session, installation, payload, *, preaccepted_event_log_id=None):
        raise RuntimeError("processor exploded app_secret=secret tenant_access_token=t1 Authorization: Bearer tok.abc")

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr("server.routers.collaboration.process_feishu_event", failing_process)
    monkeypatch.setattr("server.routers.collaboration.AsyncSessionFactory", test_session_factory)
    await test_client.post(
        "/api/collaboration/installations/feishu",
        json={
            "app_id": "cli_callback_failure",
            "app_secret": "secret",
            "connection_mode": "websocket",
            "verification_token": "verify-token-failure",
            "encrypt_key": "encrypt-key-failure",
        },
    )
    installation = (await test_session.execute(select(CollaborationInstallation))).scalar_one()
    installation.is_active = True
    await test_session.commit()
    body, headers = _encrypted_feishu_callback(
        {
            "header": {"event_id": "evt_callback_failure", "event_type": "im.message.receive_v1"},
            "token": "verify-token-failure",
            "event": {
                "sender": {"sender_id": {"open_id": "ou_callback_failure"}},
                "message": {
                    "message_id": "om_callback_failure",
                    "chat_id": "oc_callback_failure",
                    "chat_type": "group",
                    "content": "{\"text\":\"hello\"}",
                },
            },
        },
        "encrypt-key-failure",
    )

    resp = await test_client.post(
        f"/api/collaboration/feishu/callback/{installation.public_id}",
        content=body,
        headers=headers,
    )

    assert resp.status_code == 200
    assert resp.json() == {"code": 0}
    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    assert event.external_event_id == "evt_callback_failure"
    assert event.processing_status == "failed_terminal"
    assert event.attempt_count == 1
    assert event.error_message is not None
    assert "secret" not in event.error_message
    assert "t1" not in event.error_message
    assert "tok.abc" not in event.error_message


async def test_feishu_callback_background_inactive_race_marks_preaccepted_event_terminal(
    test_client,
    test_session,
    test_engine,
    monkeypatch,
):
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)

    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-callback"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    async def unexpected_process(session, installation, payload, *, preaccepted_event_log_id=None):
        raise AssertionError("background processor must not run after installation is deactivated")

    captured_background_tasks: list[tuple] = []

    def capture_background_task(self, func, *args, **kwargs):
        captured_background_tasks.append((func, args, kwargs))

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr("server.routers.collaboration.process_feishu_event", unexpected_process)
    monkeypatch.setattr("server.routers.collaboration.AsyncSessionFactory", test_session_factory)
    monkeypatch.setattr("starlette.background.BackgroundTasks.add_task", capture_background_task)
    await test_client.post(
        "/api/collaboration/installations/feishu",
        json={
            "app_id": "cli_callback_inactive_race",
            "app_secret": "secret",
            "connection_mode": "websocket",
            "verification_token": "verify-token-inactive-race",
            "encrypt_key": "encrypt-key-inactive-race",
        },
    )
    installation = (await test_session.execute(select(CollaborationInstallation))).scalar_one()
    installation.is_active = True
    await test_session.commit()
    body, headers = _encrypted_feishu_callback(
        {
            "header": {"event_id": "evt_callback_inactive_race", "event_type": "im.message.receive_v1"},
            "token": "verify-token-inactive-race",
            "event": {
                "sender": {"sender_id": {"open_id": "ou_callback_inactive_race"}},
                "message": {
                    "message_id": "om_callback_inactive_race",
                    "chat_id": "oc_callback_inactive_race",
                    "chat_type": "group",
                    "content": "{\"text\":\"hello\"}",
                },
            },
        },
        "encrypt-key-inactive-race",
    )

    resp = await test_client.post(
        f"/api/collaboration/feishu/callback/{installation.public_id}",
        content=body,
        headers=headers,
    )
    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    assert len(captured_background_tasks) == 1
    assert event.processing_status == "received"
    installation.is_active = False
    installation.health_status = "disconnected"
    await test_session.commit()

    background_func, background_args, background_kwargs = captured_background_tasks[0]
    await background_func(*background_args, **background_kwargs)

    assert resp.status_code == 200
    await test_session.refresh(event)
    assert event.processing_status == "inactive"
    assert event.attempt_count == 0
    assert event.error_message == "Feishu installation became inactive before background callback dispatch."


async def test_feishu_callback_rejects_unsigned_or_unencrypted_public_id_injection(test_client, test_session, monkeypatch):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-callback"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    await test_client.post(
        "/api/collaboration/installations/feishu",
        json={
            "app_id": "cli_callback",
            "app_secret": "secret",
            "connection_mode": "websocket",
            "verification_token": "verify-token",
            "encrypt_key": "encrypt-key",
        },
    )
    installation = (await test_session.execute(select(CollaborationInstallation))).scalar_one()

    resp = await test_client.post(
        f"/api/collaboration/feishu/callback/{installation.public_id}",
        json={"header": {"event_id": "evt_injected", "event_type": "im.message.receive_v1"}},
    )

    assert resp.status_code == 401
    assert (await test_session.execute(select(CollaborationEventLog))).scalars().all() == []


async def test_feishu_callback_rejects_bad_signature_without_dispatching(test_client, test_session, monkeypatch):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-callback"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    dispatched = False

    async def fake_process(session, installation, payload, *, preaccepted_event_log_id=None):
        nonlocal dispatched
        dispatched = True
        return {"status": "completed"}

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr("server.routers.collaboration.process_feishu_event", fake_process)
    await test_client.post(
        "/api/collaboration/installations/feishu",
        json={
            "app_id": "cli_callback_bad_sig",
            "app_secret": "secret",
            "connection_mode": "websocket",
            "verification_token": "verify-token-bad-sig",
            "encrypt_key": "encrypt-key-bad-sig",
        },
    )
    installation = (await test_session.execute(select(CollaborationInstallation))).scalar_one()
    body, headers = _encrypted_feishu_callback(
        {
            "header": {"event_id": "evt_bad_sig", "event_type": "im.message.receive_v1"},
            "token": "verify-token-bad-sig",
            "event": {"message": {"message_id": "om_bad_sig"}},
        },
        "encrypt-key-bad-sig",
    )
    headers["X-Lark-Signature"] = "bad-signature"

    resp = await test_client.post(
        f"/api/collaboration/feishu/callback/{installation.public_id}",
        content=body,
        headers=headers,
    )

    assert resp.status_code == 401
    assert dispatched is False
    assert (await test_session.execute(select(CollaborationEventLog))).scalars().all() == []


async def test_feishu_callback_rejects_invalid_encrypted_payload_without_dispatching(
    test_client,
    test_session,
    monkeypatch,
):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-callback"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    dispatched = False

    async def fake_process(session, installation, payload, *, preaccepted_event_log_id=None):
        nonlocal dispatched
        dispatched = True
        return {"status": "completed"}

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr("server.routers.collaboration.process_feishu_event", fake_process)
    await test_client.post(
        "/api/collaboration/installations/feishu",
        json={
            "app_id": "cli_callback_bad_encrypt",
            "app_secret": "secret",
            "connection_mode": "websocket",
            "verification_token": "verify-token-bad-encrypt",
            "encrypt_key": "encrypt-key-bad-encrypt",
        },
    )
    installation = (await test_session.execute(select(CollaborationInstallation))).scalar_one()
    body = json.dumps({"encrypt": "not-valid-base64"}).encode("utf-8")
    timestamp = str(int(time.time()))
    nonce = "nonce-bad-encrypt"
    signature = hashlib.sha256((timestamp + nonce + "encrypt-key-bad-encrypt").encode("utf-8") + body).hexdigest()

    resp = await test_client.post(
        f"/api/collaboration/feishu/callback/{installation.public_id}",
        content=body,
        headers={
            "X-Lark-Request-Timestamp": timestamp,
            "X-Lark-Request-Nonce": nonce,
            "X-Lark-Signature": signature,
            "Content-Type": "application/json",
        },
    )

    assert resp.status_code == 401
    assert dispatched is False
    assert (await test_session.execute(select(CollaborationEventLog))).scalars().all() == []


async def test_feishu_external_identity_mapping_api_requires_same_tenant_member(
    test_client,
    test_session,
    monkeypatch,
):
    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-b"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": f"tenant-{uuid4().hex[:6]}",
            "external_tenant_name": "Acme",
        }

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_b", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]
    installation = (
        await test_session.execute(select(CollaborationInstallation).where(CollaborationInstallation.id == installation_id))
    ).scalar_one()

    identity = ExternalIdentity(
        tenant_id=installation.tenant_id,
        platform="feishu",
        installation_id=installation.id,
        external_user_id="ou_seen",
        union_id="on_seen",
        status="seen",
    )
    test_session.add(identity)

    member_user = User(
        id=uuid4(),
        email=f"feishu-map-{uuid4().hex[:8]}@test.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        full_name="Mapped User",
    )
    test_session.add(member_user)
    await test_session.flush()
    test_session.add(TenantMember(user_id=member_user.id, tenant_id=installation.tenant_id, role="member"))

    outsider_user = User(
        id=uuid4(),
        email=f"feishu-outsider-{uuid4().hex[:8]}@test.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    test_session.add(outsider_user)
    await test_session.flush()
    outsider_tenant = Tenant(
        id=uuid4(),
        name="Other Tenant",
        slug=f"other-{uuid4().hex[:8]}",
        owner_id=outsider_user.id,
    )
    test_session.add(outsider_tenant)
    await test_session.flush()
    test_session.add(TenantMember(user_id=outsider_user.id, tenant_id=outsider_tenant.id, role="owner"))
    await test_session.commit()

    before = await test_client.get(f"/api/collaboration/installations/{installation_id}/feishu/identities")
    assert before.status_code == 200
    assert before.json()["data"]["items"] == [
        {
            "id": str(identity.id),
            "external_user_id": "ou_seen",
            "union_id": "on_seen",
            "status": "seen",
            "user_id": None,
            "byaan_user_id": None,
            "mapped_user": None,
            "last_seen_at": before.json()["data"]["items"][0]["last_seen_at"],
        }
    ]

    outsider = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/identities/{identity.id}/mapping",
        json={"user_id": str(outsider_user.id)},
    )
    assert outsider.status_code == 404

    mapped = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/identities/{identity.id}/mapping",
        json={"user_id": str(member_user.id)},
    )
    assert mapped.status_code == 200
    mapped_data = mapped.json()["data"]
    assert mapped_data["status"] == "linked"
    assert mapped_data["byaan_user_id"] == str(member_user.id)
    assert mapped_data["mapped_user"] == {
        "id": str(member_user.id),
        "email": member_user.email,
        "full_name": "Mapped User",
    }

    await test_session.refresh(identity)
    assert identity.byaan_user_id == member_user.id
    assert identity.user_id == member_user.id
    assert identity.status == "linked"

    unmap = await test_client.delete(
        f"/api/collaboration/installations/{installation_id}/feishu/identities/{identity.id}/mapping"
    )
    assert unmap.status_code == 200
    assert unmap.json()["data"]["status"] == "seen"
