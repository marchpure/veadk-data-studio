from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, TIMESTAMP, CheckConstraint, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db.base import GUID, Base

if TYPE_CHECKING:
    from server.models.notebooks import Notebook
    from server.models.user import User


def generate_uuid() -> UUID:
    return uuid4()


NOTEBOOK_ASSET_TYPES = ("dataset", "semantic_model", "knowledge_resource")


class NotebookAsset(Base):
    __tablename__ = "notebook_assets"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=generate_uuid)
    tenant_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notebook_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    added_by: Mapped[UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    usage_policy_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    added_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=False), server_default=func.current_timestamp())

    notebook: Mapped[Notebook] = relationship("Notebook")
    user: Mapped[User | None] = relationship("User")

    __table_args__ = (
        CheckConstraint(f"asset_type IN {NOTEBOOK_ASSET_TYPES}", name="ck_notebook_assets_type"),
        UniqueConstraint("tenant_id", "notebook_id", "asset_type", "asset_id", name="uq_notebook_assets_asset"),
    )
