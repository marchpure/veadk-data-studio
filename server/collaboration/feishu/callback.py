from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from server.collaboration.feishu.client import safe_feishu_error_message

MAX_CALLBACK_SKEW_SECONDS = 300


class FeishuCallbackVerificationError(ValueError):
    pass


class _CallbackReplayCache:
    def __init__(self) -> None:
        self._seen: dict[str, float] = {}
        self._lock = Lock()

    def mark_seen(self, key: str, expires_at: float) -> bool:
        now = time.time()
        with self._lock:
            expired = [item for item, expiry in self._seen.items() if expiry <= now]
            for item in expired:
                self._seen.pop(item, None)
            if key in self._seen:
                return False
            self._seen[key] = expires_at
            return True


callback_replay_cache = _CallbackReplayCache()


@dataclass(slots=True)
class FeishuCallbackPayload:
    payload: dict[str, Any]
    event_type: str | None
    event_id: str | None
    challenge: str | None
    is_url_verification: bool


class FeishuCallbackVerifier:
    def __init__(
        self,
        *,
        verification_token: str | None,
        encrypt_key: str | None,
        now: float | None = None,
    ) -> None:
        self.verification_token = (verification_token or "").strip()
        self.encrypt_key = (encrypt_key or "").strip()
        self.now = time.time() if now is None else now

    def verify_and_decode(self, *, raw_body: bytes, headers: Mapping[str, str]) -> FeishuCallbackPayload:
        if not self.verification_token or not self.encrypt_key:
            raise FeishuCallbackVerificationError("Feishu callback token and encrypt key are required")
        self._verify_signature(raw_body=raw_body, headers=headers)
        envelope = self._json(raw_body)
        encrypted = envelope.get("encrypt")
        if not isinstance(encrypted, str) or not encrypted:
            raise FeishuCallbackVerificationError("Feishu callback must be encrypted")
        payload = self._json(self._decrypt(encrypted).encode("utf-8"))
        token = payload.get("token") or payload.get("header", {}).get("token")
        if token != self.verification_token:
            raise FeishuCallbackVerificationError("Feishu callback token mismatch")

        event_type = payload.get("type") or payload.get("header", {}).get("event_type")
        event_id = payload.get("uuid") or payload.get("event_id") or payload.get("header", {}).get("event_id")
        challenge = payload.get("challenge")
        return FeishuCallbackPayload(
            payload=payload,
            event_type=str(event_type) if event_type else None,
            event_id=str(event_id) if event_id else None,
            challenge=str(challenge) if challenge else None,
            is_url_verification=event_type == "url_verification",
        )

    def _verify_signature(self, *, raw_body: bytes, headers: Mapping[str, str]) -> None:
        timestamp = _header(headers, "X-Lark-Request-Timestamp")
        nonce = _header(headers, "X-Lark-Request-Nonce")
        signature = _header(headers, "X-Lark-Signature")
        if not timestamp or not nonce or not signature:
            raise FeishuCallbackVerificationError("Missing Feishu callback signature headers")
        try:
            timestamp_int = int(timestamp)
        except ValueError:
            raise FeishuCallbackVerificationError("Invalid Feishu callback timestamp")
        if abs(self.now - timestamp_int) > MAX_CALLBACK_SKEW_SECONDS:
            raise FeishuCallbackVerificationError("Stale Feishu callback timestamp")
        signed = (timestamp + nonce + self.encrypt_key).encode("utf-8") + raw_body
        expected = hashlib.sha256(signed).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise FeishuCallbackVerificationError("Feishu callback signature verification failed")
        replay_key = hashlib.sha256(f"{timestamp}:{nonce}:{signature}".encode()).hexdigest()
        if not callback_replay_cache.mark_seen(
            replay_key,
            expires_at=timestamp_int + MAX_CALLBACK_SKEW_SECONDS,
        ):
            raise FeishuCallbackVerificationError("Replay Feishu callback signature")

    def _decrypt(self, encrypted: str) -> str:
        try:
            encrypted_bytes = base64.b64decode(encrypted)
        except Exception as exc:
            raise FeishuCallbackVerificationError("Invalid Feishu callback encryption payload") from exc
        if len(encrypted_bytes) <= 16 or len(encrypted_bytes) % 16 != 0:
            raise FeishuCallbackVerificationError("Invalid Feishu callback encrypted block")
        key = hashlib.sha256(self.encrypt_key.encode("utf-8")).digest()
        iv = encrypted_bytes[:16]
        ciphertext = encrypted_bytes[16:]
        decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        pad_length = padded[-1]
        if pad_length < 1 or pad_length > 16:
            raise FeishuCallbackVerificationError("Invalid Feishu callback padding")
        return padded[:-pad_length].decode("utf-8")

    @staticmethod
    def _json(raw: bytes) -> dict[str, Any]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FeishuCallbackVerificationError("Feishu callback body was not JSON") from exc
        if not isinstance(data, dict):
            raise FeishuCallbackVerificationError("Feishu callback body must be a JSON object")
        return data


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def safe_callback_error(error: Exception) -> str:
    return safe_feishu_error_message(error)
