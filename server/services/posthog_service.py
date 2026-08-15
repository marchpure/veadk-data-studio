import logging
import os
from contextvars import ContextVar
from typing import Any

from posthog import Posthog

from server.utils.config_loader import get_posthog_config

logger = logging.getLogger(__name__)

ANALYTICS_OPT_OUT_KEY = "analytics_opt_out"

_request_opt_out_var: ContextVar[bool] = ContextVar("analytics_request_opt_out", default=False)


class PostHogService:
    _instance: Posthog | None = None
    _initialized: bool = False
    _current_user_id: str | None = None  # Stores current user_id for automatic tracking
    _current_user_email: str | None = None  # Stores current user email for error tracking
    _user_opt_out_cache: dict[str, bool] = {}  # user_id -> opted_out

    @classmethod
    def get_current_user_id(cls) -> str:
        """Get current user_id or default to 'server'"""
        return cls._current_user_id or "server"

    @classmethod
    def set_current_user_id(cls, user_id: str | None) -> None:
        """Set current user_id for automatic tracking"""
        cls._current_user_id = user_id

    @classmethod
    def get_current_user_email(cls) -> str | None:
        """Get current user email"""
        return cls._current_user_email

    @classmethod
    def set_current_user_email(cls, email: str | None) -> None:
        """Set current user email for error tracking"""
        cls._current_user_email = email

    @staticmethod
    def set_request_opt_out(opted_out: bool) -> None:
        """Set per-request opt-out flag (driven by X-Analytics-Opt-Out header)."""
        _request_opt_out_var.set(opted_out)

    @staticmethod
    def is_request_opt_out() -> bool:
        return _request_opt_out_var.get()

    @classmethod
    def prime_user_opt_out(cls, user_id: str, opted_out: bool) -> None:
        """Cache a user's opt-out preference (read from DB or set via API)."""
        if opted_out:
            cls._user_opt_out_cache[user_id] = True
        else:
            cls._user_opt_out_cache.pop(user_id, None)

    @classmethod
    def is_user_opted_out(cls, user_id: str | None) -> bool:
        if not user_id:
            return False
        return cls._user_opt_out_cache.get(user_id, False)

    @classmethod
    def _should_skip(cls, distinct_id: str | None) -> bool:
        if cls.is_request_opt_out():
            return True
        if cls.is_user_opted_out(distinct_id):
            return True
        if cls.is_user_opted_out(cls._current_user_id):
            return True
        return False

    @classmethod
    def initialize(cls) -> None:
        if cls._initialized:
            logger.warning("PostHog already initialized")
            return

        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TEST"):
            logger.info("PostHog disabled in test environment")
            cls._initialized = True
            return

        if os.getenv("VITE_DEV_MODE", "").lower() == "true":
            logger.info("PostHog disabled in dev mode (VITE_DEV_MODE=true)")
            cls._initialized = True
            return

        posthog_config = get_posthog_config()
        api_key = posthog_config.get("api_key") or os.getenv("VITE_PUBLIC_POSTHOG_KEY")
        host = posthog_config.get("host") or os.getenv("VITE_PUBLIC_POSTHOG_HOST", "https://us.i.posthog.com")

        if not api_key:
            logger.warning("PostHog API key not found. Analytics disabled.")
            cls._initialized = True
            return

        try:
            cls._instance = Posthog(project_api_key=api_key, host=host, enable_exception_autocapture=True)
            cls._initialized = True
            logger.info(f"PostHog initialized with exception autocapture (host: {host})")

        except Exception as e:
            logger.error(f"Failed to initialize PostHog: {e}")
            cls._initialized = True

    @classmethod
    async def load_opt_outs_from_db(cls) -> None:
        """Prime the per-user opt-out cache from the settings table at startup."""
        try:
            from sqlalchemy import select

            from server.db.session import AsyncSessionFactory
            from server.models.settings import Setting

            async with AsyncSessionFactory() as session:
                result = await session.execute(
                    select(Setting.user_id).where(
                        Setting.setting_key == ANALYTICS_OPT_OUT_KEY,
                        Setting.setting_value == "true",
                    )
                )
                count = 0
                for row in result.all():
                    user_id = row[0]
                    if user_id:
                        cls._user_opt_out_cache[str(user_id)] = True
                        count += 1
                if count:
                    logger.info(f"Primed analytics opt-out cache for {count} user(s)")
        except Exception as e:
            logger.warning(f"Failed to prime analytics opt-out cache: {e}")

    @classmethod
    def shutdown(cls) -> None:
        if cls._instance:
            try:
                cls._instance.shutdown()
                logger.info("PostHog shutdown successfully")
            except Exception as e:
                logger.error(f"Error shutting down PostHog: {e}")
            finally:
                cls._instance = None
                cls._initialized = False

    @classmethod
    def identify(cls, distinct_id: str, properties: dict[str, Any] | None = None) -> None:
        """Set user properties (person profile) in PostHog.

        Note: In PostHog Python SDK V6+, identify() was removed.
        Use set() to set person properties instead.

        Args:
            distinct_id: Unique user identifier (user_id)
            properties: User properties like email, name
        """
        # Store user_id for automatic tracking in logger
        cls.set_current_user_id(distinct_id)

        if not cls._instance:
            return

        if cls._should_skip(distinct_id):
            return

        try:
            # PostHog V6+ uses set() instead of identify()
            # This sets person properties on the user profile
            cls._instance.set(distinct_id=distinct_id, properties=properties or {})
            cls._instance.flush()
            logger.info(f"PostHog user '{distinct_id}' properties set: {list((properties or {}).keys())}")
        except Exception as e:
            logger.error(f"Failed to set user properties for '{distinct_id}': {e}")

    @classmethod
    def capture_event(cls, distinct_id: str, event: str, properties: dict[str, Any] | None = None) -> None:
        if not cls._instance:
            return

        if cls._should_skip(distinct_id):
            return

        try:
            cls._instance.capture(distinct_id=distinct_id, event=event, properties=properties or {})
            # Flush immediately to ensure events are sent in DMG builds
            cls._instance.flush()
            logger.debug(f"PostHog event '{event}' captured and flushed")
        except Exception as e:
            logger.error(f"Failed to capture event '{event}': {e}")

    @classmethod
    def capture_error(
        cls, error: Exception, distinct_id: str = "server", context: dict[str, Any] | None = None
    ) -> None:
        """Capture exceptions using PostHog's official capture_exception API.

        Args:
            error: The exception to capture
            distinct_id: User identifier (defaults to "server")
            context: Additional properties to include with the exception
        """
        if not cls._instance:
            return

        if cls._should_skip(distinct_id):
            return

        try:
            # Add context properties including source identifier
            properties = {"source": "python_backend", **(context or {})}

            # Include user email if available
            if cls._current_user_email:
                properties["user_email"] = cls._current_user_email

            # Use PostHog's official exception capture API
            cls._instance.capture_exception(error, distinct_id=distinct_id, properties=properties)
            # Flush immediately to ensure errors are tracked in DMG builds
            cls._instance.flush()
            logger.debug(f"PostHog exception captured and flushed: {type(error).__name__}")
        except Exception as e:
            logger.error(f"Failed to capture exception: {e}")
