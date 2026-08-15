from __future__ import annotations

import base64
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MessageAttachmentCreate(BaseModel):
    file_name: str = Field(..., max_length=255)
    mime_type: Literal["image/png", "image/jpeg", "image/webp"]
    file_data: str = Field(..., description="Base64 encoded image data")

    @field_validator("file_data")
    @classmethod
    def validate_base64(cls, v: str) -> str:
        try:
            base64.b64decode(v)
            return v
        except Exception:
            raise ValueError("file_data must be valid base64")


class MessageAttachmentRead(BaseModel):
    id: UUID
    message_id: UUID
    file_name: str
    mime_type: str
    file_data: str
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }
