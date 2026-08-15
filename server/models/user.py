from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import TIMESTAMP, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import Base

if TYPE_CHECKING:
    from server.models.refresh_token import RefreshToken
    from server.models.tenant_member import TenantMember
    from server.models.verification_token import VerificationToken


class User(SQLAlchemyBaseUserTableUUID, Base):
    """User model compatible with FastAPI Users.

    SQLAlchemyBaseUserTableUUID provides:
    - id: UUID (primary key)
    - email: str (unique, indexed)
    - hashed_password: str
    - is_active: bool (default True)
    - is_verified: bool (default False)
    - is_superuser: bool (default False)
    """

    __tablename__ = "users"

    # Custom fields
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    tenant_memberships: Mapped[list[TenantMember]] = relationship(back_populates="user", cascade="all, delete-orphan")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user", cascade="all, delete-orphan")
    verification_tokens: Mapped[list[VerificationToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
