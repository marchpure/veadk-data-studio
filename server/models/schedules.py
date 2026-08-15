from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.notebooks import Notebook
    from server.models.user import User


def generate_uuid() -> UUID:
    return uuid4()


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notebook_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    slack_channel_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delivery_target_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("collaboration_delivery_targets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)

    next_run_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=False), nullable=True, index=True)
    is_running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    notebook: Mapped[Notebook] = relationship("Notebook", foreign_keys=[notebook_id])
    creator: Mapped[User | None] = relationship("User", foreign_keys=[created_by])
    runs: Mapped[list[ScheduleRun]] = relationship(back_populates="schedule", cascade="all, delete-orphan")


class ScheduleRun(Base):
    __tablename__ = "schedule_runs"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    schedule_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=False), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    queries_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    queries_succeeded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    queries_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_id: Mapped[UUID | None] = mapped_column(GUID(), nullable=True)

    schedule: Mapped[Schedule] = relationship("Schedule", back_populates="runs")
