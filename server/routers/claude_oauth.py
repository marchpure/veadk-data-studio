"""
Claude OAuth Router
-------------------
API endpoints for Claude Pro/Max OAuth authentication flow.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from server.schemas.standard_response import error_response, success_response
from server.services.claude_oauth_service import (
    create_auth_url,
    delete_credentials,
    delete_long_term_token,
    exchange_code_for_tokens,
    get_auth_method,
    get_credentials,
    is_token_expired,
    refresh_tokens,
    save_credentials,
    save_long_term_token,
)
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/claude-oauth", tags=["claude-oauth"])


class ExchangeCodeRequest(BaseModel):
    """Request body for exchanging authorization code."""

    code: str
    state: str


class SaveTokenRequest(BaseModel):
    """Request body for saving a long-term token."""

    token: str


@router.post("/start")
async def start_oauth():
    """
    Start OAuth flow - generates PKCE parameters and returns authorization URL.

    The user should visit the returned URL in their browser, authenticate with Claude,
    and then copy the authorization code to submit via /exchange.
    """
    try:
        auth_url, state = create_auth_url()
        logger.info("[CLAUDE OAUTH API] Started OAuth flow")
        return success_response(
            {"auth_url": auth_url, "state": state},
            "Authorization URL generated. Visit the URL and paste the authorization code.",
        )
    except Exception as e:
        logger.error(f"[CLAUDE OAUTH API] Failed to start OAuth: {e}")
        return error_response(str(e), "Failed to start OAuth flow")


@router.post("/exchange")
async def exchange_code(request: ExchangeCodeRequest):
    """
    Exchange authorization code for tokens.

    After the user authenticates with Claude and receives an authorization code,
    this endpoint exchanges it for access and refresh tokens.
    """
    try:
        tokens = await exchange_code_for_tokens(request.code, request.state)
        credentials_path = save_credentials(tokens)
        logger.info("[CLAUDE OAUTH API] Successfully authenticated with Claude")
        return success_response(
            {"authenticated": True, "credentials_path": str(credentials_path)},
            "Successfully authenticated with Claude Pro/Max",
        )
    except ValueError as e:
        logger.error(f"[CLAUDE OAUTH API] Exchange failed: {e}")
        return error_response(str(e), "Authentication failed")
    except Exception as e:
        logger.error(f"[CLAUDE OAUTH API] Unexpected error during exchange: {e}")
        return error_response(str(e), "Failed to exchange authorization code")


@router.get("/status")
async def check_auth_status():
    """
    Check if Claude OAuth credentials exist and are valid.

    Returns authentication status including auth_method ('oauth', 'token', or null).
    """
    try:
        auth_method = get_auth_method()

        if auth_method == "token":
            return success_response(
                {
                    "authenticated": True,
                    "auth_method": "token",
                    "needs_refresh": False,
                },
                "Authenticated with long-term token",
            )

        credentials = get_credentials()
        if not credentials:
            return success_response(
                {"authenticated": False, "auth_method": None, "needs_refresh": False},
                "Not authenticated with Claude",
            )

        expired = is_token_expired()
        return success_response(
            {
                "authenticated": True,
                "auth_method": "oauth",
                "needs_refresh": expired,
                "has_refresh_token": bool(credentials.get("refreshToken")),
            },
            "Authenticated with Claude" + (" (token expired)" if expired else ""),
        )
    except Exception as e:
        logger.error(f"[CLAUDE OAUTH API] Status check failed: {e}")
        return error_response(str(e), "Failed to check authentication status")


@router.post("/refresh")
async def refresh_access_token():
    """
    Refresh the access token using the stored refresh token.

    This should be called when the access token is expired but a refresh token exists.
    """
    try:
        tokens = await refresh_tokens()
        if tokens:
            return success_response(
                {"refreshed": True},
                "Token refreshed successfully",
            )
        else:
            return error_response(
                "No refresh token available or refresh failed",
                "Token refresh failed",
            )
    except Exception as e:
        logger.error(f"[CLAUDE OAUTH API] Refresh failed: {e}")
        return error_response(str(e), "Failed to refresh token")


@router.post("/logout")
async def logout():
    """
    Delete stored OAuth credentials (logout from Claude).
    """
    try:
        deleted = delete_credentials()
        if deleted:
            logger.info("[CLAUDE OAUTH API] Logged out from Claude")
            return success_response(
                {"logged_out": True},
                "Successfully logged out from Claude",
            )
        else:
            return success_response(
                {"logged_out": False},
                "No credentials to delete",
            )
    except Exception as e:
        logger.error(f"[CLAUDE OAUTH API] Logout failed: {e}")
        return error_response(str(e), "Failed to logout")


@router.post("/save-token")
async def save_token(request: SaveTokenRequest):
    """
    Save a long-term token obtained from `claude setup-token`.

    Once saved, this takes precedence over OAuth credentials.
    Token validity is checked when actually used for inference.
    """
    try:
        token = request.token.strip()
        if not token:
            return error_response("Token cannot be empty", "Invalid token")

        token_path = save_long_term_token(token)
        logger.info("[CLAUDE OAUTH API] Long-term token saved successfully")
        return success_response(
            {"authenticated": True, "auth_method": "token", "token_path": str(token_path)},
            "Long-term token saved successfully",
        )
    except Exception as e:
        logger.error(f"[CLAUDE OAUTH API] Save token failed: {e}")
        return error_response(str(e), "Failed to save token")


@router.post("/delete-token")
async def delete_token():
    """
    Delete the stored long-term token.
    """
    try:
        deleted = delete_long_term_token()
        if deleted:
            logger.info("[CLAUDE OAUTH API] Long-term token deleted")
            return success_response({"deleted": True}, "Long-term token deleted")
        else:
            return success_response({"deleted": False}, "No token to delete")
    except Exception as e:
        logger.error(f"[CLAUDE OAUTH API] Delete token failed: {e}")
        return error_response(str(e), "Failed to delete token")
