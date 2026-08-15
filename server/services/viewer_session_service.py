from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from uuid import UUID

from server.utils.config_loader import get_auth_secret

VIEWER_SESSION_MINUTES = int(os.getenv("VIEWER_SESSION_MINUTES", "15"))


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


class ViewerSessionService:
    @staticmethod
    def generate_token(user_id: UUID, tenant_id: UUID) -> str:
        exp = int(time.time()) + (VIEWER_SESSION_MINUTES * 60)
        payload = {
            "uid": str(user_id),
            "tid": str(tenant_id),
            "exp": exp,
        }
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        payload_b64 = _b64url_encode(payload_bytes)
        secret = get_auth_secret().encode()
        signature = hmac.new(secret, payload_b64.encode(), hashlib.sha256).digest()
        return f"{payload_b64}.{_b64url_encode(signature)}"

    @staticmethod
    def verify(token: str) -> dict[str, str] | None:
        try:
            payload_b64, signature_b64 = token.split(".", 1)
        except ValueError:
            return None

        try:
            secret = get_auth_secret().encode()
            expected_sig = hmac.new(secret, payload_b64.encode(), hashlib.sha256).digest()
            if not hmac.compare_digest(_b64url_encode(expected_sig), signature_b64):
                return None

            payload = json.loads(_b64url_decode(payload_b64))
            if int(payload.get("exp", 0)) <= int(time.time()):
                return None

            return payload
        except Exception:
            return None
