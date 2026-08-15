from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from server.schemas.messages import MessageRead


class ThreadCreate(BaseModel):
    id: str | None = None  # Optional - if provided, use this ID instead of generating new one
    thread_title: str | None = None
    notebook_id: str | UUID


class ThreadRead(BaseModel):
    id: UUID
    thread_title: str | None = None
    notebook_id: UUID
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class ThreadWithMessages(BaseModel):
    thread: ThreadRead
    messages: list[MessageRead]

    model_config = {
        "from_attributes": True,
    }


class ConversationResponse(BaseModel):
    thread: ThreadRead
    message: MessageRead
