from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from server.collaboration.feishu.callback import MAX_CALLBACK_SKEW_SECONDS
from server.collaboration.feishu.client import safe_feishu_error_message


def redacted_ref(kind: str, value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{kind}:{digest}"


@dataclass(slots=True, frozen=True)
class SimulatedFeishuCallback:
    raw_body: bytes
    headers: dict[str, str]
    payload: dict[str, Any]
    event_type: str | None
    event_id: str | None

    def redacted_refs(self) -> dict[str, str | None]:
        event = self.payload.get("event") if isinstance(self.payload.get("event"), dict) else {}
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
        sender_id = sender.get("sender_id") if isinstance(sender.get("sender_id"), dict) else {}
        operator_id = event.get("operator_id") if isinstance(event.get("operator_id"), dict) else {}
        return {
            "event": redacted_ref("event", self.event_id),
            "message": redacted_ref("message", message.get("message_id") or event.get("message_id")),
            "chat": redacted_ref("chat", message.get("chat_id") or event.get("chat_id")),
            "sender": redacted_ref("user", sender_id.get("open_id") or operator_id.get("open_id")),
            "signature": redacted_ref("signature", self.headers.get("X-Lark-Signature")),
        }


class FeishuWebhookSimulator:
    """Local Feishu callback generator for contract tests.

    The simulator creates the same signed + encrypted callback envelope that the
    production verifier accepts. It intentionally exposes only redacted refs for
    evidence/reporting; tests can still pass raw ids into payload builders.
    """

    def __init__(
        self,
        *,
        verification_token: str,
        encrypt_key: str,
        now: float | None = None,
        bot_open_id: str = "ou_bot",
    ) -> None:
        self.verification_token = verification_token
        self.encrypt_key = encrypt_key
        self.now = time.time() if now is None else now
        self.bot_open_id = bot_open_id

    def signed_callback(
        self,
        payload: dict[str, Any],
        *,
        nonce: str = "nonce-1",
        timestamp: int | None = None,
    ) -> SimulatedFeishuCallback:
        timestamp_text = str(int(self.now if timestamp is None else timestamp))
        raw_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        pad_len = 16 - (len(raw_payload) % 16)
        padded = raw_payload + bytes([pad_len]) * pad_len
        iv = b"0123456789abcdef"
        key = hashlib.sha256(self.encrypt_key.encode("utf-8")).digest()
        encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
        encrypted = iv + encryptor.update(padded) + encryptor.finalize()
        body = json.dumps(
            {"encrypt": base64.b64encode(encrypted).decode("utf-8")},
            separators=(",", ":"),
        ).encode("utf-8")
        signature = hashlib.sha256((timestamp_text + nonce + self.encrypt_key).encode("utf-8") + body).hexdigest()
        return SimulatedFeishuCallback(
            raw_body=body,
            headers={
                "X-Lark-Request-Timestamp": timestamp_text,
                "X-Lark-Request-Nonce": nonce,
                "X-Lark-Signature": signature,
                "Content-Type": "application/json",
            },
            payload=payload,
            event_type=_event_type(payload),
            event_id=_event_id(payload),
        )

    def url_verification(
        self,
        *,
        challenge: str = "challenge-ok",
        event_id: str = "evt_url_verification",
        nonce: str = "nonce-url-verification",
    ) -> SimulatedFeishuCallback:
        return self.signed_callback(
            {
                "type": "url_verification",
                "token": self.verification_token,
                "challenge": challenge,
                "uuid": event_id,
            },
            nonce=nonce,
        )

    def message_event(
        self,
        *,
        event_id: str,
        message_id: str,
        chat_id: str,
        sender_open_id: str,
        text: str = "hello",
        root_id: str | None = None,
        parent_id: str | None = None,
        chat_type: str = "group",
        mention_bot: bool = True,
        nonce: str | None = None,
        create_time_ms: int | None = None,
        timestamp: int | None = None,
    ) -> SimulatedFeishuCallback:
        mentions = []
        rendered_text = text
        if mention_bot and chat_type != "p2p":
            mentions.append({"id": {"open_id": self.bot_open_id}})
            rendered_text = f'<at user_id="{self.bot_open_id}">Byaan</at> {text}'
        message: dict[str, Any] = {
            "message_id": message_id,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "content": json.dumps({"text": rendered_text}, ensure_ascii=False),
            "mentions": mentions,
            "create_time": str(create_time_ms if create_time_ms is not None else int(self.now * 1000)),
        }
        if root_id:
            message["root_id"] = root_id
        if parent_id:
            message["parent_id"] = parent_id
        return self.signed_callback(
            {
                "header": {
                    "event_id": event_id,
                    "event_type": "im.message.receive_v1",
                    "token": self.verification_token,
                },
                "token": self.verification_token,
                "event": {
                    "sender": {"sender_id": {"open_id": sender_open_id}},
                    "message": message,
                },
            },
            nonce=nonce or f"nonce-{event_id}",
            timestamp=timestamp,
        )

    def duplicate(self, callback: SimulatedFeishuCallback, *, nonce: str) -> SimulatedFeishuCallback:
        return self.signed_callback(callback.payload, nonce=nonce)

    def out_of_order_thread(
        self,
        *,
        chat_id: str,
        root_id: str,
        sender_open_id: str,
    ) -> list[SimulatedFeishuCallback]:
        first_time = int(self.now * 1000)
        return [
            self.message_event(
                event_id="evt_out_of_order_2",
                message_id="om_out_of_order_2",
                chat_id=chat_id,
                sender_open_id=sender_open_id,
                root_id=root_id,
                text="second message arrives first",
                mention_bot=False,
                nonce="nonce-out-of-order-2",
                create_time_ms=first_time + 2000,
            ),
            self.message_event(
                event_id="evt_out_of_order_1",
                message_id="om_out_of_order_1",
                chat_id=chat_id,
                sender_open_id=sender_open_id,
                root_id=root_id,
                text="first message arrives second",
                mention_bot=True,
                nonce="nonce-out-of-order-1",
                create_time_ms=first_time + 1000,
            ),
        ]

    def revoked_message_event(
        self,
        *,
        event_id: str,
        chat_id: str,
        message_id: str,
        operator_open_id: str,
        nonce: str = "nonce-revoked",
    ) -> SimulatedFeishuCallback:
        return self.signed_callback(
            {
                "header": {
                    "event_id": event_id,
                    "event_type": "im.message.recalled_v1",
                    "token": self.verification_token,
                },
                "token": self.verification_token,
                "event": {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "operator_id": {"open_id": operator_open_id},
                },
            },
            nonce=nonce,
        )

    def unknown_event(
        self,
        *,
        event_id: str,
        event_type: str = "im.chat.member.user.added_v1",
        chat_id: str = "oc_unknown",
        operator_open_id: str = "ou_operator",
        nonce: str = "nonce-unknown",
    ) -> SimulatedFeishuCallback:
        return self.signed_callback(
            {
                "header": {"event_id": event_id, "event_type": event_type, "token": self.verification_token},
                "token": self.verification_token,
                "event": {"chat_id": chat_id, "operator_id": {"open_id": operator_open_id}},
            },
            nonce=nonce,
        )

    def timed_out_message_event(self, **kwargs: Any) -> SimulatedFeishuCallback:
        stale_timestamp = int(self.now) - MAX_CALLBACK_SKEW_SECONDS - 1
        return self.message_event(timestamp=stale_timestamp, **kwargs)


@dataclass(slots=True)
class SimulatedDeliveryRecord:
    operation: str
    target_ref: str | None
    message_ref: str | None
    root_ref: str | None
    text_ref: str | None
    request_uuid_ref: str | None
    idempotency_key_ref: str | None
    status: str = "attempted"
    platform_message_ref: str | None = None
    state_transitions: list[str] = field(default_factory=lambda: ["attempted"])
    error: str | None = None

    def mark_failed(self, error: Exception) -> None:
        self.status = "failed_retryable"
        self.error = safe_feishu_error_message(error)
        self.state_transitions.append(self.status)

    def mark_sent(self, platform_message_id: str) -> None:
        self.status = "sent"
        self.platform_message_ref = redacted_ref("message", platform_message_id)
        self.state_transitions.append(self.status)

    def as_redacted(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "target_ref": self.target_ref,
            "message_ref": self.message_ref,
            "root_ref": self.root_ref,
            "text_ref": self.text_ref,
            "request_uuid_ref": self.request_uuid_ref,
            "idempotency_key_ref": self.idempotency_key_ref,
            "status": self.status,
            "platform_message_ref": self.platform_message_ref,
            "state_transitions": list(self.state_transitions),
            "error": self.error,
        }


class FeishuOutboundSink:
    """In-memory Feishu transport for local contract tests.

    It records redacted delivery refs and state transitions without contacting
    Feishu. Tests can inject failures to verify retry/idempotency behavior.
    """

    def __init__(self, *, visible_chats: list[dict[str, Any]] | None = None) -> None:
        self.visible_chats = list(visible_chats or [])
        self.records: list[SimulatedDeliveryRecord] = []
        self._failures: dict[str, list[Exception]] = {"send": [], "reply": []}

    def fail_next(self, operation: str, error: Exception) -> None:
        if operation not in self._failures:
            raise ValueError(f"Unsupported Feishu sink operation: {operation}")
        self._failures[operation].append(error)

    async def list_chats(self) -> list[dict[str, Any]]:
        return [dict(chat) for chat in self.visible_chats]

    async def send_text_message(
        self,
        *,
        receive_id_type: str,
        receive_id: str,
        text: str,
        root_id: str | None = None,
        request_uuid: str | None = None,
    ) -> dict[str, Any]:
        del receive_id_type
        record = SimulatedDeliveryRecord(
            operation="send",
            target_ref=redacted_ref("chat", receive_id),
            message_ref=None,
            root_ref=redacted_ref("root", root_id),
            text_ref=redacted_ref("text", text),
            request_uuid_ref=redacted_ref("request_uuid", request_uuid),
            idempotency_key_ref=_idempotency_ref_from_request_uuid(request_uuid),
        )
        return await self._deliver("send", record)

    async def reply_text_message(
        self,
        *,
        message_id: str,
        text: str,
        request_uuid: str | None = None,
    ) -> dict[str, Any]:
        record = SimulatedDeliveryRecord(
            operation="reply",
            target_ref=None,
            message_ref=redacted_ref("message", message_id),
            root_ref=None,
            text_ref=redacted_ref("text", text),
            request_uuid_ref=redacted_ref("request_uuid", request_uuid),
            idempotency_key_ref=_idempotency_ref_from_request_uuid(request_uuid),
        )
        return await self._deliver("reply", record)

    async def _deliver(self, operation: str, record: SimulatedDeliveryRecord) -> dict[str, Any]:
        self.records.append(record)
        failures = self._failures[operation]
        if failures:
            error = failures.pop(0)
            record.mark_failed(error)
            raise error
        platform_message_id = f"om_simulated_{len(self.records)}"
        record.mark_sent(platform_message_id)
        return {"message_id": platform_message_id}

    def redacted_records(self) -> list[dict[str, Any]]:
        return [record.as_redacted() for record in self.records]


def _event_type(payload: dict[str, Any]) -> str | None:
    value = payload.get("type") or (payload.get("header") or {}).get("event_type")
    return str(value) if value else None


def _event_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("uuid") or payload.get("event_id") or (payload.get("header") or {}).get("event_id")
    return str(value) if value else None


def _idempotency_ref_from_request_uuid(request_uuid: str | None) -> str | None:
    if not request_uuid:
        return None
    if request_uuid.startswith("feishu-outbound-"):
        return redacted_ref("idempotency", request_uuid.removeprefix("feishu-outbound-"))
    return None
