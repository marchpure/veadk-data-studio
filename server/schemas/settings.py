from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SettingCreate(BaseModel):
    setting_key: str
    setting_value: str
    description: str | None = None
    is_encrypted: bool = False


class SettingUpdate(BaseModel):
    setting_value: str | None = None
    description: str | None = None
    is_encrypted: bool | None = None


class SettingRead(BaseModel):
    id: UUID
    setting_key: str
    setting_value: str
    description: str | None = None
    is_encrypted: bool
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
    }


class SettingListResponse(BaseModel):
    items: list[SettingRead]
    total: int | None = None
