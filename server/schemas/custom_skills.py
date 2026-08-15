from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CustomSkillApiConfig(BaseModel):
    api_base_url: str = Field(..., min_length=1, max_length=500)
    api_type: Literal["rest", "graphql"] = "rest"
    api_auth_type: Literal["bearer", "custom"] = "bearer"
    api_domain: str = ""
    api_key: str = ""


class CustomSkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Skill name (slug format)")
    description: str = Field(
        ..., min_length=1, max_length=500, description="Brief description of when to use this skill"
    )
    instructions: str = Field(..., min_length=1, description="The skill instructions/content")
    scope: Literal["user", "org"] = Field(default="user", description="Scope: 'user' (personal) or 'org' (team shared)")
    skill_type: Literal["general", "slack_inbound", "slack_outbound"] = Field(
        default="general", description="Skill type: 'general', 'slack_inbound', or 'slack_outbound'"
    )
    api_config: CustomSkillApiConfig | None = None


class CustomSkillUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, min_length=1, max_length=500)
    instructions: str | None = Field(None, min_length=1)
    skill_type: Literal["general", "slack_inbound", "slack_outbound"] | None = None
    is_active: bool | None = None
    api_config: CustomSkillApiConfig | None = None
    remove_api_config: bool = False


class CustomSkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    instructions: str
    scope: str
    skill_type: str
    is_active: bool
    created_by: UUID
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    can_execute_api: bool = False
    api_base_url: str | None = None
    api_type: str | None = None
    api_auth_type: str | None = None
    api_domain: str | None = None
    domain_active: bool = True
    has_credentials: bool = False
    github_repo_id: UUID | None = None
    github_analysis_type: str | None = None
    github_repo_name: str | None = None


class CustomSkillListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    scope: str
    skill_type: str
    is_active: bool
    created_by: UUID
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    can_execute_api: bool = False
    api_base_url: str | None = None
    api_type: str | None = None
    api_auth_type: str | None = None
    api_domain: str | None = None
    domain_active: bool = True
    has_credentials: bool = False
    github_repo_id: UUID | None = None
    github_analysis_type: str | None = None
    github_repo_name: str | None = None


class CustomSkillDomainToggleRequest(BaseModel):
    active: bool
