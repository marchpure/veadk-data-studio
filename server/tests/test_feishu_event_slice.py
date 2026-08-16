from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from server.collaboration.feishu.adapter import FeishuChannelAdapter
from server.collaboration.feishu.event_processor import process_feishu_event
from server.collaboration.models import (
    CollaborationConversation,
    CollaborationDeliveryTarget,
    CollaborationEventLog,
    CollaborationInstallation,
    CollaborationResponseRef,
    ExternalIdentity,
)
from server.collaboration.repositories import CollaborationInstallationRepository
from server.models.llm_connections import LLMConnection
from server.models.notebooks import Notebook
from server.models.tenant import Tenant
from server.models.user import User
from server.services.crypto_service import CryptoService

pytestmark = pytest.mark.asyncio


async def _tenant(session) -> tuple[Tenant, User]:
    user = User(
        id=uuid4(),
        email=f"feishu-{uuid4().hex[:8]}@test.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    tenant = Tenant(id=uuid4(), name="Feishu Tenant", slug=f"feishu-{uuid4().hex[:8]}", owner_id=user.id)
    session.add(tenant)
    await session.commit()
    return tenant, user


async def _install(session, tenant: Tenant, llm_id):
    encrypted = await CryptoService.encrypt_config({"app_id": "cli_a", "app_secret": "secret"}, session)
    installation = CollaborationInstallation(
        tenant_id=tenant.id,
        platform="feishu",
        external_tenant_id=f"tenant-{uuid4().hex[:8]}",
        app_id="cli_a",
        credentials_encrypted=encrypted,
        connection_mode="websocket",
        bot_external_id="ou_bot",
        default_llm_connection_id=llm_id,
        health_status="configured",
    )
    session.add(installation)
    await session.commit()
    await session.refresh(installation)
    return installation


async def _link_identity(
    session,
    tenant: Tenant,
    installation: CollaborationInstallation,
    user: User,
    external_user_id: str,
    union_id: str | None = None,
):
    identity = ExternalIdentity(
        tenant_id=tenant.id,
        platform="feishu",
        installation_id=installation.id,
        external_user_id=external_user_id,
        union_id=union_id,
        user_id=user.id,
        byaan_user_id=user.id,
        status="linked",
    )
    session.add(identity)
    await session.commit()
    await session.refresh(identity)
    return identity


async def _bind_target(
    session,
    installation: CollaborationInstallation,
    chat_id: str,
    *,
    target_type: str = "group",
    root_id: str | None = None,
    enabled: bool = True,
):
    target = CollaborationDeliveryTarget(
        installation_id=installation.id,
        target_type=target_type,
        external_target_id=chat_id,
        external_root_id=root_id,
        normalized_root_id=root_id or "__root__",
        display_name="Allowed Feishu chat",
        is_verified=enabled,
        config_json={"is_enabled": enabled, "source": "test_admin_binding"},
    )
    session.add(target)
    await session.commit()
    await session.refresh(target)
    return target


async def test_feishu_event_creates_one_notebook_and_dedupes(test_session, setup_encryption_key, monkeypatch):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    await _link_identity(test_session, tenant, installation, user, "ou_user")
    await _bind_target(test_session, installation, "oc_chat")
    tenant_id = tenant.id
    installation_id = installation.id
    notebook_id = uuid4()

    async def fake_run_agent(request, session, tenant_id, user_id=None):
        notebook = Notebook(id=notebook_id, tenant_id=tenant_id, notebook_name="Feishu analysis")
        session.add(notebook)
        await session.commit()
        from server.collaboration.channel_agent_service import AgentRunResult

        return AgentRunResult(
            run_id="run-1",
            raw_response="analysis result",
            notebook_id=notebook_id,
            dashboard_generated=False,
            query_executed=False,
        )

    sent: list[str] = []

    async def fake_start(self, conversation, response, *, reply_to_message_id=None):
        sent.append(response.summary)
        from server.collaboration.contracts import ResponseRef

        return ResponseRef(run_id="pending", conversation_id=conversation.id, platform_message_id="om_ack")

    async def fake_finish(self, response_ref, result, *, conversation):
        sent.append(result.summary)
        return response_ref

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)
    monkeypatch.setattr(FeishuChannelAdapter, "start_response", fake_start)
    monkeypatch.setattr(FeishuChannelAdapter, "finish_response", fake_finish)

    raw = {
        "header": {"event_id": "evt_once"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_user"}},
            "message": {
                "message_id": "om_msg",
                "root_id": "om_root",
                "chat_id": "oc_chat",
                "chat_type": "group",
                "content": "{\"text\":\"<at user_id=\\\"ou_bot\\\">Byaan</at> revenue?\"}",
                "mentions": [{"id": {"open_id": "ou_bot"}}],
            },
        },
    }

    first = await process_feishu_event(test_session, installation, raw)
    second = await process_feishu_event(test_session, installation, raw)

    assert first["status"] == "completed"
    assert second["status"] == "duplicate"
    assert sent == ["正在分析，我会在当前会话里回复结果。", "analysis result"]

    conversations = (await test_session.execute(select(CollaborationConversation))).scalars().all()
    assert len(conversations) == 1
    assert conversations[0].external_chat_id == "oc_chat"
    assert conversations[0].external_root_id == "om_root"
    assert conversations[0].notebook_id == notebook_id

    identities = (await test_session.execute(select(ExternalIdentity))).scalars().all()
    assert len(identities) == 1
    assert identities[0].tenant_id == tenant_id
    assert identities[0].installation_id == installation_id
    assert identities[0].platform == "feishu"
    assert identities[0].external_user_id == "ou_user"

    targets = (await test_session.execute(select(CollaborationDeliveryTarget))).scalars().all()
    assert len(targets) == 1
    assert targets[0].installation_id == installation_id
    assert targets[0].target_type == "group"
    assert targets[0].external_target_id == "oc_chat"
    assert targets[0].external_root_id is None
    assert targets[0].is_verified is True
    assert targets[0].config_json["source"] == "test_admin_binding"

    events = (await test_session.execute(select(CollaborationEventLog))).scalars().all()
    assert len(events) == 1
    assert events[0].processing_status == "completed"
    assert events[0].conversation_id == conversations[0].id
    assert events[0].notebook_id == notebook_id
    assert events[0].run_id == "run-1"

    await test_session.refresh(installation)
    subscription = installation.config_json["event_subscription"]
    assert subscription["required_event_types"] == ["im.message.receive_v1"]
    assert subscription["first_event_observed_at"] is not None
    assert subscription["last_event_observed_at"] is not None
    assert subscription["last_event_id"] == "evt_once"
    assert subscription["ready"] is True


