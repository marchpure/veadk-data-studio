from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

AssetType = Literal["dataset", "semantic_model", "knowledge_resource", "dashboard"]
PublishState = Literal["draft", "validating", "blocked", "published", "archived"]


class GateSummary(BaseModel):
    score: int = Field(default=0, ge=0, le=100)
    passed: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    blockers: list[str] = Field(default_factory=list)


class AssetSearchRequest(BaseModel):
    notebook_id: UUID | None = None
    query: str = ""
    asset_types: list[AssetType] = Field(default_factory=list)
    publish_states: list[PublishState] = Field(default_factory=list)
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
    publish_state: PublishState = "draft"
    gate: GateSummary | None = None
    version: str | None = None
    consumers: list[str] = Field(default_factory=list)
    capabilities: dict[str, Any]
    freshness: dict[str, Any]
    provenance: dict[str, Any]
    usage_policy: dict[str, Any] = Field(default_factory=dict)
    sample_evidence: list[dict[str, Any]] = Field(default_factory=list)


class AssetSearchResponse(BaseModel):
    items: list[AssetDescriptor]
    total: int
