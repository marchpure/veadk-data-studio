"""Slack signature verification service."""

import hashlib
import hmac
import time

from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


class SlackSignatureError(Exception):
    """Raised when Slack signature verification fails."""

    pass


class SlackSignatureService:
    """Verify Slack request signatures using HMAC-SHA256."""

    SIGNATURE_VERSION = "v0"
    MAX_TIMESTAMP_DIFF = 300  # 5 minutes

    @staticmethod
    def verify_signature(
        signing_secret: str,
        timestamp: str,
        body: bytes,
        signature: str,
    ) -> bool:
        """
        Verify Slack request signature.

        Process:
        1. Check timestamp is within 5 minutes (prevent replay attacks)
        2. Construct base string: "v0:{timestamp}:{body}"
        3. Compute HMAC-SHA256 with signing secret
        4. Compare with provided signature (constant-time)

        Args:
            signing_secret: Slack app signing secret
            timestamp: X-Slack-Request-Timestamp header value
            body: Raw request body bytes
            signature: X-Slack-Signature header value

        Returns:
            True if signature is valid

        Raises:
            SlackSignatureError: If verification fails
        """
        current_time = int(time.time())
        try:
            request_time = int(timestamp)
        except ValueError:
            logger.warning("Invalid Slack timestamp format")
            raise SlackSignatureError("Invalid timestamp format")

        if abs(current_time - request_time) > SlackSignatureService.MAX_TIMESTAMP_DIFF:
            logger.warning(f"Slack request timestamp too old: {current_time - request_time}s")
            raise SlackSignatureError("Request timestamp too old")

        try:
            body_str = body.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning("Invalid request body encoding")
            raise SlackSignatureError("Invalid request body encoding")

        sig_basestring = f"{SlackSignatureService.SIGNATURE_VERSION}:{timestamp}:{body_str}"

        computed_signature = (
            f"{SlackSignatureService.SIGNATURE_VERSION}="
            + hmac.new(
                signing_secret.encode("utf-8"),
                sig_basestring.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        )

        if not hmac.compare_digest(computed_signature, signature):
            logger.warning("Slack signature mismatch")
            raise SlackSignatureError("Invalid signature")

        return True
