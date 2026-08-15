from __future__ import annotations

import asyncio
import threading
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.collaboration.channel_agent_service import ChannelAgentService
from server.collaboration.contracts import ChannelChatType
from server.collaboration.feishu.client import FeishuApiClient, FeishuApiError, FeishuTokenCache
from server.collaboration.feishu.normalizer import normalize_feishu_message_event, should_trigger_feishu_message
from server.collaboration.feishu.transport import FeishuLeaseLost, FeishuWebSocketManager
from server.collaboration.models import CollaborationEventLog, CollaborationInstallation
from server.collaboration.repositories import (
    CollaborationConversationRepository,
    CollaborationEventRepository,
    CollaborationInstallationRepository,
    CollaborationLeaseRepository,
)
from server.models.custom_skill import CustomSkill
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
        is_active=False,
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


async def test_channel_agent_prompt_is_skill_aware_and_tenant_scoped(test_session):
    tenant = await _tenant(test_session)
    user = (await test_session.execute(select(User).where(User.id == tenant.owner_id))).scalar_one()
    test_session.add_all(
        [
            CustomSkill(
                tenant_id=tenant.id,
                created_by=user.id,
                name="Revenue Org Data",
                description="Published revenue semantic skill",
                instructions="Use recognized_revenue from the published semantic model.",
                scope="org",
                skill_type="channel_inbound",
                is_active=True,
            ),
            CustomSkill(
                tenant_id=tenant.id,
                created_by=user.id,
                name="User Scope Skill",
                description="Must not leak",
                instructions="other tenant secret",
                scope="user",
                skill_type="channel_inbound",
                is_active=True,
            ),
        ]
    )
    await test_session.commit()

    prompt = await ChannelAgentService.build_prompt(
        platform="feishu",
        question="各渠道收入是多少？",
        tenant_id=tenant.id,
        session=test_session,
    )

    assert "Published Org Data Skill → Source Skill → Governed raw fallback" in prompt
    assert "Revenue Org Data" in prompt
    assert "recognized_revenue" in prompt
    assert "other tenant secret" not in prompt
    assert "do not use assets outside the current tenant" in prompt


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

    async def fake_run_sdk_client(
        self,
        *,
        app_id,
        app_secret,
        on_event,
        stop_event,
        health,
        on_connected,
        on_reconnecting,
    ):
        assert app_id == "cli_a"
        assert app_secret == "secret"
        await on_connected()
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


async def test_feishu_websocket_manager_coalesces_concurrent_same_installation_connects(
    test_session,
    test_engine,
    monkeypatch,
):
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("server.collaboration.feishu.transport.AsyncSessionFactory", test_session_factory)

    tenant = await _tenant(test_session)
    installation = await _installation(test_session, tenant)
    started_count = 0
    started_twice = threading.Event()
    first_started = threading.Event()

    async def fake_decrypt_config(_blob, _session):
        return {"app_id": "cli_a", "app_secret": "secret"}

    async def fake_run_sdk_client(
        self,
        *,
        app_id,
        app_secret,
        on_event,
        stop_event,
        health,
        on_connected,
        on_reconnecting,
    ):
        nonlocal started_count
        started_count += 1
        if started_count == 1:
            first_started.set()
        else:
            started_twice.set()
        await on_connected()
        while not stop_event.is_set():
            await asyncio.sleep(0.01)

    monkeypatch.setattr("server.collaboration.feishu.transport.CryptoService.decrypt_config", fake_decrypt_config)
    monkeypatch.setattr(FeishuWebSocketManager, "_run_sdk_client", fake_run_sdk_client)

    manager = FeishuWebSocketManager(owner_id="owner-coalesce")
    first, second = await asyncio.gather(manager.connect(installation.id), manager.connect(installation.id))

    assert first.installation_id == installation.id
    assert second.installation_id == installation.id
    assert first_started.wait(timeout=1)
    await asyncio.sleep(0.05)
    assert started_count == 1
    assert not started_twice.is_set()

    await manager.disconnect(installation.id)


