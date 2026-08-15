"""
Waitlist Schemas - Pydantic models for request/response validation
"""

from pydantic import BaseModel, EmailStr


class JoinWaitlistRequest(BaseModel):
    """Request to join waitlist"""

    email: EmailStr
    name: str | None = None


class StoredCredentialsResponse(BaseModel):
    """Response for stored credentials"""

    email: str
    apiKey: str
    hasCredits: bool
