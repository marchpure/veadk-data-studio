from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, TIMESTAMP, CheckConstraint, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.message_attachments import MessageAttachment
    from server.models.threads import Thread


def generate_uuid() -> UUID:
    return uuid4()


ROLES = ("user", "assistant", "system", "tool")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    thread_id: Mapped[UUID | None] = mapped_column(GUID(), ForeignKey("threads.id", ondelete="CASCADE"), nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_call_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())

    thread: Mapped[Thread] = relationship(back_populates="messages")
    attachments: Mapped[list[MessageAttachment]] = relationship(back_populates="message", cascade="all, delete-orphan")

    __table_args__ = (CheckConstraint(f"role IN {ROLES}", name="ck_messages_role"),)