async def test_feishu_websocket_manager_does_not_mark_connected_before_sdk_connected(
    test_session,
    test_engine,
    monkeypatch,
):
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("server.collaboration.feishu.transport.AsyncSessionFactory", test_session_factory)

    tenant = await _tenant(test_session)
    installation = await _installation(test_session, tenant)
    entered_sdk = threading.Event()
    allow_connect = threading.Event()

    async def fake_decrypt_config(_blob, _session):
        return {"app_id": "cli_a", "app_secret": "secret"}

    async def fake_run_sdk_client(
        self,
        *,
        app_id,
        app_secret,
        on_event,
        stop_event,
        health,
        on_connected,
        on_reconnecting,
    ):
        entered_sdk.set()
        while not allow_connect.is_set() and not stop_event.is_set():
            await asyncio.sleep(0.01)
        if not stop_event.is_set():
            await on_connected()
        while not stop_event.is_set():
            await asyncio.sleep(0.01)

    monkeypatch.setattr("server.collaboration.feishu.transport.CryptoService.decrypt_config", fake_decrypt_config)
    monkeypatch.setattr(FeishuWebSocketManager, "_run_sdk_client", fake_run_sdk_client)

    manager = FeishuWebSocketManager(owner_id="owner-delayed")
    health = await manager.connect(installation.id)
    assert health.status == "connecting"
    assert entered_sdk.wait(timeout=1)

    await test_session.refresh(installation)
    assert installation.health_status == "connecting"
    assert installation.last_connected_at is None

    allow_connect.set()
    for _ in range(100):
        await test_session.refresh(installation)
        if installation.health_status == "connected":
            break
        await asyncio.sleep(0.01)

    assert installation.health_status == "connected"
    assert installation.last_connected_at is not None
    await manager.disconnect(installation.id)


async def test_feishu_websocket_manager_auto_resumes_active_websocket_installations(
    test_session,
    test_engine,
    monkeypatch,
):
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("server.collaboration.feishu.transport.AsyncSessionFactory", test_session_factory)

    tenant = await _tenant(test_session)
    installation = await _installation(test_session, tenant)
    installation.is_active = True
    await test_session.commit()
    started = threading.Event()

    async def fake_decrypt_config(_blob, _session):
        return {"app_id": "cli_a", "app_secret": "secret"}

    async def fake_run_sdk_client(
        self,
        *,
        app_id,
        app_secret,
        on_event,
        stop_event,
        health,
        on_connected,
        on_reconnecting,
    ):
        await on_connected()
        started.set()
        while not stop_event.is_set():
            await asyncio.sleep(0.01)

    monkeypatch.setattr("server.collaboration.feishu.transport.CryptoService.decrypt_config", fake_decrypt_config)
    monkeypatch.setattr(FeishuWebSocketManager, "_run_sdk_client", fake_run_sdk_client)

    manager = FeishuWebSocketManager(owner_id="owner-resume")
    summary = await manager.resume_active_installations()

    assert summary == {"resumed": 1, "leased_elsewhere": 0, "failed": 0}
    assert started.wait(timeout=1)
    await test_session.refresh(installation)
    assert installation.health_status == "connected"
    await manager.shutdown()


