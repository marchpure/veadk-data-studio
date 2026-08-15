"""
Utility for sanitizing error messages to prevent credential exposure.

This module provides functions to redact sensitive patterns like API keys,
Bearer tokens, passwords, and connection strings from error messages before
they are returned to clients.
"""

import re

SENSITIVE_PATTERNS = [
    (re.compile(r"(Authorization:\s*)(Bearer\s+)?[\w\-\.]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(api[_-]?key[\"']?\s*[:=]\s*[\"']?)[\w\-]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(token[\"']?\s*[:=]\s*[\"']?)[\w\-]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(password[\"']?\s*[:=]\s*[\"']?)[\w\-]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(secret[\"']?\s*[:=]\s*[\"']?)[\w\-]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"Bearer\s+[\w\-\.]+", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"mongodb://[^@]+@", re.IGNORECASE), "mongodb://[REDACTED]@"),
    (re.compile(r"postgres://[^@]+@", re.IGNORECASE), "postgres://[REDACTED]@"),
    (re.compile(r"mysql://[^@]+@", re.IGNORECASE), "mysql://[REDACTED]@"),
]


def sanitize_error_message(error: Exception) -> str:
    """
    Sanitize an error message by redacting sensitive patterns.

    Args:
        error: The exception to sanitize

    Returns:
        A sanitized string representation of the error
    """
    message = str(error)
    for pattern, replacement in SENSITIVE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message
