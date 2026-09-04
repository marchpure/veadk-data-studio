from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SkillRef(BaseModel):
    id: str
    kind: Literal["connection", "mcp_action", "knowledge_resource"]
    name: str
    source: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillSessionCreate(BaseModel):
    skill_id: UUID | None = None
    target: str = ""
    mcp_refs: list[SkillRef] = Field(default_factory=list)
    knowledge_refs: list[SkillRef] = Field(default_factory=list)


class SkillInvocationCreate(BaseModel):
    message: str = Field(..., min_length=1)
    client_invocation_id: str = Field(..., min_length=1, max_length=160)
    validate: bool = False


class SkillRetryRequest(BaseModel):
    client_invocation_id: str | None = Field(default=None, max_length=160)


class SkillSessionResponse(BaseModel):
    id: str
    skill_id: str | None = None
    target: str
    mcp_refs: list[SkillRef]
    knowledge_refs: list[SkillRef]
    revision: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    artifact: dict[str, Any] | None = None
    status: str = "idle"
    backend: Literal["REAL AGENT", "TEST BACKEND"]
    preview_url: str


class SkillSessionsResponse(BaseModel):
    items: list[SkillSessionResponse]
    total: int
