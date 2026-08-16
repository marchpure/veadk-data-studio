from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

SourceResourceType = Literal[
    "pdf",
    "web",
    "feishu_doc",
    "feishu_wiki",
    "feishu_sheet",
    "feishu_base",
    "tos_bucket",
    "tos_prefix",
    "tos_object",
    "extracted_table",
]


class SourceResourceCreate(BaseModel):
    resource_type: SourceResourceType
    name: str
    external_id: str | None = None
    source_url: str | None = None
    visibility: str = "workspace"
    sync_mode: Literal["manual", "scheduled"] = "manual"
    sync_config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content: str | None = Field(
        default=None,
        description="Optional caller-supplied text content. External connectors are not simulated when this is absent.",
    )
    external_revision: str | None = None
    provider: str = "byaan-native"


class SourceResourceSelection(BaseModel):
    external_id: str
    resource_type: SourceResourceType
    name: str | None = None
    source_url: str | None = None
    parent_external_id: str | None = None
    subresources: list[dict[str, Any]] = Field(default_factory=list)
    selection_config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceResourceImportRequest(BaseModel):
    connection_id: UUID
    selections: list[SourceResourceSelection] = Field(min_length=1)
    sync_mode: Literal["manual", "scheduled"] = "manual"
    schedule: dict[str, Any] | None = None


class SourceResourceSyncRequest(BaseModel):
    content: str | None = None
    external_revision: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    provider: str = "byaan-native"


class SourceSnapshotRead(BaseModel):
    id: UUID
    resource_id: UUID
    external_revision: str | None = None
    content_hash: str
    raw_storage_uri: str
    captured_at: datetime
    parser_version: str | None = None
    metadata_json: dict[str, Any] | None = None
    status: str
    error_json: dict[str, Any] | None = None


class EvidenceFragmentRead(BaseModel):
    id: UUID
    knowledge_resource_id: UUID
    snapshot_id: UUID
    fragment_type: str
    title_path: list[Any] | None = None
    text: str
    locator_json: dict[str, Any]
    confidence: str | None = None
    content_hash: str | None = None
    created_at: datetime


class KnowledgeResourceRead(BaseModel):
    id: UUID
    resource_id: UUID
    snapshot_id: UUID
    provider: str
    provider_resource_id: str | None = None
    parse_status: str
    index_status: str
    completeness_score: float | None = None
    created_at: datetime
    evidence_count: int = 0


class SourceResourceRead(BaseModel):
    id: UUID
    connection_id: UUID | None = None
    source_connection_id: UUID | None = None
    resource_type: str
    name: str
    external_id: str | None = None
    source_url: str | None = None
    parent_external_id: str | None = None
    selection_config_json: dict[str, Any] | None = None
    visibility: str
    sync_mode: str
    sync_config_json: dict[str, Any] | None = None
    status: str
    latest_snapshot_id: UUID | None = None
    projected_dataset_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    latest_snapshot: SourceSnapshotRead | None = None
    knowledge_resource: KnowledgeResourceRead | None = None


class SourceResourceProcessingRead(BaseModel):
    resource_id: UUID
    status: str
    stage: str
    message: str
    latest_snapshot_id: UUID | None = None
    knowledge_resource_id: UUID | None = None
    evidence_count: int = 0
    connector_required: bool = False
    next_actions: list[str] = Field(default_factory=list)


class KnowledgeSearchRequest(BaseModel):
    query: str
    resource_ids: list[UUID] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=50)


class KnowledgeSearchResponse(BaseModel):
    items: list[EvidenceFragmentRead]
    total: int


class NotebookAssetCreate(BaseModel):
    asset_type: Literal["dataset", "semantic_model", "knowledge_resource"]
    asset_id: str
    usage_policy: dict[str, Any] = Field(default_factory=dict)


class NotebookAssetRead(BaseModel):
    id: UUID
    notebook_id: UUID
    asset_type: str
    asset_id: str
    added_by: UUID | None = None
    usage_policy_json: dict[str, Any]
    added_at: datetime
