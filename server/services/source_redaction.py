from __future__ import annotations

import hashlib
import re
from typing import Any

SENSITIVE_SOURCE_TYPES = {
    "feishu_doc",
    "feishu_wiki",
    "feishu_sheet",
    "feishu_base",
    "tos_bucket",
    "tos_prefix",
    "tos_object",
}

SENSITIVE_CONTENT_REF_SOURCE_TYPES = {
    "feishu_sheet",
    "feishu_base",
    "tos_bucket",
    "tos_prefix",
    "tos_object",
}

_URL_RE = re.compile(r"https?://[^\s'\"),\]}]+", re.IGNORECASE)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b("
    r"[a-z0-9_-]*(?:access[_-]?token|refresh[_-]?token|session[_-]?token|app[_-]?secret|"
    r"secret[_-]?access[_-]?key|access[_-]?key[_-]?id|secret|token|key|bucket|sk|ak)[a-z0-9_-]*"
    r")\s*[:=]\s*['\"]?([^'\"\s,;)]+)"
)
_LIKELY_SECRET_TOKEN_RE = re.compile(r"(?i)\b[a-z0-9_-]*(?:secret|token)[a-z0-9_-]*\b")
_OBJECT_PATH_RE = re.compile(r"\b[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+\b")


def source_ref(kind: str, value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{kind}:ref:{digest}"


def is_sensitive_source_type(resource_type: str | None) -> bool:
    return bool(resource_type and resource_type in SENSITIVE_SOURCE_TYPES)


def should_ref_evidence_text(resource_type: str | None) -> bool:
    return bool(resource_type and resource_type in SENSITIVE_CONTENT_REF_SOURCE_TYPES)


def redact_sensitive_text(value: str | None) -> str | None:
    if value is None:
        return None

    def replace_url(match: re.Match[str]) -> str:
        return source_ref("url", match.group(0)) or "url:ref"

    redacted = _URL_RE.sub(replace_url, value)

    def replace_secret(match: re.Match[str]) -> str:
        key = match.group(1)
        secret = match.group(2)
        return f"{key}={source_ref(key.lower().replace('-', '_'), secret)}"

    redacted = _SECRET_ASSIGNMENT_RE.sub(replace_secret, redacted)
    redacted = _OBJECT_PATH_RE.sub(lambda match: source_ref("path", match.group(0)) or "path:ref", redacted)
    return _LIKELY_SECRET_TOKEN_RE.sub(lambda match: source_ref("token", match.group(0)) or "token:ref", redacted)


def sensitive_text_ref(value: str | None) -> str:
    return source_ref("content", value or "") or "content:ref"


def redact_source_identifier(kind: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return source_ref(kind, value)
    return source_ref(kind, str(value))


def redact_sensitive_json(value: Any, *, resource_type: str | None = None) -> Any:
    if isinstance(value, dict):
        return {key: _redact_json_item(key, item, resource_type=resource_type) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_json(item, resource_type=resource_type) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def _redact_json_item(key: str, value: Any, *, resource_type: str | None) -> Any:
    key_lower = key.lower()
    if key_lower in {
        "source_url",
        "original_url",
        "final_url",
        "located_from_url",
        "raw_storage_uri",
    }:
        return redact_source_identifier("url", value)

    if any(term in key_lower for term in ("secret", "token", "access_key", "refresh", "password", "credential")):
        return redact_source_identifier(key_lower, value)

    if key_lower in {"external_id"} and is_sensitive_source_type(resource_type):
        return redact_source_identifier(f"{resource_type}_external", value)

    if resource_type and resource_type.startswith("tos_") and key_lower in {"bucket", "key", "prefix"}:
        return redact_source_identifier(f"tos_{key_lower}", value)

    return redact_sensitive_json(value, resource_type=resource_type)
