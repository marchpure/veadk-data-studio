from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from server.collaboration.feishu.adapter import FeishuChannelAdapter
from server.collaboration.feishu.client import FeishuApiClient
from server.collaboration.feishu.simulator import FeishuOutboundSink
from server.collaboration.models import CollaborationConversation, CollaborationInstallation, CollaborationResponseRef
from server.models.tenant import Tenant
from server.models.user import User
from server.services.crypto_service import CryptoService

pytestmark = pytest.mark.asyncio


async def _tenant(session):
    user = User(
        id=uuid4(),
        email=f"feishu-sink-{uuid4().hex[:8]}@test.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    tenant = Tenant(id=uuid4(), name="Feishu Sink Tenant", slug=f"feishu-sink-{uuid4().hex[:8]}", owner_id=user.id)
    session.add(tenant)
    await session.commit()
    return tenant, user


async def _installation(session, tenant):
    encrypted = await CryptoService.encrypt_config({"app_id": "cli_sink", "app_secret": "secret"}, session)
    installation = CollaborationInstallation(
        tenant_id=tenant.id,
        platform="feishu",
        external_tenant_id="tenant-sink",
        app_id="cli_sink",
        credentials_encrypted=encrypted,
        connection_mode="websocket",
        bot_external_id="ou_bot",
        health_status="configured",
    )
    session.add(installation)
    await session.commit()
    await session.refresh(installation)
    return installation


async def test_feishu_outbound_sink_records_redacted_ack_final_followup_and_retry_state(
    test_session,
    setup_encryption_key,
    monkeypatch,
):
    tenant, _ = await _tenant(test_session)
    installation = await _installation(test_session, tenant)
    conversation = CollaborationConversation(
        installation_id=installation.id,
        external_chat_id="oc_sink_chat",
        external_root_id="om_sink_root",
        normalized_root_id="om_sink_root",
        external_user_id="ou_sender",
        chat_type="topic_group",
        bot_owned=True,
    )
    test_session.add(conversation)
    await test_session.commit()
    await test_session.refresh(conversation)

    sink = FeishuOutboundSink(visible_chats=[{"chat_id": "oc_sink_chat", "name": "Sink Group", "chat_type": "group"}])
    sink.fail_next("reply", RuntimeError("temporary failure app_secret=secret tenant_access_token=t1"))

    async def sink_reply(_client, *, message_id, text, request_uuid=None):
        return await sink.reply_text_message(message_id=message_id, text=text, request_uuid=request_uuid)

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(FeishuApiClient, "reply_text_message", sink_reply)
    monkeypatch.setattr("server.collaboration.feishu.adapter.asyncio.sleep", no_sleep)

    from server.collaboration.contracts import ChannelResult, ChannelResultStatus

    adapter = FeishuChannelAdapter(test_session, installation)
    ack_ref = await adapter.start_response(
        conversation,
        ChannelResult(run_id="pending", status=ChannelResultStatus.RUNNING, summary="ack message"),
        reply_to_message_id="om_inbound",
    )
    ack_message_id = ack_ref.platform_message_id
    final_ref = await adapter.finish_response(
        ack_ref,
        ChannelResult(run_id="run-1", status=ChannelResultStatus.COMPLETED, summary="final answer"),
        conversation=conversation,
    )
    followup_ref = await adapter.start_response(
        conversation,
        ChannelResult(run_id="pending-followup", status=ChannelResultStatus.RUNNING, summary="follow-up ack"),
        reply_to_message_id="om_followup",
    )

    records = sink.redacted_records()
    assert [record["operation"] for record in records] == ["reply", "reply", "reply", "reply"]
    assert records[0]["status"] == "failed_retryable"
    assert records[0]["state_transitions"] == ["attempted", "failed_retryable"]
    assert records[1]["status"] == "sent"
    assert records[2]["status"] == "sent"
    assert records[3]["status"] == "sent"
    rendered = str(records)
    assert "oc_sink_chat" not in rendered
    assert "om_inbound" not in rendered
    assert "om_followup" not in rendered
    assert "ack message" not in rendered
    assert "final answer" not in rendered
    assert "secret" not in rendered
    assert "t1" not in rendered
    assert records[1]["message_ref"] == records[0]["message_ref"]
    assert ack_message_id == "om_simulated_2"
    assert final_ref.platform_message_id == "om_simulated_3"
    assert followup_ref.platform_message_id == "om_simulated_4"

    refs = (await test_session.execute(select(CollaborationResponseRef))).scalars().all()
    assert sorted(ref.run_id for ref in refs) == ["pending-followup", "run-1"]


async def test_feishu_outbound_sink_records_api_outbound_idempotency_without_raw_target(
    test_client,
    test_session,
    monkeypatch,
):
    sink = FeishuOutboundSink(visible_chats=[{"chat_id": "oc_sink_outbound", "name": "Sink Outbound", "chat_type": "group"}])

    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-sink-outbound"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": "tenant-sink-outbound",
            "external_tenant_name": "Acme",
        }

    async def sink_list(_client):
        return await sink.list_chats()

    async def sink_send(_client, *, receive_id_type, receive_id, text, root_id=None, request_uuid=None):
        return await sink.send_text_message(
            receive_id_type=receive_id_type,
            receive_id=receive_id,
            text=text,
            root_id=root_id,
            request_uuid=request_uuid,
        )

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", sink_list)
    monkeypatch.setattr(FeishuApiClient, "send_text_message", sink_send)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_sink_outbound", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]
    bound = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_sink_outbound"},
    )
    target_id = bound.json()["data"]["id"]
    payload = {
        "delivery_target_id": target_id,
        "text": "approved outbound",
        "idempotency_key": "idem-sink-outbound",
        "confirm": True,
    }

    first = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/outbound-message",
        json=payload,
    )
    duplicate = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/outbound-message",
        json={**payload, "text": "must not resend"},
    )

    assert first.status_code == 200
    assert first.json()["data"]["idempotent"] is False
    assert duplicate.status_code == 200
    assert duplicate.json()["data"]["idempotent"] is True
    assert len(sink.records) == 1
    record = sink.redacted_records()[0]
    assert record["operation"] == "send"
    assert record["status"] == "sent"
    assert record["idempotency_key_ref"] is not None
    assert record["request_uuid_ref"] is not None
    rendered = str(record)
    assert "oc_sink_outbound" not in rendered
    assert "approved outbound" not in rendered
    assert "idem-sink-outbound" not in rendered
    assert "must not resend" not in rendered


