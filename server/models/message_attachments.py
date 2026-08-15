from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, CheckConstraint, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.messages import Message


def generate_uuid() -> UUID:
    return uuid4()


ALLOWED_MIME_TYPES = ("image/png", "image/jpeg", "image/webp")


class MessageAttachment(Base):
    __tablename__ = "message_attachments"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    message_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_data: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())

    message: Mapped[Message] = relationship(back_populates="attachments")

    __table_args__ = (CheckConstraint(f"mime_type IN {ALLOWED_MIME_TYPES}", name="ck_message_attachments_mime_type"),)