async def test_feishu_event_persists_sender_union_id_for_identity_mapping(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    await _link_identity(test_session, tenant, installation, user, "ou_sender")
    await _bind_target(test_session, installation, "oc_chat_identity")

    async def fake_run_agent(request, session, tenant_id, user_id=None):
        from server.collaboration.channel_agent_service import AgentRunResult

        return AgentRunResult(
            run_id="run-identity",
            raw_response="analysis result",
            notebook_id=None,
            dashboard_generated=False,
            query_executed=False,
        )

    async def fake_start(self, conversation, response, *, reply_to_message_id=None):
        from server.collaboration.contracts import ResponseRef

        return ResponseRef(run_id="pending", conversation_id=conversation.id, platform_message_id="om_ack")

    async def fake_finish(self, response_ref, result, *, conversation):
        return response_ref

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)
    monkeypatch.setattr(FeishuChannelAdapter, "start_response", fake_start)
    monkeypatch.setattr(FeishuChannelAdapter, "finish_response", fake_finish)

    result = await process_feishu_event(
        test_session,
        installation,
        {
            "header": {"event_id": "evt_identity"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_sender", "user_id": "u_sender", "union_id": "on_union"}},
                "message": {
                    "message_id": "om_identity",
                    "root_id": "om_root_identity",
                    "chat_id": "oc_chat_identity",
                    "chat_type": "group",
                    "content": "{\"text\":\"<at user_id=\\\"ou_bot\\\">Byaan</at> revenue?\"}",
                    "mentions": [{"id": {"open_id": "ou_bot"}}],
                },
            },
        },
    )

    assert result["status"] == "completed"
    identity = (await test_session.execute(select(ExternalIdentity))).scalar_one()
    assert identity.external_user_id == "ou_sender"
    assert identity.union_id == "on_union"


