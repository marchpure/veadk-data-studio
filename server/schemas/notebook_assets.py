from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

NotebookAssetType = Literal["dataset", "semantic_model", "knowledge_resource"]


class NotebookAssetAssociateRequest(BaseModel):
    asset_type: NotebookAssetType
    asset_id: UUID
    usage_policy_json: dict | None = None


class NotebookAssetAssociationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    notebook_id: UUID
    asset_type: str
    asset_id: UUID
    added_by: UUID | None = None
    added_at: datetime
    usage_policy_json: dict | None = None


class NotebookAssetListResponse(BaseModel):
    items: list[dict]
    total: int
