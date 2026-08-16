from __future__ import annotations

import time

import pytest

from server.collaboration.feishu.callback import FeishuCallbackVerificationError, FeishuCallbackVerifier
from server.collaboration.feishu.normalizer import normalize_feishu_message_event
from server.collaboration.feishu.simulator import FeishuWebhookSimulator


def test_feishu_webhook_simulator_generates_signed_encrypted_url_verification_and_rejects_replay():
    now = time.time()
    simulator = FeishuWebhookSimulator(
        verification_token="verify-token",
        encrypt_key="encrypt-key",
        now=now,
    )
    callback = simulator.url_verification(challenge="challenge-ok", event_id="evt_url", nonce="nonce-url")
    verifier = FeishuCallbackVerifier(
        verification_token="verify-token",
        encrypt_key="encrypt-key",
        now=now,
    )

    decoded = verifier.verify_and_decode(raw_body=callback.raw_body, headers=callback.headers)

    assert decoded.is_url_verification is True
    assert decoded.challenge == "challenge-ok"
    assert decoded.event_id == "evt_url"
    assert callback.redacted_refs()["event"].startswith("event:")
    assert "evt_url" not in str(callback.redacted_refs())
    with pytest.raises(FeishuCallbackVerificationError, match="Replay"):
        verifier.verify_and_decode(raw_body=callback.raw_body, headers=callback.headers)


def test_feishu_webhook_simulator_message_unknown_revoke_out_of_order_and_timeout_contracts():
    simulator = FeishuWebhookSimulator(
        verification_token="verify-token-contract",
        encrypt_key="encrypt-key-contract",
        now=1_786_000_100,
        bot_open_id="ou_bot",
    )
    verifier = FeishuCallbackVerifier(
        verification_token="verify-token-contract",
        encrypt_key="encrypt-key-contract",
        now=1_786_000_100,
    )

    message = simulator.message_event(
        event_id="evt_message",
        message_id="om_message",
        chat_id="oc_chat",
        root_id="om_root",
        sender_open_id="ou_sender",
        text="revenue?",
        nonce="nonce-message",
    )
    decoded_message = verifier.verify_and_decode(raw_body=message.raw_body, headers=message.headers)
    normalized = normalize_feishu_message_event(decoded_message.payload, installation_id="00000000-0000-0000-0000-000000000001", bot_external_id="ou_bot")

    assert decoded_message.event_type == "im.message.receive_v1"
    assert normalized.event_id == "evt_message"
    assert normalized.chat_id == "oc_chat"
    assert normalized.message_id == "om_message"
    assert normalized.root_message_id == "om_root"
    assert normalized.mentions == ["ou_bot"]
    assert normalized.text == "revenue?"

    duplicate = simulator.duplicate(message, nonce="nonce-message-duplicate")
    decoded_duplicate = verifier.verify_and_decode(raw_body=duplicate.raw_body, headers=duplicate.headers)
    assert decoded_duplicate.event_id == decoded_message.event_id
    assert duplicate.headers["X-Lark-Request-Nonce"] != message.headers["X-Lark-Request-Nonce"]

    unknown = simulator.unknown_event(event_id="evt_unknown", nonce="nonce-unknown")
    decoded_unknown = verifier.verify_and_decode(raw_body=unknown.raw_body, headers=unknown.headers)
    assert decoded_unknown.event_type == "im.chat.member.user.added_v1"
    assert decoded_unknown.event_id == "evt_unknown"

    revoked = simulator.revoked_message_event(
        event_id="evt_recalled",
        chat_id="oc_chat",
        message_id="om_recalled",
        operator_open_id="ou_operator",
        nonce="nonce-recalled",
    )
    decoded_revoked = verifier.verify_and_decode(raw_body=revoked.raw_body, headers=revoked.headers)
    assert decoded_revoked.event_type == "im.message.recalled_v1"
    assert decoded_revoked.payload["event"]["message_id"] == "om_recalled"

    out_of_order = simulator.out_of_order_thread(chat_id="oc_chat", root_id="om_root", sender_open_id="ou_sender")
    assert [callback.event_id for callback in out_of_order] == ["evt_out_of_order_2", "evt_out_of_order_1"]
    assert out_of_order[0].payload["event"]["message"]["create_time"] > out_of_order[1].payload["event"]["message"]["create_time"]

    stale = simulator.timed_out_message_event(
        event_id="evt_stale",
        message_id="om_stale",
        chat_id="oc_chat",
        sender_open_id="ou_sender",
        nonce="nonce-stale",
    )
    with pytest.raises(FeishuCallbackVerificationError, match="Stale"):
        verifier.verify_and_decode(raw_body=stale.raw_body, headers=stale.headers)