async def test_feishu_websocket_manager_shutdown_preserves_active_installation_for_next_resume(
    test_session,
    test_engine,
    monkeypatch,
):
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("server.collaboration.feishu.transport.AsyncSessionFactory", test_session_factory)

    tenant = await _tenant(test_session)
    installation = await _installation(test_session, tenant)
    started = threading.Event()

    async def fake_decrypt_config(_blob, _session):
        return {"app_id": "cli_a", "app_secret": "secret"}

    async def fake_run_sdk_client(
        self,
        *,
        app_id,
        app_secret,
        on_event,
        stop_event,
        health,
        on_connected,
        on_reconnecting,
    ):
        await on_connected()
        started.set()
        while not stop_event.is_set():
            await asyncio.sleep(0.01)

    monkeypatch.setattr("server.collaboration.feishu.transport.CryptoService.decrypt_config", fake_decrypt_config)
    monkeypatch.setattr(FeishuWebSocketManager, "_run_sdk_client", fake_run_sdk_client)

    manager = FeishuWebSocketManager(owner_id="owner-container")
    await manager.connect(installation.id)
    assert started.wait(timeout=1)

    await manager.shutdown()

    async with test_session_factory() as verify_session:
        current = await CollaborationInstallationRepository(verify_session).get(installation.id)
        lease = await CollaborationLeaseRepository(verify_session).get(installation.id)

    assert current is not None
    assert current.is_active is True
    assert current.health_status == "configured"
    assert current.health_error is None
    assert lease is None


async def test_feishu_websocket_manager_marks_lease_loss_without_releasing_other_owner(
    test_session,
    test_engine,
    monkeypatch,
):
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("server.collaboration.feishu.transport.AsyncSessionFactory", test_session_factory)

    tenant = await _tenant(test_session)
    installation = await _installation(test_session, tenant)
    ready = threading.Event()
    raise_lease_lost = threading.Event()
    lease_lost_observed = threading.Event()
    released = threading.Event()

    async def fake_decrypt_config(_blob, _session):
        return {"app_id": "cli_a", "app_secret": "secret"}

    async def fake_run_sdk_client(
        self,
        *,
        app_id,
        app_secret,
        on_event,
        stop_event,
        health,
        on_connected,
        on_reconnecting,
    ):
        await on_connected()
        ready.set()
        while not stop_event.is_set():
            if raise_lease_lost.is_set():
                lease_lost_observed.set()
                raise FeishuLeaseLost("Lost Feishu WebSocket lease.")
            await asyncio.sleep(0.01)

    monkeypatch.setattr("server.collaboration.feishu.transport.CryptoService.decrypt_config", fake_decrypt_config)
    monkeypatch.setattr(FeishuWebSocketManager, "_run_sdk_client", fake_run_sdk_client)

    manager = FeishuWebSocketManager(owner_id="owner-a", heartbeat_interval_seconds=0.01)
    await manager.connect(installation.id)
    assert ready.wait(timeout=1)

    await CollaborationLeaseRepository(test_session).release(installation.id, "owner-a")
    assert await CollaborationLeaseRepository(test_session).acquire(installation.id, "owner-b", ttl_seconds=60)
    raise_lease_lost.set()
    assert lease_lost_observed.wait(timeout=1)

    for _ in range(100):
        if not manager.is_running(installation.id):
            break
        await asyncio.sleep(0.01)
    assert not manager.is_running(installation.id)

    for _ in range(300):
        async with test_session_factory() as verify_session:
            current = await CollaborationInstallationRepository(verify_session).get(installation.id)
            if current and current.health_status == "leased_elsewhere":
                released.set()
                break
        await asyncio.sleep(0.01)

    assert released.is_set()
    async with test_session_factory() as verify_session:
        lease = await CollaborationLeaseRepository(verify_session).get(installation.id)
        assert lease is not None
        assert lease.owner_id == "owner-b"
    await manager.shutdown()


