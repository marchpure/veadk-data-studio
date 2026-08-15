from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol
from uuid import UUID


class CollaborationPlatform(str, Enum):
    FEISHU = "feishu"
    SLACK = "slack"


class ChannelEventType(str, Enum):
    MESSAGE = "message"
    CARD_ACTION = "card_action"
    MEMBER_CHANGE = "member_change"
    DELIVERY = "delivery"


class ChannelChatType(str, Enum):
    GROUP = "group"
    TOPIC_GROUP = "topic_group"
    P2P = "p2p"


class ChannelResultStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class ChannelAttachment:
    id: str
    type: str
    name: str | None = None
    url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChannelEvent:
    platform: CollaborationPlatform
    installation_id: UUID
    event_id: str
    event_type: ChannelEventType
    chat_id: str
    chat_type: ChannelChatType
    message_id: str
    root_message_id: str | None
    parent_message_id: str | None
    sender_external_id: str
    mentions: list[str]
    text: str
    attachments: list[ChannelAttachment] = field(default_factory=list)
    action: dict[str, Any] | None = None
    occurred_at: datetime | None = None
    raw_reference: dict[str, Any] = field(default_factory=dict)

    @property
    def conversation_root_id(self) -> str | None:
        return self.root_message_id or self.parent_message_id


@dataclass(slots=True)
class ResponseRef:
    run_id: str
    conversation_id: UUID
    platform_message_id: str
    platform_card_id: str | None = None
    sequence: int = 0
    status: str = "running"


@dataclass(slots=True)
class ChannelResult:
    run_id: str
    status: ChannelResultStatus
    summary: str
    progress_steps: list[str] = field(default_factory=list)
    artifact_id: str | None = None
    result_snapshot_id: str | None = None
    metrics: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    error_user_message: str | None = None


class CollaborationChannel(Protocol):
    async def probe(self, installation: Any) -> dict[str, Any]:
        ...

    async def normalize_event(self, raw_event: dict[str, Any]) -> ChannelEvent:
        ...

    async def send_ack(self, conversation: Any) -> ResponseRef | None:
        ...

    async def start_response(self, conversation: Any, response: ChannelResult) -> ResponseRef:
        ...

    async def update_response(self, response_ref: ResponseRef, delta: ChannelResult) -> ResponseRef:
        ...

    async def finish_response(self, response_ref: ResponseRef, result: ChannelResult) -> ResponseRef:
        ...

    async def send_file(self, conversation: Any, file: Any) -> dict[str, Any]:
        ...

    async def fetch_history(self, conversation: Any, limit: int) -> list[dict[str, Any]]:
        ...

    async def list_delivery_targets(self) -> list[dict[str, Any]]:
        ...

    async def mention_user(self, external_user_id: str) -> str:
        ...
