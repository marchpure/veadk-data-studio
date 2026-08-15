from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from server.collaboration.feishu.adapter import FeishuChannelAdapter
from server.collaboration.feishu.event_processor import process_feishu_event
from server.collaboration.models import (
    CollaborationConversation,
    CollaborationEventLog,
    CollaborationInstallation,
    CollaborationResponseRef,
)
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


async def test_feishu_event_creates_one_notebook_and_dedupes(test_session, setup_encryption_key, monkeypatch):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
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

    events = (await test_session.execute(select(CollaborationEventLog))).scalars().all()
    assert len(events) == 1
    assert events[0].processing_status == "completed"


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
    event = (await test_session.execute(select(CollaborationEventLog))).scalar_one()
    assert event.processing_status == "ignored"


async def test_feishu_owned_thread_followup_reuses_notebook(test_session, setup_encryption_key, monkeypatch):
    tenant, user = await _tenant(test_session)
    encrypted_llm = await CryptoService.encrypt_config({"model": "fake-model"}, test_session)
    llm = LLMConnection(tenant_id=tenant.id, name="LLM", type="openai", config=encrypted_llm, created_by=user.id)
    test_session.add(llm)
    await test_session.commit()
    await test_session.refresh(llm)
    installation = await _install(test_session, tenant, llm.id)
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


async def test_feishu_adapter_persists_response_ref(test_session, setup_encryption_key, monkeypatch):
    tenant, _ = await _tenant(test_session)
    installation = await _install(test_session, tenant, None)
    conversation = CollaborationConversation(
        installation_id=installation.id,
        external_chat_id="oc_chat",
        external_root_id="om_root",
        normalized_root_id="om_root",
        external_user_id="ou_user",
        chat_type="topic_group",
        bot_owned=True,
    )
    test_session.add(conversation)
    await test_session.commit()
    await test_session.refresh(conversation)
    sent: list[dict] = []

    async def fake_reply(self, *, message_id, text):
        sent.append({"message_id": message_id, "text": text})
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
        {"message_id": "om_input", "text": "ack"},
        {"message_id": "om_input_reply", "text": "done"},
    ]