async def test_feishu_outbound_sink_records_p2p_outbound_path_without_raw_private_target(
    test_client,
    monkeypatch,
):
    sink = FeishuOutboundSink(visible_chats=[{"chat_id": "oc_sink_private", "name": "Private Sink", "chat_type": "p2p"}])

    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-sink-p2p"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": "tenant-sink-p2p",
            "external_tenant_name": "Acme",
        }

    async def sink_list(_client):
        return await sink.list_chats()

    async def sink_send(_client, *, receive_id_type, receive_id, text, root_id=None, request_uuid=None):
        return await sink.send_text_message(
            receive_id_type=receive_id_type,
            receive_id=receive_id,
            text=text,
            root_id=root_id,
            request_uuid=request_uuid,
        )

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", sink_list)
    monkeypatch.setattr(FeishuApiClient, "send_text_message", sink_send)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_sink_p2p", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]
    bound = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_sink_private", "target_type": "p2p"},
    )
    assert bound.status_code == 200
    assert bound.json()["data"]["target_type"] == "p2p"
    assert bound.json()["data"]["root_id"] is None

    sent = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/outbound-message",
        json={
            "delivery_target_id": bound.json()["data"]["id"],
            "text": "private outbound",
            "idempotency_key": "idem-sink-private",
            "confirm": True,
        },
    )

    assert sent.status_code == 200
    assert len(sink.records) == 1
    record = sink.redacted_records()[0]
    assert record["operation"] == "send"
    assert record["status"] == "sent"
    assert record["target_ref"] is not None
    assert record["root_ref"] is None
    rendered = str(record)
    assert "oc_sink_private" not in rendered
    assert "private outbound" not in rendered
    assert "idem-sink-private" not in rendered


async def test_feishu_outbound_sink_records_failed_outbound_retry_state_for_same_idempotency_key(
    test_client,
    monkeypatch,
):
    sink = FeishuOutboundSink(visible_chats=[{"chat_id": "oc_sink_retry", "name": "Sink Retry", "chat_type": "group"}])
    sink.fail_next("send", RuntimeError("temporary outbound failure app_secret=secret tenant_access_token=t1"))

    async def fake_probe(self):
        return {
            "ok": True,
            "bot": {"open_id": "ou_bot", "tenant_key": "tenant-sink-retry"},
            "bot_external_id": "ou_bot",
            "external_tenant_id": "tenant-sink-retry",
            "external_tenant_name": "Acme",
        }

    async def sink_list(_client):
        return await sink.list_chats()

    async def sink_send(_client, *, receive_id_type, receive_id, text, root_id=None, request_uuid=None):
        return await sink.send_text_message(
            receive_id_type=receive_id_type,
            receive_id=receive_id,
            text=text,
            root_id=root_id,
            request_uuid=request_uuid,
        )

    monkeypatch.setattr(FeishuApiClient, "probe", fake_probe)
    monkeypatch.setattr(FeishuApiClient, "list_chats", sink_list)
    monkeypatch.setattr(FeishuApiClient, "send_text_message", sink_send)

    create = await test_client.post(
        "/api/collaboration/installations/feishu",
        json={"app_id": "cli_sink_retry", "app_secret": "secret", "connection_mode": "websocket"},
    )
    installation_id = create.json()["data"]["id"]
    bound = await test_client.post(
        f"/api/collaboration/installations/{installation_id}/feishu/delivery-targets",
        json={"chat_id": "oc_sink_retry"},
    )
    payload = {
        "delivery_target_id": bound.json()["data"]["id"],
        "text": "retry outbound",
        "idempotency_key": "idem-sink-retry",
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

    assert first.status_code == 400
    assert retry.status_code == 200
    assert retry.json()["data"]["idempotent"] is False
    records = sink.redacted_records()
    assert [record["status"] for record in records] == ["failed_retryable", "sent"]
    assert records[0]["idempotency_key_ref"] == records[1]["idempotency_key_ref"]
    rendered = str(records)
    assert "oc_sink_retry" not in rendered
    assert "retry outbound" not in rendered
    assert "idem-sink-retry" not in rendered
    assert "secret" not in rendered
    assert "t1" not in rendered
