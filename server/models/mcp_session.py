from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.mcp_api_key import MCPAPIKey
    from server.models.notebook import Notebook
    from server.models.tenant import Tenant
    from server.models.user import User


class MCPSession(Base):
    __tablename__ = "mcp_sessions"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    session_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mcp_api_key_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("mcp_api_keys.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notebook_id: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("notebooks.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_activity_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp()
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=False), default=datetime.now, server_default=func.current_timestamp()
    )

    tenant: Mapped[Tenant] = relationship("Tenant", foreign_keys=[tenant_id])
    user: Mapped[User] = relationship("User", foreign_keys=[user_id])
    mcp_api_key: Mapped[MCPAPIKey | None] = relationship("MCPAPIKey", foreign_keys=[mcp_api_key_id])
    notebook: Mapped[Notebook | None] = relationship("Notebook", foreign_keys=[notebook_id])
