import os
import secrets
from uuid import UUID

from fastapi import Depends, Request, Response
from fastapi_users import BaseUserManager, UUIDIDMixin, exceptions, schemas
from sqlalchemy import select

from server.auth.db import get_user_db
from server.models.user import User
from server.services.email_service import EmailService, SMTPEmailService
from server.utils.config_loader import get_auth_secret, get_email_config, get_smtp_config
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


def _get_email_service() -> EmailService | SMTPEmailService | None:
    """
    Get email service based on configuration priority:
    1. SMTP (if configured) - for self-hosted deployments
    2. Resend API (if configured) - for deployments using Resend service
    3. None - if neither configured
    """
    smtp_config = get_smtp_config()
    if smtp_config:
        return SMTPEmailService(
            smtp_host=smtp_config["smtp_host"],
            smtp_port=smtp_config["smtp_port"],
            smtp_username=smtp_config["smtp_username"],
            smtp_password=smtp_config["smtp_password"],
            smtp_from_email=smtp_config["smtp_from_email"],
            smtp_from_name=smtp_config["smtp_from_name"],
            smtp_use_tls=smtp_config["smtp_use_tls"],
        )

    email_config = get_email_config()
    if email_config["api_key"]:
        return EmailService(api_key=email_config["api_key"], from_email=email_config["from_email"])

    return None


class UserManager(UUIDIDMixin, BaseUserManager[User, UUID]):
    # External OIDC functions receive KMS-backed secrets in request headers.
    # Keep module import side-effect free on that path.
    _import_secret = (
        secrets.token_urlsafe(32)
        if os.getenv("DWV1_EXTERNAL_OIDC_ENABLED", "").strip().lower() in {"1", "true", "yes"}
        else get_auth_secret()
    )
    reset_password_token_secret = _import_secret
    verification_token_secret = _import_secret

    async def on_after_login(
        self,
        user: User,
        request: Request | None = None,
        response: Response | None = None,
    ) -> None:
        logger.info(f"User {user.email} logged in successfully")

    async def on_after_register(self, user: User, request: Request | None = None):
        # Skip verification email for Google OAuth users (already verified by Google)
        if user.is_verified:
            logger.info(f"User {user.email} registered via OAuth, already verified")
            return
        logger.info(f"User {user.email} registered, requesting verification")
        await self.request_verify(user, request)

    async def on_after_forgot_password(self, user: User, token: str, request: Request | None = None):
        email_service = _get_email_service()
        if not email_service:
            logger.warning("Email service not configured, skipping password reset email")
            return

        config = get_email_config()
        reset_link = f"{config['frontend_url']}/reset-password?token={token}"
        try:
            result = await email_service.send_password_reset_email(
                to_email=user.email,
                reset_link=reset_link,
                name=user.full_name,
            )
            if result.get("success"):
                logger.info(f"Password reset email sent successfully to {user.email}")
            else:
                error_detail = result.get("error", "Unknown error")
                logger.error(f"Failed to send password reset email to {user.email}: {error_detail}")
        except Exception as e:
            logger.error(f"Unexpected error sending password reset email to {user.email}: {str(e)}", exc_info=True)

    async def on_after_request_verify(self, user: User, token: str, request: Request | None = None):
        email_service = _get_email_service()
        if not email_service:
            logger.warning("Email service not configured, skipping verification email")
            return

        config = get_email_config()
        verification_link = f"{config['frontend_url']}/verify-email?token={token}"
        try:
            result = await email_service.send_verification_email(
                to_email=user.email,
                verification_link=verification_link,
                name=user.full_name,
            )
            if result.get("success"):
                logger.info(f"Verification email sent successfully to {user.email}")
            else:
                error_detail = result.get("error", "Unknown error")
                logger.error(f"Failed to send verification email to {user.email}: {error_detail}")
        except Exception as e:
            logger.error(f"Unexpected error sending verification email to {user.email}: {str(e)}", exc_info=True)

    async def on_after_verify(self, user: User, request: Request | None = None):
        logger.info(f"User {user.email} verified successfully")

    async def create(
        self,
        user_create: schemas.UC,
        safe: bool = False,
        request: Request | None = None,
    ) -> User:
        existing_user = await self.user_db.get_by_email(user_create.email)
        if existing_user is not None:
            raise exceptions.UserAlreadyExists()
        return await super().create(user_create, safe, request)

    async def get_by_google_id(self, google_id: str) -> User | None:
        """Get user by Google ID."""
        session = self.user_db.session
        result = await session.execute(select(User).where(User.google_id == google_id))
        return result.scalar_one_or_none()

    async def oauth_callback(
        self,
        email: str,
        google_id: str,
        name: str | None = None,
        picture: str | None = None,
    ) -> User:
        """
        Handle Google OAuth callback - either get existing user, link accounts, or create new user.

        Logic:
        1. If user with this google_id exists -> return that user
        2. If user with this email exists (password-based) -> link google_id and return
        3. Otherwise -> create new user with google_id

        All users from Google OAuth are marked as verified (trusting Google's verification).
        """
        # First, check if user with this google_id already exists
        user = await self.get_by_google_id(google_id)
        if user:
            logger.info(f"Google OAuth: Existing user found by google_id: {email}")
            return user

        # Check if user with this email exists (could be password-based account)
        try:
            user = await self.get_by_email(email)
            if user:
                # Link the Google account to existing user
                logger.info(f"Google OAuth: Linking Google account to existing user: {email}")
                update_dict = {
                    "google_id": google_id,
                    "is_verified": True,  # Mark as verified since Google verified the email
                }
                if picture and not user.avatar_url:
                    update_dict["avatar_url"] = picture
                if name and not user.full_name:
                    update_dict["full_name"] = name

                await self.user_db.update(user, update_dict)
                # Refresh user to get updated data
                user = await self.get_by_email(email)
                return user
        except exceptions.UserNotExists:
            pass

        # Create new user
        logger.info(f"Google OAuth: Creating new user: {email}")

        # Generate a random password hash (user won't use password to login)
        random_password = secrets.token_urlsafe(32)

        user_dict = {
            "email": email,
            "hashed_password": self.password_helper.hash(random_password),
            "is_active": True,
            "is_verified": True,  # Trust Google's email verification
            "is_superuser": False,
            "full_name": name,
            "google_id": google_id,
            "avatar_url": picture,
        }

        created_user = await self.user_db.create(user_dict)
        await self.on_after_register(created_user, None)

        return created_user


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)
