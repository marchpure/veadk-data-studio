from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base


def generate_uuid() -> UUID:
    return uuid4()


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    thread_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    notebook_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())

    notebook: Mapped[Notebook] = relationship(back_populates="threads")
    messages: Mapped[list[Message]] = relationship(back_populates="thread", cascade="all, delete-orphan")
