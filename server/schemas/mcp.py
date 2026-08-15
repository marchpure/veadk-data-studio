from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MCPAPIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Friendly name for this API key")


class MCPAPIKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime


class MCPAPIKeyCreateResponse(BaseModel):
    id: UUID
    name: str
    api_key: str
    key_prefix: str
    created_at: datetime
