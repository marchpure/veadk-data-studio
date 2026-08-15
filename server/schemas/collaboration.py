from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class FeishuInstallationCreate(BaseModel):
    app_id: str | None = Field(None, min_length=1)
    app_secret: str | None = None
    connection_mode: str = Field("websocket", min_length=1)
    default_llm_connection_id: UUID | None = None
    verification_token: str | None = None
    encrypt_key: str | None = None


class FeishuInstallationUpdate(BaseModel):
    app_id: str | None = Field(None, min_length=1)
    app_secret: str | None = Field(None, min_length=1)
    connection_mode: str | None = Field(None, min_length=1)
    default_llm_connection_id: UUID | None = None
    is_active: bool | None = None


class TestMessageRequest(BaseModel):
    chat_id: str = Field(..., min_length=1)
    text: str = Field("Byaan 飞书连接测试消息。", min_length=1)
    root_id: str | None = None


class ExternalIdentityMappingRequest(BaseModel):
    user_id: UUID


class FeishuDeliveryTargetBindRequest(BaseModel):
    chat_id: str = Field(..., min_length=1)
    root_id: str | None = None
    target_type: str | None = Field(None, min_length=1)
    display_name: str | None = None


class FeishuOutboundMessageRequest(BaseModel):
    delivery_target_id: UUID
    text: str = Field(..., min_length=1, max_length=4000)
    idempotency_key: str = Field(..., min_length=8, max_length=128)
    confirm: bool = False


class FeishuOAuthStartRequest(BaseModel):
    default_llm_connection_id: UUID | None = None


class FeishuOAuthResultRequest(BaseModel):
    state: str = Field(..., min_length=16)
