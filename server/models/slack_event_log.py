from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, Boolean, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from server.db.base import GUID, Base


class SlackEventLog(Base):
    __tablename__ = "slack_event_logs"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    slack_workspace_id: Mapped[UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    slack_channel_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    slack_user_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(20), nullable=False, default="received")
    redaction_applied: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp()
    )
