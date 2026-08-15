from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SourceEvidenceRead(BaseModel):
    id: UUID
    fragment_type: str
    title_path: list[Any] | None = None
    text: str
    locator_json: dict[str, Any]
    confidence: str | None = None


class SourceResourceUnderstandingRead(BaseModel):
    id: UUID
    resource_type: str
    name: str
    external_id: str | None = None
    latest_snapshot_id: UUID | None = None
    status: str


class SourceSkillCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    resource_id: UUID
    snapshot_id: UUID
    source_id: str
    candidate_type: str
    title: str
    statement: str
    structured_payload_json: dict[str, Any]
    evidence_ids_json: list[Any]
    evidence: list[SourceEvidenceRead] = Field(default_factory=list)
    confidence: float
    validation_status: str
    validation_json: dict[str, Any]
    review_status: str
    generator: str
    version: int
    reviewed_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime
    updated_at: datetime


class SourceUnderstandingRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    datasource_id: str
    connection_id: UUID | None = None
    provider: str
    status: str
    analyzer_version: str
    source_snapshot_ids_json: list[Any]
    summary_json: dict[str, Any]
    drift_json: dict[str, Any]
    error_json: dict[str, Any] | None = None
    created_at: datetime
    completed_at: datetime | None = None


class SourceUnderstandingRead(BaseModel):
    datasource_id: str
    datasource_name: str
    datasource_type: str
    latest_run: SourceUnderstandingRunRead | None = None
    resources: list[SourceResourceUnderstandingRead] = Field(default_factory=list)
    candidates: list[SourceSkillCandidateRead] = Field(default_factory=list)
    evidence: list[SourceEvidenceRead] = Field(default_factory=list)
    overview: dict[str, Any] = Field(default_factory=dict)
    profile: dict[str, Any] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)
    sync_drift: dict[str, Any] = Field(default_factory=dict)


class SourceAnalyzeRequest(BaseModel):
    refresh_schema: bool = False
    scope: list[str] = Field(default_factory=list)


class SourceSkillReviewRequest(BaseModel):
    action: Literal["accept", "edit", "reject"]
    title: str | None = None
    statement: str | None = None
    structured_payload: dict[str, Any] | None = None
    note: str | None = None


class SourceToSemanticModelRequest(BaseModel):
    model_id: str | None = None
    name: str | None = None
    domain: str = "Sales / Orders"
    owner: str = "Data Team"
    candidate_ids: list[UUID] = Field(default_factory=list)


class SourceToSemanticModelResponse(BaseModel):
    model: dict[str, Any]
    applied_candidate_ids: list[UUID]
    lineage: dict[str, Any]
