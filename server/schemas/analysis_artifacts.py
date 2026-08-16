from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

AnalysisArtifactStatus = Literal["draft", "review", "published", "archived"]


class AnalysisArtifactCreate(BaseModel):
    notebook_id: UUID
    name: str
    objective: str = ""
    definition: dict[str, Any] = Field(default_factory=dict)
    status: AnalysisArtifactStatus = "draft"


class AnalysisArtifactUpdate(BaseModel):
    name: str | None = None
    objective: str | None = None
    definition: dict[str, Any] | None = None
    status: AnalysisArtifactStatus | None = None


class AnalysisArtifactRead(BaseModel):
    id: UUID
    notebook_id: UUID
    name: str
    objective: str
    definition_json: dict[str, Any]
    version: int
    status: str
    latest_result_snapshot_id: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AnalysisArtifactListResponse(BaseModel):
    items: list[AnalysisArtifactRead]
    total: int


class AnalysisArtifactRenderResponse(BaseModel):
    artifact_id: UUID
    format: Literal["markdown", "html"]
    content: str


class AnalysisArtifactRunResponse(BaseModel):
    artifact_id: UUID
    status: Literal["not_started", "queued"]
    message: str
    required_bindings: list[str] = Field(default_factory=list)