async def test_feishu_event_passes_mapped_external_identity_user_to_agent(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, user = await _tenant(test_session)
    mapped_user = User(
        id=uuid4(),
        email=f"mapped-feishu-{uuid4().hex[:8]}@test.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    test_session.add(mapped_user)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    await _bind_target(test_session, installation, "oc_chat_mapped_identity")
    identity = ExternalIdentity(
        tenant_id=tenant.id,
        platform="feishu",
        installation_id=installation.id,
        external_user_id="ou_mapped",
        union_id="on_mapped",
        user_id=mapped_user.id,
        byaan_user_id=mapped_user.id,
        status="linked",
    )
    test_session.add(identity)
    await test_session.commit()
    captured_user_ids = []

    async def fake_run_agent(request, session, tenant_id, user_id=None):
        captured_user_ids.append(user_id)
        from server.collaboration.channel_agent_service import AgentRunResult

        return AgentRunResult(
            run_id="run-mapped-user",
            raw_response="analysis result",
            notebook_id=None,
            dashboard_generated=False,
            query_executed=False,
        )

    async def fake_start(self, conversation, response, *, reply_to_message_id=None):
        from server.collaboration.contracts import ResponseRef

        return ResponseRef(run_id="pending", conversation_id=conversation.id, platform_message_id="om_ack")

    async def fake_finish(self, response_ref, result, *, conversation):
        return response_ref

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)
    monkeypatch.setattr(FeishuChannelAdapter, "start_response", fake_start)
    monkeypatch.setattr(FeishuChannelAdapter, "finish_response", fake_finish)

    result = await process_feishu_event(
        test_session,
        installation,
        {
            "header": {"event_id": "evt_mapped_identity"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_mapped", "union_id": "on_mapped"}},
                "message": {
                    "message_id": "om_mapped_identity",
                    "root_id": "om_root_mapped_identity",
                    "chat_id": "oc_chat_mapped_identity",
                    "chat_type": "group",
                    "content": "{\"text\":\"<at user_id=\\\"ou_bot\\\">Byaan</at> revenue?\"}",
                    "mentions": [{"id": {"open_id": "ou_bot"}}],
                },
            },
        },
    )

    assert result["status"] == "completed"
    assert captured_user_ids == [mapped_user.id]
    refreshed_identity = (await test_session.execute(select(ExternalIdentity))).scalar_one()
    assert refreshed_identity.byaan_user_id == mapped_user.id
    assert refreshed_identity.union_id == "on_mapped"


async def test_feishu_unmapped_identity_requires_mapping_before_agent_run(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    await _bind_target(test_session, installation, "oc_chat_unmapped_identity")
    run_called = False
    sent: list[str] = []

    async def fake_run_agent(request, session, tenant_id, user_id=None):
        nonlocal run_called
        run_called = True
        raise AssertionError("unmapped Feishu identity must not run the agent")

    async def fake_start(self, conversation, response, *, reply_to_message_id=None):
        sent.append(response.summary)
        from server.collaboration.contracts import ResponseRef

        return ResponseRef(
            run_id=response.run_id,
            conversation_id=conversation.id,
            platform_message_id="om_identity_required",
            status=response.status.value if hasattr(response.status, "value") else str(response.status),
        )

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)
    monkeypatch.setattr(FeishuChannelAdapter, "start_response", fake_start)

    result = await process_feishu_event(
        test_session,
        installation,
        {
            "header": {"event_id": "evt_unmapped_identity"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_unmapped", "union_id": "on_unmapped"}},
                "message": {
                    "message_id": "om_unmapped_identity",
                    "root_id": "om_root_unmapped_identity",
                    "chat_id": "oc_chat_unmapped_identity",
                    "chat_type": "group",
                    "content": "{\"text\":\"<at user_id=\\\"ou_bot\\\">Byaan</at> revenue?\"}",
                    "mentions": [{"id": {"open_id": "ou_bot"}}],
                },
            },
        },
    )

    assert result["status"] == "identity_unmapped"
    assert run_called is False
    assert sent == ["无法处理此数据请求：请先联系管理员完成飞书身份与 Byaan 用户的映射。"]

    conversation = (await test_session.execute(select(CollaborationConversation))).scalar_one()
    assert conversation.notebook_id is None
    assert conversation.bot_owned is False

    identity = (await test_session.execute(select(ExternalIdentity))).scalar_one()
    assert identity.external_user_id == "ou_unmapped"
    assert identity.union_id == "on_unmapped"
    assert identity.byaan_user_id is None

    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    assert event.processing_status == "identity_unmapped"
    assert event.conversation_id == conversation.id
    assert event.notebook_id is None
    assert event.run_id is None


async def test_feishu_group_thread_without_existing_conversation_is_ignored(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    run_called = False

    async def fake_run_agent(request, session, tenant_id, user_id=None):
        nonlocal run_called
        run_called = True
        raise AssertionError("unowned group follow-up must not run the agent")

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)

    result = await process_feishu_event(
        test_session,
        installation,
        {
            "header": {"event_id": "evt_unowned_followup"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user"}},
                "message": {
                    "message_id": "om_msg",
                    "root_id": "om_root",
                    "chat_id": "oc_chat",
                    "chat_type": "group",
                    "content": "{\"text\":\"continue here\"}",
                    "mentions": [],
                },
            },
        },
    )

    assert result["status"] == "ignored"
    assert run_called is False
    assert (await test_session.execute(select(CollaborationConversation))).scalars().all() == []
    assert (await test_session.execute(select(CollaborationDeliveryTarget))).scalars().all() == []
    identities = (await test_session.execute(select(ExternalIdentity))).scalars().all()
    assert len(identities) == 1
    assert identities[0].external_user_id == "ou_user"
    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    assert event.processing_status == "ignored"


async def test_feishu_triggering_event_requires_enabled_delivery_target(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    await _link_identity(test_session, tenant, installation, user, "ou_user")
    run_called = False

    async def fake_run_agent(request, session, tenant_id, user_id=None):
        nonlocal run_called
        run_called = True
        raise AssertionError("unbound Feishu target must not run the agent")

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)

    result = await process_feishu_event(
        test_session,
        installation,
        {
            "header": {"event_id": "evt_unbound_target"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user"}},
                "message": {
                    "message_id": "om_unbound_target",
                    "root_id": "om_root_unbound_target",
                    "chat_id": "oc_unbound_target",
                    "chat_type": "group",
                    "content": "{\"text\":\"<at user_id=\\\"ou_bot\\\">Byaan</at> revenue?\"}",
                    "mentions": [{"id": {"open_id": "ou_bot"}}],
                },
            },
        },
    )

    assert result["status"] == "target_unbound"
    assert run_called is False
    assert (await test_session.execute(select(CollaborationConversation))).scalars().all() == []
    target = (await test_session.execute(select(CollaborationDeliveryTarget))).scalar_one()
    assert target.external_target_id == "oc_unbound_target"
    assert target.is_verified is False
    assert target.config_json["is_enabled"] is False
    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    assert event.processing_status == "target_unbound"


async def test_feishu_private_chat_uses_enabled_p2p_binding(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    await _link_identity(test_session, tenant, installation, user, "ou_private")
    await _bind_target(test_session, installation, "oc_private", target_type="p2p")
    captured_requests = []

    async def fake_run_agent(request, session, tenant_id, user_id=None):
        captured_requests.append((request.create_notebook, request.notebook_id, user_id))
        notebook = Notebook(id=uuid4(), tenant_id=tenant_id, notebook_name="Private Feishu analysis")
        session.add(notebook)
        await session.commit()
        from server.collaboration.channel_agent_service import AgentRunResult

        return AgentRunResult(
            run_id="run-private",
            raw_response="private result",
            notebook_id=notebook.id,
            dashboard_generated=False,
            query_executed=False,
        )

    async def fake_start(self, conversation, response, *, reply_to_message_id=None):
        from server.collaboration.contracts import ResponseRef

        return ResponseRef(run_id="pending", conversation_id=conversation.id, platform_message_id="om_private_ack")

    async def fake_finish(self, response_ref, result, *, conversation):
        return response_ref

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)
    monkeypatch.setattr(FeishuChannelAdapter, "start_response", fake_start)
    monkeypatch.setattr(FeishuChannelAdapter, "finish_response", fake_finish)

    result = await process_feishu_event(
        test_session,
        installation,
        {
            "header": {"event_id": "evt_private"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_private"}},
                "message": {
                    "message_id": "om_private",
                    "chat_id": "oc_private",
                    "chat_type": "p2p",
                    "content": "{\"text\":\"revenue?\"}",
                    "mentions": [],
                },
            },
        },
    )

    assert result["status"] == "completed"
    conversation = (await test_session.execute(select(CollaborationConversation))).scalar_one()
    assert conversation.chat_type == "p2p"
    assert conversation.external_chat_id == "oc_private"
    assert conversation.external_root_id is None
    assert conversation.notebook_id is not None
    assert captured_requests == [(True, None, user.id)]


async def test_feishu_private_chat_from_mapped_identity_requires_enabled_delivery_target(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    await _link_identity(test_session, tenant, installation, user, "ou_private_auto")
    run_called = False

    async def fake_run_agent(request, session, tenant_id, user_id=None):
        nonlocal run_called
        run_called = True
        raise AssertionError("Unbound private Feishu chats must not dispatch Agent work")

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)

    result = await process_feishu_event(
        test_session,
        installation,
        {
            "header": {"event_id": "evt_private_auto"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_private_auto"}},
                "message": {
                    "message_id": "om_private_auto",
                    "chat_id": "oc_private_auto",
                    "chat_type": "p2p",
                    "content": "{\"text\":\"revenue?\"}",
                    "mentions": [],
                },
            },
        },
    )

    assert result["status"] == "target_unbound"
    assert run_called is False
    assert (await test_session.execute(select(CollaborationConversation))).scalars().all() == []
    target = (await test_session.execute(select(CollaborationDeliveryTarget))).scalar_one()
    assert target.target_type == "p2p"
    assert target.external_target_id == "oc_private_auto"
    assert target.is_verified is False
    assert target.config_json["is_enabled"] is False
    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    assert event.processing_status == "target_unbound"


async def test_feishu_agent_failure_replies_with_sanitized_failure_and_marks_event(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    await _link_identity(test_session, tenant, installation, user, "ou_user")
    await _bind_target(test_session, installation, "oc_chat_failure")

    async def failing_run_agent(request, session, tenant_id, user_id=None):
        raise RuntimeError("agent failed app_secret=secret tenant_access_token=t1 Authorization: Bearer tok.abc")

    sent: list[tuple[str, str]] = []

    async def fake_start(self, conversation, response, *, reply_to_message_id=None):
        sent.append(("start", response.summary))
        from server.collaboration.contracts import ResponseRef

        return ResponseRef(run_id="pending", conversation_id=conversation.id, platform_message_id="om_ack")

    async def fake_finish(self, response_ref, result, *, conversation):
        sent.append(("finish", result.summary))
        response_ref.run_id = result.run_id
        response_ref.status = result.status.value if hasattr(result.status, "value") else str(result.status)
        return response_ref

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", failing_run_agent)
    monkeypatch.setattr(FeishuChannelAdapter, "start_response", fake_start)
    monkeypatch.setattr(FeishuChannelAdapter, "finish_response", fake_finish)

    result = await process_feishu_event(
        test_session,
        installation,
        {
            "header": {"event_id": "evt_agent_failure"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user"}},
                "message": {
                    "message_id": "om_failure",
                    "root_id": "om_root_failure",
                    "chat_id": "oc_chat_failure",
                    "chat_type": "group",
                    "content": "{\"text\":\"<at user_id=\\\"ou_bot\\\">Byaan</at> revenue?\"}",
                    "mentions": [{"id": {"open_id": "ou_bot"}}],
                },
            },
        },
    )

    assert result["status"] == "failed_terminal"
    assert sent[0] == ("start", "正在分析，我会在当前会话里回复结果。")
    assert sent[1][0] == "finish"
    assert "处理失败" in sent[1][1]
    rendered = str(sent)
    assert "secret" not in rendered
    assert "t1" not in rendered
    assert "tok.abc" not in rendered

    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    conversation = (await test_session.execute(select(CollaborationConversation))).scalar_one()
    assert event.processing_status == "failed_terminal"
    assert event.conversation_id == conversation.id
    assert event.run_id == "failed"
    assert "secret" not in event.error_message
    assert "t1" not in event.error_message
    assert "tok.abc" not in event.error_message


async def test_feishu_agent_timeout_replies_clearly_and_marks_event_timed_out(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    await _link_identity(test_session, tenant, installation, user, "ou_timeout")
    await _bind_target(test_session, installation, "oc_chat_timeout")
    sent: list[tuple[str, str]] = []

    async def slow_agent(request, session, tenant_id, user_id=None):
        await asyncio.sleep(1)
        raise AssertionError("timeout should cancel before agent returns")

    async def fake_start(self, conversation, response, *, reply_to_message_id=None):
        sent.append(("start", response.summary))
        from server.collaboration.contracts import ResponseRef

        return ResponseRef(run_id="pending", conversation_id=conversation.id, platform_message_id="om_timeout_ack")

    async def fake_finish(self, response_ref, result, *, conversation):
        sent.append(("finish", result.summary))
        return response_ref

    monkeypatch.setattr("server.collaboration.feishu.event_processor.FEISHU_AGENT_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", slow_agent)
    monkeypatch.setattr(FeishuChannelAdapter, "start_response", fake_start)
    monkeypatch.setattr(FeishuChannelAdapter, "finish_response", fake_finish)

    result = await process_feishu_event(
        test_session,
        installation,
        {
            "header": {"event_id": "evt_agent_timeout"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_timeout"}},
                "message": {
                    "message_id": "om_timeout",
                    "root_id": "om_root_timeout",
                    "chat_id": "oc_chat_timeout",
                    "chat_type": "group",
                    "content": "{\"text\":\"<at user_id=\\\"ou_bot\\\">Byaan</at> slow revenue?\"}",
                    "mentions": [{"id": {"open_id": "ou_bot"}}],
                },
            },
        },
    )

    assert result["status"] == "timed_out"
    assert sent[0] == ("start", "正在分析，我会在当前会话里回复结果。")
    assert sent[1][0] == "finish"
    assert "超时" in sent[1][1]
    assert "稍后重试" in sent[1][1]

    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    conversation = (await test_session.execute(select(CollaborationConversation))).scalar_one()
    assert event.processing_status == "timed_out"
    assert event.conversation_id == conversation.id
    assert event.run_id == "timed_out"
    assert event.error_message == "Agent processing timed out"


async def test_feishu_ack_delivery_failure_marks_event_terminal_without_agent_run(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    await _link_identity(test_session, tenant, installation, user, "ou_user")
    await _bind_target(test_session, installation, "oc_chat_ack_delivery_failure")
    run_called = False

    async def fake_run_agent(request, session, tenant_id, user_id=None):
        nonlocal run_called
        run_called = True
        raise AssertionError("agent must not run when Feishu ACK delivery fails")

    async def failing_start(self, conversation, response, *, reply_to_message_id=None):
        raise RuntimeError("reply failed app_secret=secret tenant_access_token=t1 Authorization: Bearer tok.abc")

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)
    monkeypatch.setattr(FeishuChannelAdapter, "start_response", failing_start)

    result = await process_feishu_event(
        test_session,
        installation,
        {
            "header": {"event_id": "evt_ack_delivery_failure"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user"}},
                "message": {
                    "message_id": "om_ack_delivery_failure",
                    "root_id": "om_root_ack_delivery_failure",
                    "chat_id": "oc_chat_ack_delivery_failure",
                    "chat_type": "group",
                    "content": "{\"text\":\"<at user_id=\\\"ou_bot\\\">Byaan</at> revenue?\"}",
                    "mentions": [{"id": {"open_id": "ou_bot"}}],
                },
            },
        },
    )

    assert result["status"] == "failed_terminal"
    assert run_called is False

    conversation = (await test_session.execute(select(CollaborationConversation))).scalar_one()
    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    assert event.processing_status == "failed_terminal"
    assert event.conversation_id == conversation.id
    assert event.run_id is None
    assert event.error_message is not None
    assert len(event.error_message) <= 500
    assert "secret" not in event.error_message
    assert "t1" not in event.error_message
    assert "tok.abc" not in event.error_message


async def test_feishu_reauth_delivery_failure_marks_installation_needs_reauth(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    installation.is_active = True
    installation.health_status = "connected"
    await test_session.commit()
    await _link_identity(test_session, tenant, installation, user, "ou_reauth")
    await _bind_target(test_session, installation, "oc_chat_reauth_delivery_failure")
    run_called = False

    async def fake_run_agent(request, session, tenant_id, user_id=None):
        nonlocal run_called
        run_called = True
        raise AssertionError("agent must not run when Feishu ACK delivery needs reauth")

    async def failing_start(self, conversation, response, *, reply_to_message_id=None):
        from server.collaboration.feishu.client import FeishuApiError

        raise FeishuApiError(
            "invalid tenant_access_token app_secret=secret tenant_access_token=t1 Authorization: Bearer tok.abc",
            code=99991663,
        )

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)
    monkeypatch.setattr(FeishuChannelAdapter, "start_response", failing_start)

    result = await process_feishu_event(
        test_session,
        installation,
        {
            "header": {"event_id": "evt_reauth_delivery_failure"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_reauth"}},
                "message": {
                    "message_id": "om_reauth_delivery_failure",
                    "root_id": "om_root_reauth_delivery_failure",
                    "chat_id": "oc_chat_reauth_delivery_failure",
                    "chat_type": "group",
                    "content": "{\"text\":\"<at user_id=\\\"ou_bot\\\">Byaan</at> revenue?\"}",
                    "mentions": [{"id": {"open_id": "ou_bot"}}],
                },
            },
        },
    )

    assert result["status"] == "failed_terminal"
    assert run_called is False

    await test_session.refresh(installation)
    assert installation.is_active is False
    assert installation.health_status == "needs_reauth"
    assert installation.health_error is not None
    assert len(installation.health_error) <= 500
    assert "secret" not in installation.health_error
    assert "t1" not in installation.health_error
    assert "tok.abc" not in installation.health_error

    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    assert event.processing_status == "failed_terminal"
    assert "secret" not in event.error_message
    assert "t1" not in event.error_message
    assert "tok.abc" not in event.error_message


async def test_feishu_owned_thread_followup_reuses_notebook(test_session, setup_encryption_key, monkeypatch):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    await _link_identity(test_session, tenant, installation, user, "ou_user")
    await _bind_target(test_session, installation, "oc_chat")
    notebook_id = uuid4()
    requests_seen: list[tuple[str | None, bool]] = []

    async def fake_run_agent(request, session, tenant_id, user_id=None):
        requests_seen.append((str(request.notebook_id) if request.notebook_id else None, request.create_notebook))
        if request.create_notebook:
            notebook = Notebook(id=notebook_id, tenant_id=tenant_id, notebook_name="Feishu analysis")
            session.add(notebook)
            await session.commit()
        from server.collaboration.channel_agent_service import AgentRunResult

        return AgentRunResult(
            run_id=f"run-{len(requests_seen)}",
            raw_response=f"analysis result {len(requests_seen)}",
            notebook_id=notebook_id if request.create_notebook else None,
            dashboard_generated=False,
            query_executed=False,
        )

    async def fake_start(self, conversation, response, *, reply_to_message_id=None):
        from server.collaboration.contracts import ResponseRef

        return ResponseRef(run_id="pending", conversation_id=conversation.id, platform_message_id=f"om_ack_{len(requests_seen)}")

    async def fake_finish(self, response_ref, result, *, conversation):
        return response_ref

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)
    monkeypatch.setattr(FeishuChannelAdapter, "start_response", fake_start)
    monkeypatch.setattr(FeishuChannelAdapter, "finish_response", fake_finish)

    first = await process_feishu_event(
        test_session,
        installation,
        {
            "header": {"event_id": "evt_initial"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user"}},
                "message": {
                    "message_id": "om_initial",
                    "root_id": "om_root",
                    "chat_id": "oc_chat",
                    "chat_type": "group",
                    "content": "{\"text\":\"<at user_id=\\\"ou_bot\\\">Byaan</at> revenue?\"}",
                    "mentions": [{"id": {"open_id": "ou_bot"}}],
                },
            },
        },
    )
    followup = await process_feishu_event(
        test_session,
        installation,
        {
            "header": {"event_id": "evt_followup"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user"}},
                "message": {
                    "message_id": "om_followup",
                    "root_id": "om_root",
                    "chat_id": "oc_chat",
                    "chat_type": "group",
                    "content": "{\"text\":\"continue with last analysis\"}",
                    "mentions": [],
                },
            },
        },
    )

    assert first["status"] == "completed"
    assert followup["status"] == "completed"
    assert requests_seen == [(None, True), (str(notebook_id), False)]
    conversations = (await test_session.execute(select(CollaborationConversation))).scalars().all()
    assert len(conversations) == 1
    assert conversations[0].notebook_id == notebook_id


async def test_feishu_same_root_events_execute_in_order_and_refresh_notebook_before_followup(
    test_session,
    test_engine,
    setup_encryption_key,
    monkeypatch,
):
    session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    await _link_identity(test_session, tenant, installation, user, "ou_ordered")
    await _bind_target(test_session, installation, "oc_ordered")
    installation_id = installation.id
    notebook_id = uuid4()
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    run_requests: list[tuple[str | None, bool]] = []
    active_runs = 0
    max_active_runs = 0

    async def fake_run_agent(request, session, tenant_id, user_id=None):
        nonlocal active_runs, max_active_runs
        active_runs += 1
        max_active_runs = max(max_active_runs, active_runs)
        run_requests.append((str(request.notebook_id) if request.notebook_id else None, request.create_notebook))
        try:
            if len(run_requests) == 1:
                first_entered.set()
                await release_first.wait()
                notebook = Notebook(id=notebook_id, tenant_id=tenant_id, notebook_name="Ordered Feishu analysis")
                session.add(notebook)
                await session.commit()
                result_notebook_id = notebook_id
            elif request.create_notebook:
                duplicate_notebook_id = uuid4()
                notebook = Notebook(
                    id=duplicate_notebook_id,
                    tenant_id=tenant_id,
                    notebook_name="Unexpected duplicate Feishu analysis",
                )
                session.add(notebook)
                await session.commit()
                result_notebook_id = duplicate_notebook_id
            else:
                result_notebook_id = None

            from server.collaboration.channel_agent_service import AgentRunResult

            return AgentRunResult(
                run_id=f"run-ordered-{len(run_requests)}",
                raw_response=f"ordered result {len(run_requests)}",
                notebook_id=result_notebook_id,
                dashboard_generated=False,
                query_executed=False,
            )
        finally:
            active_runs -= 1

    async def fake_start(self, conversation, response, *, reply_to_message_id=None):
        from server.collaboration.contracts import ResponseRef

        return ResponseRef(run_id="pending", conversation_id=conversation.id, platform_message_id=f"{reply_to_message_id}_ack")

    async def fake_finish(self, response_ref, result, *, conversation):
        return response_ref

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)
    monkeypatch.setattr(FeishuChannelAdapter, "start_response", fake_start)
    monkeypatch.setattr(FeishuChannelAdapter, "finish_response", fake_finish)

    def raw_event(event_id: str, message_id: str, text: str, *, mention: bool) -> dict:
        return {
            "header": {"event_id": event_id},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_ordered"}},
                "message": {
                    "message_id": message_id,
                    "root_id": "om_ordered_root",
                    "chat_id": "oc_ordered",
                    "chat_type": "group",
                    "content": f"{{\"text\":\"{text}\"}}",
                    "mentions": [{"id": {"open_id": "ou_bot"}}] if mention else [],
                },
            },
        }

    async def process_with_new_session(raw: dict) -> dict:
        async with session_factory() as session:
            fresh_installation = await CollaborationInstallationRepository(session).get(installation_id)
            assert fresh_installation is not None
            return await process_feishu_event(session, fresh_installation, raw)

    first_task = asyncio.create_task(
        process_with_new_session(
            raw_event(
                "evt_ordered_first",
                "om_ordered_first",
                "<at user_id=\\\"ou_bot\\\">Byaan</at> revenue?",
                mention=True,
            )
        )
    )
    await first_entered.wait()
    second_task = asyncio.create_task(
        process_with_new_session(
            raw_event(
                "evt_ordered_second",
                "om_ordered_second",
                "continue with same analysis",
                mention=False,
            )
        )
    )
    await asyncio.sleep(0.05)
    assert run_requests == [(None, True)]
    assert max_active_runs == 1

    release_first.set()
    first, second = await asyncio.gather(first_task, second_task)

    assert first["status"] == "completed"
    assert second["status"] == "completed"
    assert max_active_runs == 1
    assert run_requests == [(None, True), (str(notebook_id), False)]

    conversations = (await test_session.execute(select(CollaborationConversation))).scalars().all()
    notebooks = (await test_session.execute(select(Notebook))).scalars().all()
    assert len(conversations) == 1
    assert conversations[0].external_root_id == "om_ordered_root"
    assert conversations[0].notebook_id == notebook_id
    assert [notebook.id for notebook in notebooks] == [notebook_id]


