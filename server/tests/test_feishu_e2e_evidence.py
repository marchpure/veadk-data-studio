from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from scripts import feishu_collaboration_e2e as e2e
from server.collaboration.models import (
    CollaborationConversation,
    CollaborationDeliveryTarget,
    CollaborationEventLog,
    CollaborationInstallation,
    ExternalIdentity,
)
from server.models.notebooks import Notebook
from server.models.tenant import Tenant
from server.models.user import User

pytestmark = pytest.mark.asyncio


class _SessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _SessionFactory:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _SessionContext(self._session)


async def test_e2e_snapshot_includes_external_identity_and_delivery_target_evidence(test_session, monkeypatch):
    user = User(
        id=uuid4(),
        email=f"feishu-evidence-{uuid4().hex[:8]}@test.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    test_session.add(user)
    await test_session.flush()
    tenant = Tenant(id=uuid4(), name="Feishu Evidence Tenant", slug=f"feishu-evidence-{uuid4().hex[:8]}", owner_id=user.id)
    test_session.add(tenant)
    await test_session.flush()
    installation = CollaborationInstallation(
        tenant_id=tenant.id,
        platform="feishu",
        external_tenant_id="tenant-evidence",
        app_id="cli_evidence",
        credentials_encrypted="encrypted",
        connection_mode="websocket",
        health_status="connected",
        is_active=True,
        config_json={
            "tenant_token_expires_at": "2026-08-15T10:00:00",
            "callback": {
                "url_verification": "verified",
                "last_url_verification_at": "2026-08-15T09:30:00",
                "verification_token_configured": True,
                "encrypt_key_configured": True,
                "event_ingress": "signed_encrypted_only",
            },
            "event_subscription": {
                "mode": "websocket",
                "required_event_types": ["im.message.receive_v1"],
                "remote_status": "observed",
                "ready": True,
                "first_event_observed_at": "2026-08-15T09:40:00",
                "last_event_observed_at": "2026-08-15T09:45:00",
                "last_event_id": "evt_1234567890abcdef",
                "operator_action": "Event im.message.receive_v1 has been observed over the Feishu WebSocket connection.",
            },
        },
    )
    test_session.add(installation)
    await test_session.flush()
    test_session.add(
        Notebook(
            tenant_id=tenant.id,
            created_by=user.id,
            notebook_name="Feishu evidence notebook",
        )
    )
    await test_session.flush()
    notebook = (await test_session.execute(select(Notebook).where(Notebook.tenant_id == tenant.id))).scalars().first()
    conversation = CollaborationConversation(
        installation_id=installation.id,
        external_chat_id="oc_chat_1234567890abcdef",
        external_root_id="om_root_1234567890abcdef",
        normalized_root_id="om_root_1234567890abcdef",
        external_user_id="ou_user_1234567890abcdef",
        chat_type="topic_group",
        notebook_id=notebook.id if notebook else None,
        bot_owned=True,
    )
    test_session.add(conversation)
    await test_session.flush()
    test_session.add(
        CollaborationEventLog(
            installation_id=installation.id,
            platform="feishu",
            external_event_id="evt_1234567890abcdef",
            event_type="message",
            external_chat_id="oc_chat_1234567890abcdef",
            external_user_id="ou_user_1234567890abcdef",
            conversation_id=conversation.id,
            notebook_id=notebook.id if notebook else None,
            run_id="run-evidence-1",
            processing_status="completed",
            attempt_count=1,
        )
    )
    test_session.add(
        ExternalIdentity(
            tenant_id=tenant.id,
            platform="feishu",
            installation_id=installation.id,
            external_user_id="ou_user_1234567890abcdef",
            union_id="on_union_abcdef123456",
            user_id=user.id,
            byaan_user_id=user.id,
            status="seen",
        )
    )
    test_session.add(
        CollaborationDeliveryTarget(
            installation_id=installation.id,
            target_type="topic_group",
            external_target_id="oc_chat_1234567890abcdef",
            external_root_id="om_root_1234567890abcdef",
            normalized_root_id="om_root_1234567890abcdef",
            display_name="Feishu E2E Test",
            is_verified=True,
        )
    )
    await test_session.commit()

    monkeypatch.setattr(e2e, "AsyncSessionFactory", _SessionFactory(test_session))

    snapshot = await e2e.FeishuCollaborationEvidence(installation.id).snapshot()

    assert snapshot["installation"]["tenant_token_expires_at"] == "2026-08-15T10:00:00"
    assert snapshot["installation"]["callback"] == {
        "url_verification": "verified",
        "last_url_verification_at": "2026-08-15T09:30:00",
        "verification_token_configured": True,
        "encrypt_key_configured": True,
        "event_ingress": "signed_encrypted_only",
    }
    assert snapshot["installation"]["event_subscription"] == {
        "mode": "websocket",
        "required_event_types": ["im.message.receive_v1"],
        "remote_status": "observed",
        "ready": True,
        "first_event_observed_at": "2026-08-15T09:40:00",
        "last_event_observed_at": "2026-08-15T09:45:00",
        "last_event_ref": e2e._hash_ref("evt_1234567890abcdef", prefix="evt"),
        "operator_action": "Event im.message.receive_v1 has been observed over the Feishu WebSocket connection.",
    }
    assert snapshot["recent_events"] == [
        {
            "event_ref": e2e._hash_ref("evt_1234567890abcdef", prefix="evt"),
            "event_type": "message",
            "chat_ref": e2e._hash_ref("oc_chat_1234567890abcdef", prefix="chat"),
            "sender_ref": e2e._hash_ref("ou_user_1234567890abcdef", prefix="user"),
            "conversation_id": str(conversation.id),
            "notebook_id": str(notebook.id) if notebook else None,
            "run_id": "run-evidence-1",
            "status": "completed",
            "attempt_count": 1,
            "error": None,
            "created_at": snapshot["recent_events"][0]["created_at"],
            "updated_at": snapshot["recent_events"][0]["updated_at"],
        }
    ]
    assert snapshot["recent_external_identities"] == [
        {
            "platform": "feishu",
            "external_user_ref": e2e._hash_ref("ou_user_1234567890abcdef", prefix="user"),
            "union_ref": e2e._hash_ref("on_union_abcdef123456", prefix="union"),
            "status": "seen",
            "user_id": str(user.id),
            "byaan_user_id": str(user.id),
            "last_seen_at": snapshot["recent_external_identities"][0]["last_seen_at"],
        }
    ]
    assert snapshot["recent_delivery_targets"] == [
        {
            "target_type": "topic_group",
            "target_ref": e2e._hash_ref("oc_chat_1234567890abcdef", prefix="target"),
            "root_ref": e2e._hash_ref("om_root_1234567890abcdef", prefix="root"),
            "is_verified": True,
            "updated_at": snapshot["recent_delivery_targets"][0]["updated_at"],
        }
    ]
    rendered = str(snapshot)
    assert "evt_1234567890abcdef" not in rendered
    assert "ou_user_1234567890abcdef" not in rendered
    assert "oc_chat_1234567890abcdef" not in rendered
    assert "Feishu E2E Test" not in rendered


async def test_e2e_list_chats_redacts_chat_ids_and_names(monkeypatch):
    class FakeClient:
        async def list_chats(self, max_items=200):
            return [
                {
                    "chat_id": "oc_chat_1234567890abcdef",
                    "name": "Sensitive Test Group",
                    "chat_type": "group",
                }
            ]

    evidence = e2e.FeishuCollaborationEvidence()

    async def fake_client():
        return FakeClient()

    monkeypatch.setattr(evidence, "_client", fake_client)

    chats = await evidence.list_chats()

    assert chats == [
        {
            "chat_ref": e2e._hash_ref("oc_chat_1234567890abcdef", prefix="chat"),
            "chat_type": "group",
        }
    ]
    rendered = str(chats)
    assert "oc_chat_1234567890abcdef" not in rendered
    assert "Sensitive Test Group" not in rendered
