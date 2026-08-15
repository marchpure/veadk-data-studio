from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class FeishuInstallationCreate(BaseModel):
    app_id: str = Field(..., min_length=1)
    app_secret: str | None = None
    connection_mode: str = Field("websocket", pattern="^(websocket|webhook)$")
    default_llm_connection_id: UUID | None = None


class FeishuInstallationUpdate(BaseModel):
    app_id: str | None = Field(None, min_length=1)
    app_secret: str | None = Field(None, min_length=1)
    connection_mode: str | None = Field(None, pattern="^(websocket|webhook)$")
    default_llm_connection_id: UUID | None = None
    is_active: bool | None = None


class TestMessageRequest(BaseModel):
    chat_id: str | None = Field(None, min_length=1)
    target_id: UUID | None = None
    text: str = Field("Byaan 飞书连接测试消息。", min_length=1)
    root_id: str | None = None
    confirm_non_production: bool = False


class FeishuChatSelectRequest(BaseModel):
    chat_id: str = Field(..., min_length=1)
    name: str | None = None
    chat_type: str = "group"
    root_id: str | None = None
    confirm_non_production: bool = False


class FeishuEventIngestRequest(BaseModel):
    installation_id: UUID | None = None
    event: dict
