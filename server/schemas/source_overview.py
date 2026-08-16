from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SourceKind = Literal["connection", "dataset", "source_resource"]
SourceFamily = Literal["files", "documents", "saas", "databases", "nosql", "warehouses", "object_storage", "web", "api"]
AttentionState = Literal["none", "auth", "permission", "parse", "index", "stale", "policy"]
FreshnessStatus = Literal["fresh", "stale", "unknown"]
ContextIndexStatus = Literal["pending", "indexing", "indexed", "failed", "unavailable"]
ParseStatus = Literal["pending", "parsed", "failed"]
SourceVisibility = Literal["private", "workspace", "team", "public"]
ModelingStatus = Literal[
    "supported",
    "needs_projection",
    "context_only",
    "permission_required",
    "reauthorization_required",
    "blocked",
    "source_unavailable",
    "processing",
    "failed",
    "planned",
    "unsupported",
]
ModelingMode = Literal[
    "relational",
    "warehouse",
    "projection",
    "document_projection",
    "context_assisted",
    "business_object",
    "event",
    "semantic_import",
]


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
    connection_id: str | None = None
    family: SourceFamily
    provider: str
    resource_type: str | None = None
    name: str
    status: str
    attention_state: AttentionState = "none"
    freshness_status: FreshnessStatus = "unknown"
    last_synced_at: str | None = None
    latest_snapshot_id: str | None = None
    raw_artifact_uri: str | None = None
    projected_dataset_id: str | None = None
    projection_review: dict[str, Any] | None = None
    context_index_status: ContextIndexStatus = "unavailable"
    parse_status: ParseStatus = "pending"
    parsed_asset_counts: ParsedAssetCounts = Field(default_factory=ParsedAssetCounts)
    consumer_counts: ConsumerCounts = Field(default_factory=ConsumerCounts)
    owner: SourceOwner | None = None
    visibility: SourceVisibility
    next_actions: list[str] = Field(default_factory=list)
    modeling_status: ModelingStatus = "unsupported"
    modeling_mode: ModelingMode | None = None
    modeling_reason: str | None = None
    modeling_next_action: str | None = None
    modeling_evidence_summary: str | None = None
    modeling_can_load_profile: bool = False
    created_at: str
    updated_at: str | None = None
    counts_partial: bool = True


class SourceOverviewResponse(BaseModel):
    items: list[SourceOverviewItem]
    total: int
    counts_partial: bool = True
