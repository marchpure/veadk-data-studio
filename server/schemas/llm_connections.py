from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class LLMConnectionCreate(BaseModel):
    type: str
    name: str | None = None
    config: dict[str, Any]


class LLMConnectionRead(BaseModel):
    id: UUID
    type: str
    name: str | None = None
    config: dict[str, Any]
    created_by: UUID | None = None
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class LLMConnectionUpdate(BaseModel):
    type: str | None = None
    name: str | None = None
    config: dict[str, Any] | None = None


class LLMConnectionListResponse(BaseModel):
    items: list[LLMConnectionRead]
    total: int | None = None
