from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from server.collaboration.contracts import ChannelChatType, ChannelEvent, ChannelEventType, CollaborationPlatform

MENTION_TAG_RE = re.compile(r"<at[^>]*?user_id=[\"']([^\"']+)[\"'][^>]*>.*?</at>")


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    result: dict[str, Any] = {}
    for name in dir(value):
        if name.startswith("_"):
            continue
        try:
            attr = getattr(value, name)
        except Exception:
            continue
        if callable(attr):
            continue
        if attr is not None:
            result[name] = attr
    return result


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return content
    elif isinstance(content, dict):
        parsed = content
    else:
        parsed = _as_dict(content)
    text = parsed.get("text") if isinstance(parsed, dict) else None
    return str(text or "")


def _chat_type(raw_type: str | None, root_id: str | None) -> ChannelChatType:
    lowered = (raw_type or "").lower()
    if lowered in {"p2p", "private", "dm"}:
        return ChannelChatType.P2P
    if root_id:
        return ChannelChatType.TOPIC_GROUP
    return ChannelChatType.GROUP


def normalize_feishu_message_event(raw_event: Any, installation_id: UUID, bot_external_id: str | None = None) -> ChannelEvent:
    raw = _as_dict(raw_event)
    event = _as_dict(raw.get("event", raw))
    sender = _as_dict(event.get("sender") or raw.get("sender") or {})
    message = _as_dict(event.get("message") or raw.get("message") or {})
    sender_id = _as_dict(sender.get("sender_id") or sender.get("id") or {})

    message_id = str(message.get("message_id") or raw.get("message_id") or raw.get("event_id") or "")
    event_id = str(
        _as_dict(raw.get("header") or {}).get("event_id")
        or raw.get("event_id")
        or message.get("message_id")
        or message_id
    )
    chat_id = str(message.get("chat_id") or raw.get("chat_id") or "")
    root_id = message.get("root_id") or message.get("parent_id")
    root_id = str(root_id) if root_id else None
    parent_id = message.get("parent_id")
    parent_id = str(parent_id) if parent_id else None
    text = _content_text(message.get("content"))

    mentions: list[str] = []
    for mention in message.get("mentions") or []:
        mention_dict = _as_dict(mention)
        mention_id = _as_dict(mention_dict.get("id") or {})
        user_id = mention_id.get("open_id") or mention_id.get("user_id") or mention_dict.get("user_id")
        if user_id:
            mentions.append(str(user_id))
    mentions.extend(MENTION_TAG_RE.findall(text))
    mentions = list(dict.fromkeys(mentions))

    if bot_external_id:
        text = _strip_feishu_mentions(text, {bot_external_id})
    else:
        text = _strip_feishu_mentions(text, set())

    sender_external_id = (
        sender_id.get("open_id")
        or sender_id.get("user_id")
        or sender.get("open_id")
        or sender.get("user_id")
        or raw.get("sender_external_id")
        or ""
    )
    raw_chat_type = message.get("chat_type") or raw.get("chat_type")
    occurred_at = None
    create_time = message.get("create_time") or raw.get("event_time")
    if create_time:
        try:
            occurred_at = datetime.fromtimestamp(int(create_time) / 1000 if int(create_time) > 10_000_000_000 else int(create_time))
        except Exception:
            occurred_at = None

    return ChannelEvent(
        platform=CollaborationPlatform.FEISHU,
        installation_id=installation_id,
        event_id=event_id,
        event_type=ChannelEventType.MESSAGE,
        chat_id=chat_id,
        chat_type=_chat_type(str(raw_chat_type) if raw_chat_type else None, root_id),
        message_id=message_id,
        root_message_id=root_id,
        parent_message_id=parent_id,
        sender_external_id=str(sender_external_id),
        mentions=mentions,
        text=text.strip(),
        occurred_at=occurred_at,
        raw_reference={
            "message_id": message_id,
            "chat_id": chat_id,
            "root_id": root_id,
            "chat_type": raw_chat_type,
        },
    )


def should_trigger_feishu_message(
    event: ChannelEvent,
    bot_external_id: str | None,
    *,
    has_existing_conversation: bool = False,
) -> bool:
    if not event.text:
        return False
    if bot_external_id and event.sender_external_id == bot_external_id:
        return False
    if event.chat_type == ChannelChatType.P2P:
        return True
    if bot_external_id and bot_external_id in event.mentions:
        return True
    return bool(event.conversation_root_id and has_existing_conversation)


def _strip_feishu_mentions(text: str, bot_ids: set[str]) -> str:
    def repl(match: re.Match[str]) -> str:
        user_id = match.group(1)
        return "" if not bot_ids or user_id in bot_ids else match.group(0)

    stripped = MENTION_TAG_RE.sub(repl, text)
    return re.sub(r"\s+", " ", stripped).strip()