async def test_feishu_group_top_level_mentions_without_root_do_not_share_notebook(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    await _link_identity(test_session, tenant, installation, user, "ou_user")
    await _bind_target(test_session, installation, "oc_chat")
    created_notebooks = [uuid4(), uuid4()]
    requests_seen: list[tuple[str | None, bool]] = []

    async def fake_run_agent(request, session, tenant_id, user_id=None):
        requests_seen.append((str(request.notebook_id) if request.notebook_id else None, request.create_notebook))
        notebook_id = created_notebooks[len(requests_seen) - 1]
        notebook = Notebook(id=notebook_id, tenant_id=tenant_id, notebook_name=f"Feishu analysis {len(requests_seen)}")
        session.add(notebook)
        await session.commit()
        from server.collaboration.channel_agent_service import AgentRunResult

        return AgentRunResult(
            run_id=f"run-{len(requests_seen)}",
            raw_response=f"analysis result {len(requests_seen)}",
            notebook_id=notebook_id,
            dashboard_generated=False,
            query_executed=False,
        )

    async def fake_start(self, conversation, response, *, reply_to_message_id=None):
        from server.collaboration.contracts import ResponseRef

        return ResponseRef(run_id="pending", conversation_id=conversation.id, platform_message_id=f"{reply_to_message_id}_ack")

    async def fake_finish(self, response_ref, result, *, conversation):
        return response_ref

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)
    monkeypatch.setattr(FeishuChannelAdapter, "start_response", fake_start)
    monkeypatch.setattr(FeishuChannelAdapter, "finish_response", fake_finish)

    for event_id, message_id, text in [
        ("evt_top_level_a", "om_top_level_a", "revenue by region?"),
        ("evt_top_level_b", "om_top_level_b", "profit by product?"),
    ]:
        result = await process_feishu_event(
            test_session,
            installation,
            {
                "header": {"event_id": event_id},
                "event": {
                    "sender": {"sender_id": {"open_id": "ou_user"}},
                    "message": {
                        "message_id": message_id,
                        "chat_id": "oc_chat",
                        "chat_type": "group",
                        "content": f"{{\"text\":\"<at user_id=\\\"ou_bot\\\">Byaan</at> {text}\"}}",
                        "mentions": [{"id": {"open_id": "ou_bot"}}],
                    },
                },
            },
        )
        assert result["status"] == "completed"

    assert requests_seen == [(None, True), (None, True)]
    conversations = (
        await test_session.execute(select(CollaborationConversation).order_by(CollaborationConversation.external_root_id))
    ).scalars().all()
    assert len(conversations) == 2
    assert {conversation.external_root_id for conversation in conversations} == {"om_top_level_a", "om_top_level_b"}
    assert {conversation.normalized_root_id for conversation in conversations} == {"om_top_level_a", "om_top_level_b"}
    assert {conversation.notebook_id for conversation in conversations} == set(created_notebooks)