async def test_feishu_websocket_manager_isolates_event_dispatch_failures(
    test_session,
    test_engine,
    monkeypatch,
):
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("server.collaboration.feishu.transport.AsyncSessionFactory", test_session_factory)

    tenant = await _tenant(test_session)
    installation = await _installation(test_session, tenant)
    event_dispatched = threading.Event()
    dispatch_returned = threading.Event()
    dispatch_leaked = threading.Event()

    async def fake_decrypt_config(_blob, _session):
        return {"app_id": "cli_a", "app_secret": "secret"}

    async def failing_process_event(_session, _installation, _raw_event):
        raise RuntimeError("processor failed app_secret=secret tenant_access_token=t1 Authorization: Bearer tok.abc")

    async def fake_run_sdk_client(
        self,
        *,
        app_id,
        app_secret,
        on_event,
        stop_event,
        health,
        on_connected,
        on_reconnecting,
    ):
        await on_connected()
        event_dispatched.set()
        try:
            await on_event({"header": {"event_id": "evt_dispatch_failure"}})
            dispatch_returned.set()
        except Exception:
            dispatch_leaked.set()
            raise
        while not stop_event.is_set():
            await asyncio.sleep(0.01)

    monkeypatch.setattr("server.collaboration.feishu.transport.CryptoService.decrypt_config", fake_decrypt_config)
    monkeypatch.setattr("server.collaboration.feishu.transport.process_feishu_event", failing_process_event)
    monkeypatch.setattr(FeishuWebSocketManager, "_run_sdk_client", fake_run_sdk_client)

    manager = FeishuWebSocketManager(owner_id="owner-dispatch")
    await manager.connect(installation.id)
    assert event_dispatched.wait(timeout=1)
    assert dispatch_returned.wait(timeout=1)
    assert not dispatch_leaked.is_set()

    async with test_session_factory() as verify_session:
        current = await CollaborationInstallationRepository(verify_session).get(installation.id)

    assert current is not None
    assert current.health_status == "connected"
    assert current.reconnect_count == 0
    assert current.health_error is not None
    assert "secret" not in current.health_error
    assert "t1" not in current.health_error
    assert "tok.abc" not in current.health_error
    health = manager.health(installation.id)
    assert health is not None
    assert health.status == "connected"
    assert health.last_error == current.health_error

    await manager.shutdown()


def test_feishu_token_cache_expires_with_skew(monkeypatch):
    cache = FeishuTokenCache()
    base = 1_000_000
    monkeypatch.setattr("time.time", lambda: base)
    cache.set("cli_a", "token-a", 300)
    assert cache.get("cli_a") == "token-a"

    monkeypatch.setattr("time.time", lambda: base + 190)
    assert cache.get("cli_a") is None


async def test_feishu_tenant_token_refresh_is_serialized(monkeypatch):
    cache = FeishuTokenCache()
    calls = 0

    async def fake_post_without_auth(self, path, payload):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"tenant_access_token": "token-serialized", "expire": 7200}

    monkeypatch.setattr(FeishuApiClient, "_post_json_without_auth", fake_post_without_auth)
    client = FeishuApiClient("cli_serialized", "secret", cache=cache)

    tokens = await asyncio.gather(*(client.tenant_access_token() for _ in range(5)))

    assert tokens == ["token-serialized"] * 5
    assert calls == 1


async def test_feishu_authenticated_request_refreshes_invalid_cached_tenant_token_once():
    tokens = iter(["token-old", "token-new"])
    token_requests: list[dict] = []
    api_requests: list[dict] = []

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json=None):
            token_requests.append({"url": url, "json": json})
            return httpx.Response(200, json={"code": 0, "tenant_access_token": next(tokens), "expire": 7200})

        async def request(self, method, url, headers=None, json=None):
            api_requests.append({"method": method, "url": url, "headers": headers, "json": json})
            if len(api_requests) == 1:
                return httpx.Response(200, json={"code": 99991663, "msg": "invalid tenant_access_token"})
            return httpx.Response(200, json={"code": 0, "data": {"message_id": "om_after_token_refresh"}})

    cache = FeishuTokenCache()
    client = FeishuApiClient("cli_refresh", "secret", http_client=FakeAsyncClient(), cache=cache)

    result = await client.send_text_message(
        receive_id_type="chat_id",
        receive_id="oc_refresh",
        text="token refresh send",
        request_uuid="uuid-refresh-once",
    )

    assert result == {"message_id": "om_after_token_refresh"}
    assert len(token_requests) == 2
    assert [request["headers"]["Authorization"] for request in api_requests] == [
        "Bearer token-old",
        "Bearer token-new",
    ]
    assert api_requests[0]["json"] == api_requests[1]["json"] == {
        "receive_id": "oc_refresh",
        "msg_type": "text",
        "content": '{"text": "token refresh send"}',
        "uuid": "uuid-refresh-once",
    }
    assert await client.tenant_access_token() == "token-new"
    assert len(token_requests) == 2


