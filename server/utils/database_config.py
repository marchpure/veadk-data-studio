from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from server.services.runtime_secrets import RuntimeSecretError, get_runtime_secret


def external_mode() -> bool:
    return os.getenv("DWV1_EXTERNAL_OIDC_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def database_schema() -> str:
    value = os.getenv("DWV1_DATABASE_SCHEMA", "public").strip()
    if not value or not value.replace("_", "").isalnum() or not (value[0].isalpha() or value[0] == "_"):
        raise ValueError("DWV1_DATABASE_SCHEMA must be a valid PostgreSQL schema identifier")
    return value


def configured_database_url() -> str | None:
    value = os.getenv("DATABASE_URL")
    if value:
        return value
    if not external_mode():
        return None
    try:
        return get_runtime_secret("database_url")
    except RuntimeSecretError as exc:
        raise ValueError("DATABASE_URL is unavailable from the configured KMS secret") from exc


def sync_database_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")


def async_connect_args() -> dict[str, object]:
    schema = database_schema()
    return {"server_settings": {"search_path": schema}} if schema != "public" else {}


def sync_connect_args() -> dict[str, str]:
    schema = database_schema()
    return {"options": f"-csearch_path={schema}"} if schema != "public" else {}


def add_schema_query(url: str) -> str:
    schema = database_schema()
    if schema == "public" or "postgresql" not in url:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("options", f"-csearch_path={schema}")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