async def test_feishu_agent_request_includes_channel_delivery_context(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
    await _link_identity(test_session, tenant, installation, user, "ou_user_context")
    await _bind_target(test_session, installation, "oc_chat_context")
    captured_messages: list[str] = []

    async def fake_run_agent(request, session, tenant_id, user_id=None):
        captured_messages.append(request.message)
        from server.collaboration.channel_agent_service import AgentRunResult

        return AgentRunResult(
            run_id="run-context",
            raw_response="analysis result",
            notebook_id=None,
            dashboard_generated=False,
            query_executed=False,
        )

    async def fake_start(self, conversation, response, *, reply_to_message_id=None):
        from server.collaboration.contracts import ResponseRef

        return ResponseRef(run_id="pending", conversation_id=conversation.id, platform_message_id="om_ack")

    async def fake_finish(self, response_ref, result, *, conversation):
        return response_ref

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)
    monkeypatch.setattr(FeishuChannelAdapter, "start_response", fake_start)
    monkeypatch.setattr(FeishuChannelAdapter, "finish_response", fake_finish)

    result = await process_feishu_event(
        test_session,
        installation,
        {
            "header": {"event_id": "evt_context"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user_context"}},
                "message": {
                    "message_id": "om_message_context",
                    "root_id": "om_root_context",
                    "chat_id": "oc_chat_context",
                    "chat_type": "group",
                    "content": "{\"text\":\"<at user_id=\\\"ou_bot\\\">Byaan</at> revenue?\"}",
                    "mentions": [{"id": {"open_id": "ou_bot"}}],
                },
            },
        },
    )

    conversation = (await test_session.execute(select(CollaborationConversation))).scalar_one()
    assert result["status"] == "completed"
    assert len(captured_messages) == 1
    prompt = captured_messages[0]
    assert f"- tenant_id: {tenant.id}" in prompt
    assert f"- installation_id: {installation.id}" in prompt
    assert f"- conversation_id: {conversation.id}" in prompt
    assert "- chat_type: topic_group" in prompt
    assert "- external_chat_id: oc_chat_context" in prompt
    assert "- external_root_id: om_root_context" in prompt
    assert "- inbound_message_id: om_message_context" in prompt
    assert "- sender_external_id: ou_user_context" in prompt
    assert "Use these IDs only for routing, audit, and follow-up continuity" in prompt