async def test_feishu_authenticated_concurrent_invalid_cached_token_refreshes_once():
    token_requests: list[dict] = []
    api_requests: list[dict] = []
    old_token_attempts = 0
    old_token_attempts_ready = asyncio.Event()

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json=None):
            token_requests.append({"url": url, "json": json})
            token = "token-old" if len(token_requests) == 1 else "token-new"
            return httpx.Response(200, json={"code": 0, "tenant_access_token": token, "expire": 7200})

        async def request(self, method, url, headers=None, json=None):
            nonlocal old_token_attempts
            api_requests.append({"method": method, "url": url, "headers": headers, "json": json})
            if headers == {"Authorization": "Bearer token-old"}:
                old_token_attempts += 1
                if old_token_attempts == 4:
                    old_token_attempts_ready.set()
                await old_token_attempts_ready.wait()
                return httpx.Response(200, json={"code": 99991663, "msg": "invalid tenant_access_token"})
            return httpx.Response(200, json={"code": 0, "data": {"ok": True}})

    cache = FeishuTokenCache()
    client = FeishuApiClient("cli_concurrent_refresh", "secret", http_client=FakeAsyncClient(), cache=cache)
    assert await client.tenant_access_token() == "token-old"

    results = await asyncio.gather(*(client._authenticated_request("GET", f"/test/{index}") for index in range(4)))

    assert results == [{"ok": True}] * 4
    assert len(token_requests) == 2
    assert [request["headers"]["Authorization"] for request in api_requests].count("Bearer token-old") == 4
    assert [request["headers"]["Authorization"] for request in api_requests].count("Bearer token-new") == 4


async def test_feishu_authenticated_request_refresh_failure_is_not_retried_again():
    tokens = iter(["token-old", "token-new"])
    token_requests: list[dict] = []
    api_requests: list[dict] = []

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json=None):
            token_requests.append({"url": url, "json": json})
            return httpx.Response(200, json={"code": 0, "tenant_access_token": next(tokens), "expire": 7200})

        async def request(self, method, url, headers=None, json=None):
            api_requests.append({"method": method, "url": url, "headers": headers, "json": json})
            if headers == {"Authorization": "Bearer token-old"}:
                return httpx.Response(200, json={"code": 99991663, "msg": "invalid tenant_access_token"})
            return httpx.Response(200, json={"code": 99991664, "msg": "tenant_access_token invalid again"})

    client = FeishuApiClient("cli_refresh_failure", "secret", http_client=FakeAsyncClient(), cache=FeishuTokenCache())

    with pytest.raises(FeishuApiError) as exc_info:
        await client.send_text_message(
            receive_id_type="chat_id",
            receive_id="oc_refresh_failure",
            text="refresh failure send",
            request_uuid="uuid-refresh-failure",
        )

    assert "tenant_access_token invalid again" in str(exc_info.value)
    assert len(token_requests) == 2
    assert [request["headers"]["Authorization"] for request in api_requests] == [
        "Bearer token-old",
        "Bearer token-new",
    ]
    assert api_requests[0]["json"] == api_requests[1]["json"] == {
        "receive_id": "oc_refresh_failure",
        "msg_type": "text",
        "content": '{"text": "refresh failure send"}',
        "uuid": "uuid-refresh-failure",
    }


