from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class UserPreferenceBase(BaseModel):
    preference_type: Literal["instructions", "style_guidelines"] = Field(
        ..., description="Type of preference: 'instructions', 'style_guidelines', or 'memory'"
    )
    content: str = Field(..., description="The content of the preference")


class UserPreferenceCreate(UserPreferenceBase):
    pass


class UserPreferenceUpdate(BaseModel):
    content: str = Field(..., description="The updated content of the preference")


class UserPreferenceResponse(UserPreferenceBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