async def test_feishu_agent_runtime_rejects_default_llm_from_another_tenant(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, user = await _tenant(test_session)
    foreign_tenant, foreign_user = await _tenant(test_session)
    encrypted_foreign_llm = await CryptoService.encrypt_config({"model": "foreign-model"}, test_session)
    foreign_llm = LLMConnection(
        tenant_id=foreign_tenant.id,
        name="Foreign LLM",
        type="openai",
        config=encrypted_foreign_llm,
        created_by=foreign_user.id,
    )
    test_session.add(foreign_llm)
    await test_session.commit()
    await test_session.refresh(foreign_llm)

    installation = await _install(test_session, tenant, foreign_llm.id)
    await _link_identity(test_session, tenant, installation, user, "ou_user_foreign_llm")
    await _bind_target(test_session, installation, "oc_chat_foreign_llm")
    run_called = False
    sent: list[tuple[str, str]] = []

    async def fake_run_agent(request, session, tenant_id, user_id=None):
        nonlocal run_called
        run_called = True
        raise AssertionError("foreign-tenant LLM must not be used by Feishu agent runtime")

    async def fake_start(self, conversation, response, *, reply_to_message_id=None):
        sent.append(("start", response.summary))
        from server.collaboration.contracts import ResponseRef

        return ResponseRef(run_id="pending", conversation_id=conversation.id, platform_message_id="om_foreign_llm_ack")

    async def fake_finish(self, response_ref, result, *, conversation):
        sent.append(("finish", result.summary))
        return response_ref

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)
    monkeypatch.setattr(FeishuChannelAdapter, "start_response", fake_start)
    monkeypatch.setattr(FeishuChannelAdapter, "finish_response", fake_finish)

    result = await process_feishu_event(
        test_session,
        installation,
        {
            "header": {"event_id": "evt_foreign_llm"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_user_foreign_llm"}},
                "message": {
                    "message_id": "om_foreign_llm",
                    "root_id": "om_root_foreign_llm",
                    "chat_id": "oc_chat_foreign_llm",
                    "chat_type": "group",
                    "content": "{\"text\":\"<at user_id=\\\"ou_bot\\\">Byaan</at> revenue?\"}",
                    "mentions": [{"id": {"open_id": "ou_bot"}}],
                },
            },
        },
    )

    assert result["status"] == "failed_terminal"
    assert run_called is False
    assert sent == [
        ("start", "正在分析，我会在当前会话里回复结果。"),
        ("finish", "处理失败：当前无法完成这次分析。错误已记录，管理员可在协作集成页面查看。"),
    ]
    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    assert event.processing_status == "failed_terminal"
    assert event.run_id == "failed"
    assert "current tenant" in (event.error_message or "")


