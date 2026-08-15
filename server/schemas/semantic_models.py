from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SemanticModelCreateRequest(BaseModel):
    datasource_id: str = "oracle-sales"
    domain: str = "Sales / Orders"
    selected_tables: list[str] = Field(default_factory=list)
    business_questions: str = ""


class GenerationJobResponse(BaseModel):
    id: str
    datasource_id: str
    status: str
    phase: str
    progress: int
    steps: list[dict[str, Any]]
    result_model_id: str | None = None
    error: str | None = None


class RelationshipPatch(BaseModel):
    cardinality: str | None = None
    uniqueRate: float | None = None
    orphanRate: float | None = None
    fanoutRisk: str | None = None
    validationStatus: str | None = None
    status: str | None = None
    validationMessage: str | None = None


class MetricPatch(BaseModel):
    businessName: str | None = None
    definition: str | None = None
    kind: str | None = None
    formula: str | None = None
    filter: str | None = None
    timeField: str | None = None
    defaultGrain: str | None = None
    dimensions: list[str] | None = None
    unit: str | None = None
    owner: str | None = None
    certification: str | None = None


class ExplorePatch(BaseModel):
    metricId: str | None = None
    dimensionId: str | None = None
    grain: str | None = None
    timeRange: str | None = None
    filter: str | None = None
    viewMode: str | None = None


class SaveExploreArtifactRequest(BaseModel):
    kind: str


class SuggestionActionRequest(BaseModel):
    action: str


class PublishNotesRequest(BaseModel):
    notes: str


class RawSqlFallbackRequest(BaseModel):
    enabled: bool


class McpQueryRequest(BaseModel):
    metric: str | None = None
    dimension: str | None = None
    grain: str | None = None
    time_range: str | None = None
