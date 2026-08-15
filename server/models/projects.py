from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, String, func
from sqlalchemy.orm import Mapped, mapped_column

from server.db.base import GUID, Base


def generate_uuid() -> UUID:
    return uuid4()


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )
    path: Mapped[str] = mapped_column(String, nullable=False)
