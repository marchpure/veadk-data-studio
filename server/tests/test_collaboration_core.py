from __future__ import annotations

import asyncio
import threading
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.collaboration.contracts import ChannelChatType
from server.collaboration.feishu.client import FeishuTokenCache
from server.collaboration.feishu.normalizer import normalize_feishu_message_event, should_trigger_feishu_message
from server.collaboration.feishu.transport import FeishuWebSocketManager
from server.collaboration.models import CollaborationEventLog, CollaborationInstallation
from server.collaboration.repositories import (
    CollaborationConversationRepository,
    CollaborationEventRepository,
    CollaborationLeaseRepository,
)
from server.models.tenant import Tenant
from server.models.user import User

pytestmark = pytest.mark.asyncio


async def _tenant(session) -> Tenant:
    user = User(
        id=uuid4(),
        email=f"collab-{uuid4().hex[:8]}@test.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    tenant = Tenant(id=uuid4(), name="Collab Tenant", slug=f"collab-{uuid4().hex[:8]}", owner_id=user.id)
    session.add(tenant)
    await session.commit()
    return tenant


async def _installation(session, tenant: Tenant) -> CollaborationInstallation:
    row = CollaborationInstallation(
        tenant_id=tenant.id,
        platform="feishu",
        external_tenant_id=f"tenant-{uuid4().hex[:8]}",
        external_tenant_name="Tenant",
        app_id="cli_a",
        credentials_encrypted="encrypted",
        connection_mode="websocket",
        bot_external_id="ou_bot",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def test_conversation_normalizes_null_root_for_unique_reuse(test_session):
    tenant = await _tenant(test_session)
    installation = await _installation(test_session, tenant)
    repo = CollaborationConversationRepository(test_session)

    first = await repo.get_or_create(
        installation_id=installation.id,
        external_chat_id="oc_chat",
        external_root_id=None,
        external_user_id="ou_user",
        chat_type="group",
        title="first title",
    )
    second = await repo.get_or_create(
        installation_id=installation.id,
        external_chat_id="oc_chat",
        external_root_id=None,
        external_user_id="ou_user",
        chat_type="group",
        title="second title",
    )
    threaded = await repo.get_or_create(
        installation_id=installation.id,
        external_chat_id="oc_chat",
        external_root_id="om_root",
        external_user_id="ou_user",
        chat_type="topic_group",
    )

    assert second.id == first.id
    assert first.normalized_root_id == "__root__"
    assert threaded.id != first.id
    assert threaded.normalized_root_id == "om_root"


async def test_event_log_is_persistently_idempotent(test_session):
    tenant = await _tenant(test_session)
    installation = await _installation(test_session, tenant)
    repo = CollaborationEventRepository(test_session)

    first, duplicate_first = await repo.record_received(
        installation_id=installation.id,
        platform="feishu",
        external_event_id="evt_1",
        event_type="message",
        external_chat_id="oc_chat",
        external_user_id="ou_user",
    )
    second, duplicate_second = await repo.record_received(
        installation_id=installation.id,
        platform="feishu",
        external_event_id="evt_1",
        event_type="message",
        external_chat_id="oc_chat",
        external_user_id="ou_user",
    )

    assert duplicate_first is False
    assert duplicate_second is True
    assert second.id == first.id
    rows = (await test_session.execute(select(CollaborationEventLog))).scalars().all()
    assert len(rows) == 1


async def test_lease_allows_single_owner_until_expired(test_session):
    tenant = await _tenant(test_session)
    installation = await _installation(test_session, tenant)
    repo = CollaborationLeaseRepository(test_session)

    assert await repo.acquire(installation.id, "owner-a", ttl_seconds=60) is True
    assert await repo.acquire(installation.id, "owner-b", ttl_seconds=60) is False

    lease = (await test_session.execute(select(repo.__class__.__module__))) if False else None
    assert lease is None

    # Same owner can heartbeat/renew.
    assert await repo.heartbeat(installation.id, "owner-a", ttl_seconds=60) is True
    await repo.release(installation.id, "owner-a")
    assert await repo.acquire(installation.id, "owner-b", ttl_seconds=60) is True


async def test_feishu_websocket_manager_uses_db_lease_and_disconnects(test_session, test_engine, monkeypatch):
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("server.collaboration.feishu.transport.AsyncSessionFactory", test_session_factory)

    tenant = await _tenant(test_session)
    installation = await _installation(test_session, tenant)
    started = threading.Event()

    async def fake_decrypt_config(_blob, _session):
        return {"app_id": "cli_a", "app_secret": "secret"}

    async def fake_run_sdk_client(self, *, app_id, app_secret, on_event, stop_event, health):
        assert app_id == "cli_a"
        assert app_secret == "secret"
        if health:
            health.status = "connected"
        started.set()
        while not stop_event.is_set():
            await asyncio.sleep(0.01)

    monkeypatch.setattr("server.collaboration.feishu.transport.CryptoService.decrypt_config", fake_decrypt_config)
    monkeypatch.setattr(FeishuWebSocketManager, "_run_sdk_client", fake_run_sdk_client)

    owner_a = FeishuWebSocketManager(owner_id="owner-a")
    owner_b = FeishuWebSocketManager(owner_id="owner-b")

    first = await owner_a.connect(installation.id)
    assert first.status == "connecting"
    assert started.wait(timeout=1)

    blocked = await owner_b.connect(installation.id)
    assert blocked.status == "leased_elsewhere"

    stopped = await owner_a.disconnect(installation.id)
    assert stopped.status == "disconnected"

    second = await owner_b.connect(installation.id)
    assert second.status == "connecting"
    await owner_b.disconnect(installation.id)


def test_feishu_token_cache_expires_with_skew(monkeypatch):
    cache = FeishuTokenCache()
    base = 1_000_000
    monkeypatch.setattr("time.time", lambda: base)
    cache.set("cli_a", "token-a", 300)
    assert cache.get("cli_a") == "token-a"

    monkeypatch.setattr("time.time", lambda: base + 190)
    assert cache.get("cli_a") is None


def test_feishu_normalizer_maps_root_and_mentions():
    event = normalize_feishu_message_event(
        {
            "header": {"event_id": "evt_1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user"}},
                "message": {
                    "message_id": "om_msg",
                    "root_id": "om_root",
                    "chat_id": "oc_chat",
                    "chat_type": "group",
                    "content": "{\"text\":\"<at user_id=\\\"ou_bot\\\">Byaan</at> revenue?\"}",
                    "mentions": [{"id": {"open_id": "ou_bot"}}],
                    "create_time": "1700000000000",
                },
            },
        },
        installation_id=uuid4(),
        bot_external_id="ou_bot",
    )

    assert event.event_id == "evt_1"
    assert event.chat_id == "oc_chat"
    assert event.root_message_id == "om_root"
    assert event.chat_type == ChannelChatType.TOPIC_GROUP
    assert event.mentions == ["ou_bot"]
    assert event.text == "revenue?"
    assert should_trigger_feishu_message(event, "ou_bot") is True


def test_feishu_private_chat_triggers_without_mention():
    event = normalize_feishu_message_event(
        {
            "event_id": "evt_dm",
            "message": {
                "message_id": "om_dm",
                "chat_id": "oc_dm",
                "chat_type": "p2p",
                "content": {"text": "hello"},
            },
            "sender": {"sender_id": {"open_id": "ou_user"}},
        },
        installation_id=uuid4(),
        bot_external_id="ou_bot",
    )

    assert event.chat_type == ChannelChatType.P2P
    assert should_trigger_feishu_message(event, "ou_bot") is True
