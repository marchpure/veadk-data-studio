from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

AssetType = Literal["dataset", "semantic_model", "knowledge_resource"]


class AssetSearchRequest(BaseModel):
    notebook_id: UUID | None = None
    query: str = ""
    asset_types: list[AssetType] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)


class AssetDescribeRequest(BaseModel):
    asset_type: AssetType
    asset_id: str


class AssetDescriptor(BaseModel):
    asset_type: AssetType
    asset_id: str
    name: str
    description: str | None = None
    status: str
    capabilities: dict[str, Any]
    freshness: dict[str, Any]
    provenance: dict[str, Any]
    usage_policy: dict[str, Any] = Field(default_factory=dict)
    sample_evidence: list[dict[str, Any]] = Field(default_factory=list)


class AssetSearchResponse(BaseModel):
    items: list[AssetDescriptor]
    total: int
