from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MessageCreate(BaseModel):
    role: str
    content: str
    tool_call_id: str | None = None
    metadata_: dict | None = None


class MessageAttachmentRead(BaseModel):
    id: UUID
    file_name: str
    mime_type: str
    file_data: str

    model_config = {
        "from_attributes": True,
    }


class MessageRead(BaseModel):
    id: UUID
    thread_id: UUID | None = None
    role: str
    content: str
    tool_call_id: str | None = None
    metadata_: dict | None = None
    created_at: datetime
    attachments: list[MessageAttachmentRead] = []

    model_config = {
        "from_attributes": True,
    }
