#!/usr/bin/env python
"""Feishu Collaboration real-E2E evidence collector.

This script is intentionally conservative:

- default mode is read-only and safe to run against a Team database;
- it never prints app secrets or tenant tokens;
- it only sends a Feishu message when both --send-test-message and --chat-id
  are provided explicitly.

Typical usage after the 8080 Team deployment is running:

    DATABASE_URL=... APP_SECRET=... uv run python scripts/feishu_collaboration_e2e.py --list-chats

    DATABASE_URL=... APP_SECRET=... uv run python scripts/feishu_collaboration_e2e.py \
      --chat-id oc_xxx --send-test-message

    DATABASE_URL=... APP_SECRET=... uv run python scripts/feishu_collaboration_e2e.py \
      --wait-new-event --timeout 180

For the final human-driven journey, run --snapshot before asking in Feishu,
ask the test group/DM, then run --wait-new-event to collect event/conversation/
notebook/response-ref evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.collaboration.feishu.client import FeishuApiClient, safe_feishu_error_message  # noqa: E402
from server.collaboration.models import (  # noqa: E402
    CollaborationConversation,
    CollaborationDeliveryTarget,
    CollaborationEventLog,
    CollaborationInstallation,
    CollaborationLease,
    CollaborationResponseRef,
    ExternalIdentity,
)
from server.db.session import AsyncSessionFactory  # noqa: E402
from server.models.notebooks import Notebook  # noqa: E402
from server.models.settings import Setting  # noqa: E402

ENCRYPTION_KEY_SETTING = "app_encryption_key"


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _short(value: str | None, *, keep: int = 10) -> str | None:
    if not value:
        return value
    if len(value) <= keep + 4:
        return value
    return f"{value[:keep]}…{value[-4:]}"


def _hash_ref(value: str | None, *, prefix: str) -> str | None:
    if not value:
        return None
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def _safe_callback_status(config: dict[str, Any] | None) -> dict[str, Any]:
    callback = dict((config or {}).get("callback") or {})
    allowed_keys = {
        "url_verification",
        "last_url_verification_at",
        "verification_token_configured",
        "encrypt_key_configured",
        "event_ingress",
    }
    return {key: callback[key] for key in allowed_keys if key in callback}


def _safe_event_subscription(config: dict[str, Any] | None) -> dict[str, Any]:
    subscription = dict((config or {}).get("event_subscription") or {})
    if subscription.get("last_event_id"):
        subscription["last_event_ref"] = _hash_ref(str(subscription.pop("last_event_id")), prefix="evt")
    return subscription


async def _decrypt_config_readonly(b64_blob: str, tenant_id: UUID) -> dict[str, Any]:
    """Decrypt sensitive config without importing CryptoService or mutating settings.

    CryptoService imports SettingsService, which imports the repositories package
    and can create a circular import in standalone scripts. This script only needs
    to read existing Feishu credentials for evidence collection, so it implements
    the same key selection rules without creating a missing local key.
    """

    env_key = os.getenv("ENCRYPTION_KEY")
    if env_key:
        key = bytes.fromhex(env_key)
    elif os.getenv("APP_SECRET"):
        key = hashlib.sha256(os.environ["APP_SECRET"].encode()).digest()
    else:
        async with AsyncSessionFactory() as session:
            setting = (
                await session.execute(
                    select(Setting)
                    .where(Setting.tenant_id == tenant_id)
                    .where(Setting.user_id.is_(None))
                    .where(Setting.setting_key == ENCRYPTION_KEY_SETTING)
                )
            ).scalars().first()
            if not setting:
                raise RuntimeError(
                    "No APP_SECRET/ENCRYPTION_KEY env and no local app_encryption_key setting found. "
                    "Refusing to create keys from an evidence script."
                )
            key = base64.b64decode(setting.setting_value)

    data = base64.b64decode(b64_blob)
    nonce, ciphertext = data[:12], data[12:]
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    return json.loads(plaintext.decode("utf-8"))


@dataclass(slots=True)
class EventCursor:
    last_event_created_at: datetime | None
    last_event_id: str | None


class FeishuCollaborationEvidence:
    def __init__(self, installation_id: UUID | None = None) -> None:
        self.installation_id = installation_id

    async def _installation(self) -> CollaborationInstallation:
        async with AsyncSessionFactory() as session:
            stmt = select(CollaborationInstallation).where(CollaborationInstallation.platform == "feishu")
            if self.installation_id:
                stmt = stmt.where(CollaborationInstallation.id == self.installation_id)
            stmt = stmt.order_by(CollaborationInstallation.updated_at.desc())
            installation = (await session.execute(stmt)).scalars().first()
            if not installation:
                raise RuntimeError("No Feishu collaboration installation found in the configured database.")
            self.installation_id = installation.id
            return installation

    async def _client(self) -> FeishuApiClient:
        installation_id = self.installation_id or (await self._installation()).id
        async with AsyncSessionFactory() as session:
            installation = await session.get(CollaborationInstallation, installation_id)
            if not installation:
                raise RuntimeError("Feishu installation disappeared while loading credentials.")
            credentials = await _decrypt_config_readonly(installation.credentials_encrypted, installation.tenant_id)
        return FeishuApiClient(app_id=credentials["app_id"], app_secret=credentials["app_secret"])

    async def snapshot(self) -> dict[str, Any]:
        installation = await self._installation()
        async with AsyncSessionFactory() as session:
            lease = await session.get(CollaborationLease, installation.id)
            events = (
                await session.execute(
                    select(CollaborationEventLog)
                    .where(CollaborationEventLog.installation_id == installation.id)
                    .order_by(CollaborationEventLog.created_at.desc(), CollaborationEventLog.id.desc())
                    .limit(10)
                )
            ).scalars().all()
            conversations = (
                await session.execute(
                    select(CollaborationConversation)
                    .where(CollaborationConversation.installation_id == installation.id)
                    .order_by(CollaborationConversation.last_activity_at.desc())
                    .limit(10)
                )
            ).scalars().all()
            notebook_count = (
                await session.execute(
                    select(func.count(Notebook.id)).where(Notebook.tenant_id == installation.tenant_id)
                )
            ).scalar_one()
            response_refs = (
                await session.execute(
                    select(CollaborationResponseRef)
                    .join(CollaborationConversation, CollaborationResponseRef.conversation_id == CollaborationConversation.id)
                    .where(CollaborationConversation.installation_id == installation.id)
                    .order_by(CollaborationResponseRef.updated_at.desc())
                    .limit(10)
                )
            ).scalars().all()
            external_identities = (
                await session.execute(
                    select(ExternalIdentity)
                    .where(ExternalIdentity.installation_id == installation.id)
                    .order_by(ExternalIdentity.last_seen_at.desc(), ExternalIdentity.id.desc())
                    .limit(10)
                )
            ).scalars().all()
            delivery_targets = (
                await session.execute(
                    select(CollaborationDeliveryTarget)
                    .where(CollaborationDeliveryTarget.installation_id == installation.id)
                    .order_by(CollaborationDeliveryTarget.updated_at.desc(), CollaborationDeliveryTarget.id.desc())
                    .limit(10)
                )
            ).scalars().all()

        return {
            "installation": {
                "id_ref": _hash_ref(str(installation.id), prefix="installation"),
                "tenant_ref": _hash_ref(str(installation.tenant_id), prefix="tenant"),
                "platform": installation.platform,
                "external_tenant_ref": _hash_ref(installation.external_tenant_id, prefix="external_tenant"),
                "app_ref": _hash_ref(installation.app_id, prefix="app"),
                "connection_mode": installation.connection_mode,
                "is_active": installation.is_active,
                "health_status": installation.health_status,
                "health_error": safe_feishu_error_message(installation.health_error) if installation.health_error else None,
                "bot_ref": _hash_ref(installation.bot_external_id, prefix="bot"),
                "default_llm_connection_id": str(installation.default_llm_connection_id)
                if installation.default_llm_connection_id
                else None,
                "tenant_token_expires_at": (installation.config_json or {}).get("tenant_token_expires_at"),
                "callback": _safe_callback_status(installation.config_json),
                "event_subscription": _safe_event_subscription(installation.config_json),
                "last_connected_at": _dt(installation.last_connected_at),
                "last_event_at": _dt(installation.last_event_at),
                "reconnect_count": installation.reconnect_count,
            },
            "lease": {
                "owner_id": lease.owner_id if lease else None,
                "expires_at": _dt(lease.expires_at) if lease else None,
                "heartbeat_at": _dt(lease.heartbeat_at) if lease else None,
            },
            "recent_events": [
                {
                    "event_ref": _hash_ref(event.external_event_id, prefix="evt"),
                    "event_type": event.event_type,
                    "chat_ref": _hash_ref(event.external_chat_id, prefix="chat"),
                    "sender_ref": _hash_ref(event.external_user_id, prefix="user"),
                    "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                    "notebook_id": str(event.notebook_id) if event.notebook_id else None,
                    "run_id": event.run_id,
                    "status": event.processing_status,
                    "attempt_count": event.attempt_count,
                    "error": safe_feishu_error_message(event.error_message) if event.error_message else None,
                    "created_at": _dt(event.created_at),
                    "updated_at": _dt(event.updated_at),
                }
                for event in events
            ],
            "recent_conversations": [
                {
                    "id": str(conversation.id),
                    "chat_ref": _hash_ref(conversation.external_chat_id, prefix="chat"),
                    "root_ref": _hash_ref(conversation.external_root_id, prefix="root"),
                    "chat_type": conversation.chat_type,
                    "notebook_id": str(conversation.notebook_id) if conversation.notebook_id else None,
                    "bot_owned": conversation.bot_owned,
                    "last_activity_at": _dt(conversation.last_activity_at),
                }
                for conversation in conversations
            ],
            "recent_response_refs": [
                {
                    "run_id": response_ref.run_id,
                    "conversation_id": str(response_ref.conversation_id),
                    "platform_message_ref": _hash_ref(response_ref.platform_message_id, prefix="message"),
                    "status": response_ref.status,
                    "sequence": response_ref.sequence,
                    "updated_at": _dt(response_ref.updated_at),
                }
                for response_ref in response_refs
            ],
            "recent_external_identities": [
                {
                    "platform": identity.platform,
                    "external_user_ref": _hash_ref(identity.external_user_id, prefix="user"),
                    "union_ref": _hash_ref(identity.union_id, prefix="union"),
                    "status": identity.status,
                    "user_id": str(identity.user_id) if identity.user_id else None,
                    "byaan_user_id": str(identity.byaan_user_id) if identity.byaan_user_id else None,
                    "last_seen_at": _dt(identity.last_seen_at),
                }
                for identity in external_identities
            ],
            "recent_delivery_targets": [
                {
                    "target_type": target.target_type,
                    "target_ref": _hash_ref(target.external_target_id, prefix="target"),
                    "root_ref": _hash_ref(target.external_root_id, prefix="root"),
                    "is_verified": target.is_verified,
                    "updated_at": _dt(target.updated_at),
                }
                for target in delivery_targets
            ],
            "tenant_notebook_count": notebook_count,
        }

    async def cursor(self) -> EventCursor:
        installation = await self._installation()
        async with AsyncSessionFactory() as session:
            event = (
                await session.execute(
                    select(CollaborationEventLog)
                    .where(CollaborationEventLog.installation_id == installation.id)
                    .order_by(CollaborationEventLog.created_at.desc(), CollaborationEventLog.id.desc())
                    .limit(1)
                )
            ).scalars().first()
        return EventCursor(
            last_event_created_at=event.created_at if event else None,
            last_event_id=event.external_event_id if event else None,
        )

    async def wait_new_event(self, cursor: EventCursor, *, timeout_seconds: int) -> dict[str, Any]:
        start = time.monotonic()
        while time.monotonic() - start < timeout_seconds:
            installation = await self._installation()
            async with AsyncSessionFactory() as session:
                stmt = (
                    select(CollaborationEventLog)
                    .where(CollaborationEventLog.installation_id == installation.id)
                    .order_by(CollaborationEventLog.created_at.desc(), CollaborationEventLog.id.desc())
                    .limit(1)
                )
                latest = (await session.execute(stmt)).scalars().first()
                if latest and (
                    latest.external_event_id != cursor.last_event_id
                    or (cursor.last_event_created_at and latest.created_at > cursor.last_event_created_at)
                ):
                    return await self.snapshot()
            await asyncio.sleep(2)
        raise TimeoutError(f"No new Feishu event observed within {timeout_seconds}s.")

    async def list_chats(self) -> list[dict[str, Any]]:
        client = await self._client()
        chats = await client.list_chats(max_items=200)
        return [
            {
                "chat_ref": _hash_ref(chat.get("chat_id"), prefix="chat"),
                "chat_type": chat.get("chat_type"),
            }
            for chat in chats
        ]

    async def send_test_message(self, chat_id: str, text: str, root_id: str | None) -> dict[str, Any]:
        client = await self._client()
        result = await client.send_text_message(
            receive_id_type="chat_id",
            receive_id=chat_id,
            text=text,
            root_id=root_id,
        )
        return {
            "sent": True,
            "message_ref": _hash_ref(
                result.get("message_id")
                or result.get("message", {}).get("message_id")
                or result.get("data", {}).get("message_id"),
                prefix="message",
            ),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Feishu Collaboration real-E2E evidence.")
    parser.add_argument("--installation-id", help="Specific collaboration_installations.id to inspect.")
    parser.add_argument("--list-chats", action="store_true", help="List Bot-visible Feishu chats via OpenAPI.")
    parser.add_argument("--snapshot", action="store_true", help="Print DB evidence snapshot. Default action.")
    parser.add_argument("--wait-new-event", action="store_true", help="Wait for one new Feishu event after taking a cursor.")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout seconds for --wait-new-event.")
    parser.add_argument("--send-test-message", action="store_true", help="Send a Feishu test message. Requires --chat-id.")
    parser.add_argument("--chat-id", help="Explicit test chat_id for --send-test-message.")
    parser.add_argument("--root-id", help="Optional root_id for a threaded test message.")
    parser.add_argument("--text", default="Byaan 飞书连接测试消息。", help="Text used with --send-test-message.")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    if args.send_test_message and not args.chat_id:
        raise SystemExit("--send-test-message requires explicit --chat-id. Refusing to send to an unknown chat.")
    if not os.getenv("DATABASE_URL"):
        print("DATABASE_URL is not set; default local DB resolution will be used.", file=sys.stderr)

    installation_id = UUID(args.installation_id) if args.installation_id else None
    evidence = FeishuCollaborationEvidence(installation_id)
    output: dict[str, Any] = {"ok": True, "database_url_configured": bool(os.getenv("DATABASE_URL"))}

    if args.list_chats:
        output["chats"] = await evidence.list_chats()

    if args.send_test_message:
        output["test_message"] = await evidence.send_test_message(args.chat_id, args.text, args.root_id)

    if args.wait_new_event:
        cursor = await evidence.cursor()
        output["cursor"] = {
            "last_event_ref": _hash_ref(cursor.last_event_id, prefix="evt"),
            "last_event_created_at": _dt(cursor.last_event_created_at),
        }
        output["snapshot_after_new_event"] = await evidence.wait_new_event(cursor, timeout_seconds=args.timeout)

    if args.snapshot or not (args.list_chats or args.send_test_message or args.wait_new_event):
        output["snapshot"] = await evidence.snapshot()

    print(_json(output))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(_json({"ok": False, "error": safe_feishu_error_message(exc)}), file=sys.stderr)
        raise