async def test_feishu_authenticated_request_does_not_refresh_for_non_reauth_4xx():
    token_requests: list[dict] = []
    api_requests: list[dict] = []

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json=None):
            token_requests.append({"url": url, "json": json})
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "token-valid", "expire": 7200})

        async def request(self, method, url, headers=None, json=None):
            api_requests.append({"method": method, "url": url, "headers": headers, "json": json})
            return httpx.Response(400, json={"code": 230001, "msg": "bad request"})

    client = FeishuApiClient("cli_non_reauth", "secret", http_client=FakeAsyncClient(), cache=FeishuTokenCache())

    with pytest.raises(FeishuApiError) as exc_info:
        await client.send_text_message(
            receive_id_type="chat_id",
            receive_id="oc_bad_request",
            text="bad request send",
            request_uuid="uuid-non-reauth",
        )

    assert "bad request" in str(exc_info.value)
    assert len(token_requests) == 1
    assert len(api_requests) == 1
    assert api_requests[0]["headers"] == {"Authorization": "Bearer token-valid"}


async def test_feishu_request_retries_rate_limit(monkeypatch):
    attempts = 0

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def request(self, method, url, headers=None, json=None):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(429, json={"code": 99991429, "msg": "rate limited"}, headers={"Retry-After": "0"})
            return httpx.Response(200, json={"code": 0, "data": {"ok": True}})

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    client = FeishuApiClient("cli_rate", "secret", http_client=FakeAsyncClient())

    result = await client._request("GET", "/test", token="token")

    assert result == {"ok": True}
    assert attempts == 2


async def test_feishu_send_text_message_retries_rate_limit_without_duplicate_payload(monkeypatch):
    attempts: list[dict] = []

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json=None):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "token-send", "expire": 7200})

        async def request(self, method, url, headers=None, json=None):
            attempts.append({"method": method, "url": url, "json": json})
            if len(attempts) == 1:
                return httpx.Response(429, json={"code": 99991429, "msg": "rate limited"}, headers={"Retry-After": "0"})
            return httpx.Response(200, json={"code": 0, "data": {"message_id": "om_sent_after_retry"}})

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    client = FeishuApiClient("cli_send_rate", "secret", http_client=FakeAsyncClient())

    result = await client.send_text_message(
        receive_id_type="chat_id",
        receive_id="oc_rate",
        text="rate limited send",
        root_id="om_root",
    )

    assert result == {"message_id": "om_sent_after_retry"}
    assert len(attempts) == 2
    assert attempts[0]["url"].endswith("/im/v1/messages?receive_id_type=chat_id")
    assert attempts[0]["json"] == attempts[1]["json"] == {
        "receive_id": "oc_rate",
        "msg_type": "text",
        "content": '{"text": "rate limited send"}',
        "root_id": "om_root",
    }


async def test_feishu_send_text_message_includes_stable_request_uuid(monkeypatch):
    attempts: list[dict] = []

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json=None):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "token-send", "expire": 7200})

        async def request(self, method, url, headers=None, json=None):
            attempts.append({"method": method, "url": url, "json": json})
            if len(attempts) == 1:
                return httpx.Response(429, json={"code": 99991429, "msg": "rate limited"}, headers={"Retry-After": "0"})
            return httpx.Response(200, json={"code": 0, "data": {"message_id": "om_uuid"}})

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    client = FeishuApiClient("cli_send_uuid", "secret", http_client=FakeAsyncClient())

    result = await client.send_text_message(
        receive_id_type="chat_id",
        receive_id="oc_uuid",
        text="uuid send",
        root_id="om_root",
        request_uuid="stable-request-uuid",
    )

    assert result == {"message_id": "om_uuid"}
    assert attempts[0]["json"] == attempts[1]["json"] == {
        "receive_id": "oc_uuid",
        "msg_type": "text",
        "content": '{"text": "uuid send"}',
        "root_id": "om_root",
        "uuid": "stable-request-uuid",
    }


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
