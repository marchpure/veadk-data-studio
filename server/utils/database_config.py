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
    """Convert an async SQLAlchemy URL to a libpq-compatible sync URL.

    Some managed PostgreSQL connection strings use ``ssl=true``.  asyncpg
    accepts that spelling, while psycopg2/libpq rejects it and requires the
    ``sslmode`` option instead.  Keep an explicit ``sslmode`` untouched and
    translate the common boolean form only for the synchronous migration path.
    """
    converted = url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg2://", "postgresql://"
    )
    if "postgresql" not in converted:
        return converted

    parts = urlsplit(converted)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if any(key == "sslmode" for key, _ in query):
        return converted

    translated: list[tuple[str, str]] = []
    for key, value in query:
        if key != "ssl":
            translated.append((key, value))
            continue
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            translated.append(("sslmode", "require"))
        elif normalized in {"0", "false", "no", "off"}:
            translated.append(("sslmode", "disable"))
        elif normalized:
            translated.append(("sslmode", value))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(translated), parts.fragment)
    )


def async_database_url(url: str) -> str:
    """Remove libpq-only SSL query options before handing a URL to asyncpg."""
    if "postgresql" not in url:
        return url
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in {"ssl", "sslmode"}
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def async_connect_args(url: str | None = None) -> dict[str, object]:
    schema = database_schema()
    args: dict[str, object] = {"server_settings": {"search_path": schema}} if schema != "public" else {}
    if url and "postgresql" in url:
        query = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
        ssl_value = (query.get("sslmode") or query.get("ssl") or "").strip().lower()
        if ssl_value in {"0", "false", "no", "off", "disable"}:
            args["ssl"] = False
        elif ssl_value in {"1", "true", "yes", "on", "require", "verify-ca", "verify-full"}:
            args["ssl"] = True
    return args


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
