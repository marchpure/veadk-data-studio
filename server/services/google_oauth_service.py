from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from server.utils.config_loader import get_google_oauth_config
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


class GoogleOAuthError(Exception):
    """Custom exception for Google OAuth errors."""

    pass


class GoogleOAuthService:
    """Service to verify Google OAuth tokens."""

    @staticmethod
    async def verify_google_token(credential: str) -> dict:
        """
        Verify Google ID token and return user info.

        Args:
            credential: The Google ID token (JWT) from frontend

        Returns:
            Dict with keys: email, google_id (sub), name, picture, email_verified

        Raises:
            GoogleOAuthError: If token is invalid or verification fails
        """
        config = get_google_oauth_config()
        client_id = config.get("client_id")

        if not client_id:
            logger.error("GOOGLE_CLIENT_ID not configured")
            raise GoogleOAuthError("Google OAuth not configured")

        try:
            # Verify the token (allow 10 seconds clock skew for Docker/server time drift)
            idinfo = id_token.verify_oauth2_token(
                credential, google_requests.Request(), client_id, clock_skew_in_seconds=10
            )

            # Verify the issuer
            if idinfo["iss"] not in ["accounts.google.com", "https://accounts.google.com"]:
                raise GoogleOAuthError("Invalid token issuer")

            # Verify email is verified by Google
            if not idinfo.get("email_verified", False):
                raise GoogleOAuthError("Email not verified by Google")

            return {
                "email": idinfo["email"],
                "google_id": idinfo["sub"],  # Google's unique user ID
                "name": idinfo.get("name"),
                "picture": idinfo.get("picture"),
                "email_verified": idinfo.get("email_verified", False),
            }

        except ValueError as e:
            logger.error(f"Invalid Google token: {e}")
            raise GoogleOAuthError(f"Invalid Google token: {e}")
