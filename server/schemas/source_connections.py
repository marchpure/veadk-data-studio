from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AnyUrl, BaseModel, Field

SourceProvider = Literal["feishu", "volcengine_tos"]
SourceAuthMode = Literal["oauth", "access_key", "sts", "none"]


class ConnectorDefinitionRead(BaseModel):
    id: str
    provider: str
    category: str
    family: str
    display_name: str
    icon: str
    auth_mode: str
    capabilities: list[str]
    limitations: list[str] = Field(default_factory=list)
    required_scopes: list[str] = Field(default_factory=list)
    config_schema: dict[str, Any]
    resource_picker_schema: dict[str, Any]
    resource_picker_type: str = "none"
    supported_resource_types: list[str]
    availability: str
    status: str
    modeling_modes: list[str] = Field(default_factory=list)
    description: str = ""


class SourceConnectionCreate(BaseModel):
    provider: SourceProvider
    auth_mode: SourceAuthMode
    display_name: str
    credentials: dict[str, Any] = Field(default_factory=dict)
    external_account_id: str | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)
    test_connection: bool = True


class SourceConnectionRead(BaseModel):
    id: UUID
    provider: str
    auth_mode: str
    external_account_id: str | None = None
    display_name: str
    status: str
    capabilities: dict[str, Any]
    token_expires_at: datetime | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class FeishuAdminConfigRequest(BaseModel):
    app_id: str
    app_secret: str
    redirect_uri: str
    scopes: list[str] = Field(default_factory=list)


class FeishuAdminConfigRead(BaseModel):
    configured: bool
    app_id: str | None = None
    redirect_uri: str | None = None
    scopes: list[str] = Field(default_factory=list)
    required_scopes: list[str] = Field(default_factory=list)
    missing_scopes: list[str] = Field(default_factory=list)


class FeishuOAuthStartResponse(BaseModel):
    authorization_url: str
    state: str


class FeishuOAuthCallbackResponse(BaseModel):
    connection_id: UUID
    status: str
    display_name: str


class SourceResourceListRequest(BaseModel):
    provider: SourceProvider | None = None
    scope: str = "recent"
    parent_token: str | None = None
    resource_type: str | None = None
    query: str | None = None
    page_token: str | None = None
    page_size: int = Field(default=50, ge=1, le=200)


class SourceResourcePickerItem(BaseModel):
    external_id: str
    resource_type: str
    name: str
    parent_external_id: str | None = None
    source_url: str | None = None
    has_children: bool = False
    is_folder: bool = False
    already_added: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceResourcePickerResponse(BaseModel):
    items: list[SourceResourcePickerItem]
    next_page_token: str | None = None
    scope: str
    connection_status: str


class SourceResourceQuickLocateRequest(BaseModel):
    url: AnyUrl


class SourceResourceQuickLocateResponse(BaseModel):
    item: SourceResourcePickerItem | None = None
    connection_status: str
