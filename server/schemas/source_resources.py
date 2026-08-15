from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

SourceResourceType = Literal[
    "pdf",
    "web",
    "feishu_doc",
    "feishu_sheet",
    "database_catalog",
    "database_schema",
    "database_table",
]
SourceSyncMode = Literal["manual", "scheduled"]
SourceResourceStatus = Literal["pending", "syncing", "understanding", "needs_confirmation", "ready", "failed"]
SourceSnapshotStatus = Literal["pending", "captured", "parsed", "indexed", "failed"]


class SourceResourceCreate(BaseModel):
    resource_type: SourceResourceType
    name: str
    connection_id: UUID | None = None
    external_id: str | None = None
    source_url: str | None = None
    visibility: str = "workspace"
    sync_mode: SourceSyncMode = "manual"
    sync_config_json: dict | None = None


class WebSourceResourceCreate(BaseModel):
    name: str
    source_url: str
    sync_mode: SourceSyncMode = "manual"
    sync_config_json: dict | None = None


class SourceResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    connection_id: UUID | None = None
    resource_type: str
    name: str
    external_id: str | None = None
    source_url: str | None = None
    owner_id: UUID | None = None
    visibility: str
    sync_mode: str
    sync_config_json: dict | None = None
    status: str
    latest_snapshot_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class SourceSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    resource_id: UUID
    external_revision: str | None = None
    content_hash: str
    raw_storage_uri: str
    captured_at: datetime
    parser_version: str | None = None
    metadata_json: dict | None = None
    status: str
    error_json: dict | None = None


class SourceSnapshotListResponse(BaseModel):
    items: list[SourceSnapshotRead]
    total: int


class KnowledgeResourceProcessingRead(BaseModel):
    id: UUID
    provider: str
    provider_resource_id: str | None = None
    parse_status: str
    index_status: str
    completeness_score: float | None = None


class SourceResourceProcessingRead(BaseModel):
    resource_id: UUID
    status: str
    latest_snapshot: SourceSnapshotRead | None = None
    knowledge_resource: KnowledgeResourceProcessingRead | None = None


class SourceResourceSyncResponse(BaseModel):
    resource_id: UUID
    status: str
    message: str
    snapshot_id: UUID | None = None
    knowledge_resource_id: UUID | None = None


class SourceResourceListResponse(BaseModel):
    items: list[SourceResourceRead]
    total: int
