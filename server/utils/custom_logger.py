import logging
import re
import sys
from typing import Any

from server.utils.error_sanitizer import sanitize_error_payload, sanitize_text


class CustomLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.name = name

    def _get_current_user_id(self) -> str:
        """Get current user_id from PostHogService, fallback to 'server'"""
        try:
            from server.services.posthog_service import PostHogService

            return PostHogService.get_current_user_id()
        except Exception:
            return "server"

    def _send_to_posthog(self, exception: Exception, message: str, context: dict[str, Any] | None = None):
        """Send error information to PostHog for tracking."""
        try:
            from server.services.posthog_service import PostHogService

            sanitized_context = sanitize_error_payload(context or {})
            posthog_context = {
                "module": self.name,
                "log_message": sanitize_text(message),
                "function_name": sys._getframe(3).f_code.co_name,  # Get calling function name
                **sanitized_context,
            }

            # Automatically use current user_id
            user_id = self._get_current_user_id()
            PostHogService.capture_error(error=exception, distinct_id=user_id, context=posthog_context)
        except Exception:
            # Silently fail - don't let PostHog errors break the application
            pass

    def _send_event_to_posthog(self, event_name: str, message: str, context: dict[str, Any] | None = None):
        """Send non-error events to PostHog for tracking."""
        try:
            from server.services.posthog_service import PostHogService

            sanitized_context = sanitize_error_payload(context or {})
            properties = {
                "module": self.name,
                "log_message": sanitize_text(message),
                "function_name": sys._getframe(3).f_code.co_name,
                **sanitized_context,
            }

            # Automatically use current user_id
            user_id = self._get_current_user_id()
            PostHogService.capture_event(distinct_id=user_id, event=event_name, properties=properties)
        except Exception:
            # Silently fail - don't let PostHog errors break the application
            pass

    def debug(self, message: str, *args, posthog_context: dict[str, Any] | None = None, **kwargs):
        # Set stacklevel to 2 so logging reports the caller's location, not this wrapper
        kwargs.setdefault("stacklevel", 2)
        self.logger.debug(sanitize_text(message), *args, **kwargs)

        # Send to PostHog if context provided
        if posthog_context:
            self._send_event_to_posthog("log_debug", message, posthog_context)

    def info(self, message: str, *args, posthog_context: dict[str, Any] | None = None, **kwargs):
        # Set stacklevel to 2 so logging reports the caller's location, not this wrapper
        kwargs.setdefault("stacklevel", 2)
        self.logger.info(sanitize_text(message), *args, **kwargs)

        # Send to PostHog if context provided
        if posthog_context:
            self._send_event_to_posthog("log_info", message, posthog_context)

    def warning(self, message: str, *args, posthog_context: dict[str, Any] | None = None, **kwargs):
        # Set stacklevel to 2 so logging reports the caller's location, not this wrapper
        kwargs.setdefault("stacklevel", 2)
        self.logger.warning(sanitize_text(message), *args, **kwargs)

        # Send to PostHog if context provided
        if posthog_context:
            self._send_event_to_posthog("log_warning", message, posthog_context)

    def error(self, message: str, *args, exc_info: Any = None, posthog_context: dict[str, Any] | None = None, **kwargs):
        # Set stacklevel to 2 so logging reports the caller's location, not this wrapper
        kwargs.setdefault("stacklevel", 2)
        message = sanitize_text(message)
        # Log to standard logger first
        self.logger.error(message, *args, exc_info=exc_info, **kwargs)

        # Extract exception for PostHog tracking
        exception = None
        if exc_info is True:
            exception = sys.exc_info()[1]
        elif isinstance(exc_info, Exception):
            exception = exc_info

        # If no exception provided, create a generic one for PostHog
        if not exception:
            exception = Exception(message)

        # Send to PostHog for error tracking (user_id auto-detected)
        self._send_to_posthog(exception, message, posthog_context)

    def critical(
        self, message: str, *args, exc_info: Any = None, posthog_context: dict[str, Any] | None = None, **kwargs
    ):
        # Set stacklevel to 2 so logging reports the caller's location, not this wrapper
        kwargs.setdefault("stacklevel", 2)
        message = sanitize_text(message)
        # Log to standard logger
        self.logger.critical(message, *args, exc_info=exc_info, **kwargs)

        # Extract exception for PostHog tracking
        exception = None
        if exc_info is True:
            exception = sys.exc_info()[1]
        elif isinstance(exc_info, Exception):
            exception = exc_info

        if not exception:
            exception = Exception(message)

        # Send to PostHog with critical severity (user_id auto-detected)
        posthog_context = posthog_context or {}
        posthog_context["severity"] = "critical"
        self._send_to_posthog(exception, message, posthog_context)

    def exception(self, message: str, *args, posthog_context: dict[str, Any] | None = None, **kwargs):
        # Since exception() calls error(), we need stacklevel=3 to point to the actual caller
        # (actual_code -> exception() -> error() -> logger.error())
        kwargs.setdefault("stacklevel", 3)
        self.error(message, *args, exc_info=True, posthog_context=posthog_context, **kwargs)


class SensitiveDataFilter(logging.Filter):
    """Filter that redacts sensitive data from log messages."""

    PATTERNS = [
        (re.compile(r'password["\']?\s*[:=]\s*["\']?[\w\-]+', re.IGNORECASE), "password=[REDACTED]"),
        (re.compile(r'api[_-]?key["\']?\s*[:=]\s*["\']?[\w\-]+', re.IGNORECASE), "api_key=[REDACTED]"),
        (re.compile(r"Bearer\s+[\w\-\.]+", re.IGNORECASE), "Bearer [REDACTED]"),
        (re.compile(r"mongodb://[^@]+@", re.IGNORECASE), "mongodb://[REDACTED]@"),
        (re.compile(r"postgres://[^@]+@", re.IGNORECASE), "postgres://[REDACTED]@"),
        (re.compile(r"mysql://[^@]+@", re.IGNORECASE), "mysql://[REDACTED]@"),
        (re.compile(r'secret["\']?\s*[:=]\s*["\']?[\w\-]+', re.IGNORECASE), "secret=[REDACTED]"),
        (re.compile(r'token["\']?\s*[:=]\s*["\']?[\w\-]+', re.IGNORECASE), "token=[REDACTED]"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "msg") and record.msg:
            msg = sanitize_text(str(record.msg))
            for pattern, replacement in self.PATTERNS:
                msg = pattern.sub(replacement, msg)
            record.msg = msg
        return True


def get_logger(name: str) -> CustomLogger:
    return CustomLogger(name)


def configure_log_redaction() -> None:
    """Add sensitive data filter to the root logger."""
    root_logger = logging.getLogger()
    root_logger.addFilter(SensitiveDataFilter())
