from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContextRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=2048)
    kind: Literal["mcp_action", "knowledge_resource"]
    name: str = Field(min_length=1, max_length=240)
    source: Literal["OpenConnector", "OpenViking ResourceRef"]
    connection_id: str | None = Field(default=None, max_length=256)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    target_skill: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9][a-z0-9-]*$")
    description: str = Field(default="", max_length=4000)
    mcp_refs: list[ContextRef] = Field(default_factory=list, max_length=100)
    knowledge_refs: list[ContextRef] = Field(default_factory=list, max_length=100)


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="新会话", min_length=1, max_length=200)
    mcp_refs: list[ContextRef] | None = Field(default=None, max_length=100)
    knowledge_refs: list[ContextRef] | None = Field(default=None, max_length=100)


class SessionContextUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mcp_refs: list[ContextRef] = Field(default_factory=list, max_length=100)
    knowledge_refs: list[ContextRef] = Field(default_factory=list, max_length=100)


class InvocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    message: str = Field(min_length=1, max_length=100_000)
    client_invocation_id: str = Field(min_length=1, max_length=160)
    run_validation: bool = Field(default=True, alias="validate")


class RetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_invocation_id: str | None = Field(default=None, max_length=160)