async def test_feishu_adapter_persists_response_ref(test_session, setup_encryption_key, monkeypatch):
    tenant, _ = await _tenant(test_session)
    installation = await _install(test_session, tenant, None)
    notebook = Notebook(id=uuid4(), tenant_id=tenant.id, notebook_name="Feishu adapter notebook")
    test_session.add(notebook)
    conversation = CollaborationConversation(
        installation_id=installation.id,
        external_chat_id="oc_chat",
        external_root_id="om_root",
        normalized_root_id="om_root",
        external_user_id="ou_user",
        chat_type="topic_group",
        bot_owned=True,
        notebook_id=notebook.id,
    )
    test_session.add(conversation)
    await test_session.commit()
    await test_session.refresh(conversation)
    sent: list[dict] = []

    async def fake_reply(self, *, message_id, text, request_uuid=None):
        sent.append({"message_id": message_id, "text": text, "request_uuid": request_uuid})
        return {"message_id": f"{message_id}_reply"}

    monkeypatch.setattr("server.collaboration.feishu.client.FeishuApiClient.reply_text_message", fake_reply)

    from server.collaboration.contracts import ChannelResult, ChannelResultStatus

    adapter = FeishuChannelAdapter(test_session, installation)
    ref = await adapter.start_response(
        conversation,
        ChannelResult(run_id="pending", status=ChannelResultStatus.RUNNING, summary="ack"),
        reply_to_message_id="om_input",
    )
    await adapter.finish_response(
        ref,
        ChannelResult(run_id="run-1", status=ChannelResultStatus.COMPLETED, summary="done"),
        conversation=conversation,
    )

    row = (await test_session.execute(select(CollaborationResponseRef))).scalar_one()
    assert row.run_id == "run-1"
    assert row.platform_message_id == "om_input_reply_reply"
    assert row.sequence == 1
    assert row.status == "completed"
    assert sent == [
        {"message_id": "om_input", "text": "ack", "request_uuid": f"feishu-ack-{conversation.id}-om_input"},
        {
            "message_id": "om_input_reply",
            "text": "done\n\n---\nNotebook: "
            + str(conversation.notebook_id)
            + "\nOpen in Byaan: /notebooks/"
            + str(conversation.notebook_id)
            + "\nRun: run-1",
            "request_uuid": f"feishu-final-{conversation.id}-run-1-0",
        },
    ]


