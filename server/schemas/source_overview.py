from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SourceKind = Literal["connection", "dataset", "source_resource"]
SourceFamily = Literal["files", "documents", "saas", "databases", "warehouses", "object_storage", "web", "api"]
AttentionState = Literal["none", "auth", "permission", "parse", "index", "stale", "policy"]
FreshnessStatus = Literal["fresh", "stale", "unknown"]
ContextIndexStatus = Literal["pending", "indexing", "indexed", "failed", "unavailable"]
ParseStatus = Literal["pending", "parsed", "failed"]
SourceVisibility = Literal["private", "workspace", "team", "public"]


class SourceOwner(BaseModel):
    id: str
    name: str | None = None


class ParsedAssetCounts(BaseModel):
    blocks: int = 0
    tables: int = 0
    files: int = 0
    evidence: int = 0


class ConsumerCounts(BaseModel):
    semantic_models: int = 0
    dashboards: int = 0
    notebooks: int = 0
    mcp_tools: int = 0


class SourceOverviewItem(BaseModel):
    id: str
    source_kind: SourceKind
    family: SourceFamily
    provider: str
    resource_type: str | None = None
    name: str
    status: str
    attention_state: AttentionState = "none"
    freshness_status: FreshnessStatus = "unknown"
    last_synced_at: str | None = None
    latest_snapshot_id: str | None = None
    projected_dataset_id: str | None = None
    context_index_status: ContextIndexStatus = "unavailable"
    parse_status: ParseStatus = "pending"
    parsed_asset_counts: ParsedAssetCounts = Field(default_factory=ParsedAssetCounts)
    consumer_counts: ConsumerCounts = Field(default_factory=ConsumerCounts)
    owner: SourceOwner | None = None
    visibility: SourceVisibility
    created_at: str
    updated_at: str | None = None
    counts_partial: bool = True


class SourceOverviewResponse(BaseModel):
    items: list[SourceOverviewItem]
    total: int
    counts_partial: bool = True
