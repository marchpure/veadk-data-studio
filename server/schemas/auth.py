from pydantic import BaseModel


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class GoogleAuthRequest(BaseModel):
    """Request body for Google OAuth authentication."""

    credential: str  # The ID token from Google Sign-In