async def test_feishu_adapter_retries_transient_reply_failure_before_persisting_response_ref(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, _ = await _tenant(test_session)
    installation = await _install(test_session, tenant, None)
    conversation = CollaborationConversation(
        installation_id=installation.id,
        external_chat_id="oc_retry",
        external_root_id="om_root_retry",
        normalized_root_id="om_root_retry",
        external_user_id="ou_user",
        chat_type="topic_group",
        bot_owned=True,
    )
    test_session.add(conversation)
    await test_session.commit()
    await test_session.refresh(conversation)
    attempts: list[dict] = []

    async def fake_reply(self, *, message_id, text, request_uuid=None):
        attempts.append({"message_id": message_id, "text": text, "request_uuid": request_uuid})
        if len(attempts) == 1:
            raise RuntimeError("temporary Feishu reply failure")
        return {"message_id": "om_retry_ack"}

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr("server.collaboration.feishu.client.FeishuApiClient.reply_text_message", fake_reply)
    monkeypatch.setattr("server.collaboration.feishu.adapter.asyncio.sleep", no_sleep)

    from server.collaboration.contracts import ChannelResult, ChannelResultStatus

    adapter = FeishuChannelAdapter(test_session, installation)
    ref = await adapter.start_response(
        conversation,
        ChannelResult(run_id="pending", status=ChannelResultStatus.RUNNING, summary="ack with retry"),
        reply_to_message_id="om_retry_input",
    )

    assert ref.platform_message_id == "om_retry_ack"
    assert attempts == [
        {
            "message_id": "om_retry_input",
            "text": "ack with retry",
            "request_uuid": f"feishu-ack-{conversation.id}-om_retry_input",
        },
        {
            "message_id": "om_retry_input",
            "text": "ack with retry",
            "request_uuid": f"feishu-ack-{conversation.id}-om_retry_input",
        },
    ]
    rows = (await test_session.execute(select(CollaborationResponseRef))).scalars().all()
    assert len(rows) == 1
    assert rows[0].platform_message_id == "om_retry_ack"
    assert rows[0].run_id == "pending"


async def test_feishu_adapter_does_not_retry_reauth_delivery_failure(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, _ = await _tenant(test_session)
    installation = await _install(test_session, tenant, None)
    conversation = CollaborationConversation(
        installation_id=installation.id,
        external_chat_id="oc_reauth",
        external_root_id="om_root_reauth",
        normalized_root_id="om_root_reauth",
        external_user_id="ou_user",
        chat_type="topic_group",
        bot_owned=True,
    )
    test_session.add(conversation)
    await test_session.commit()
    await test_session.refresh(conversation)
    attempts: list[dict] = []

    async def fake_reply(self, *, message_id, text, request_uuid=None):
        attempts.append({"message_id": message_id, "text": text, "request_uuid": request_uuid})
        from server.collaboration.feishu.client import FeishuApiError

        raise FeishuApiError("invalid tenant_access_token app_secret=secret", code=99991663)

    async def no_sleep(_delay):
        raise AssertionError("reauth-class delivery failures must not be retried")

    monkeypatch.setattr("server.collaboration.feishu.client.FeishuApiClient.reply_text_message", fake_reply)
    monkeypatch.setattr("server.collaboration.feishu.adapter.asyncio.sleep", no_sleep)

    from server.collaboration.contracts import ChannelResult, ChannelResultStatus
    from server.collaboration.feishu.client import FeishuApiError

    adapter = FeishuChannelAdapter(test_session, installation)
    with pytest.raises(FeishuApiError):
        await adapter.start_response(
            conversation,
            ChannelResult(run_id="pending", status=ChannelResultStatus.RUNNING, summary="ack reauth"),
            reply_to_message_id="om_reauth_input",
        )

    assert attempts == [
        {
            "message_id": "om_reauth_input",
            "text": "ack reauth",
            "request_uuid": f"feishu-ack-{conversation.id}-om_reauth_input",
        }
    ]
    assert (await test_session.execute(select(CollaborationResponseRef))).scalars().all() == []


async def test_feishu_adapter_truncates_long_final_reply_but_keeps_byaan_trace_refs(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, _ = await _tenant(test_session)
    installation = await _install(test_session, tenant, None)
    notebook = Notebook(id=uuid4(), tenant_id=tenant.id, notebook_name="Long Feishu reply notebook")
    test_session.add(notebook)
    conversation = CollaborationConversation(
        installation_id=installation.id,
        external_chat_id="oc_chat_long",
        external_root_id="om_root_long",
        normalized_root_id="om_root_long",
        external_user_id="ou_user",
        chat_type="topic_group",
        bot_owned=True,
        notebook_id=notebook.id,
    )
    test_session.add(conversation)
    await test_session.commit()
    await test_session.refresh(conversation)
    sent: list[str] = []

    async def fake_reply(self, *, message_id, text, request_uuid=None):
        sent.append(text)
        return {"message_id": f"{message_id}_reply"}

    monkeypatch.setattr("server.collaboration.feishu.client.FeishuApiClient.reply_text_message", fake_reply)

    from server.collaboration.contracts import ChannelResult, ChannelResultStatus, ResponseRef

    adapter = FeishuChannelAdapter(test_session, installation)
    ref = ResponseRef(run_id="pending", conversation_id=conversation.id, platform_message_id="om_ack")
    await adapter.finish_response(
        ref,
        ChannelResult(run_id="run-long", status=ChannelResultStatus.COMPLETED, summary="长结果" * 3000),
        conversation=conversation,
    )

    assert len(sent) == 1
    text = sent[0]
    assert len(text) <= 3800
    assert "结果较长，已截断" in text
    assert f"Open in Byaan: /notebooks/{conversation.notebook_id}" in text
    assert "Run: run-long" in text
