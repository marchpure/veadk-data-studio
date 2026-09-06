from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

from server.db import session as db_session
from server.db.session import get_async_engine, get_database_url
from server.services.conversation_state import ConversationStateSession
from server.utils.config_loader import is_self_hosted
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)
DATABASE_URL = db_session.DATABASE_URL


def _get_sqlite_agent_db_path() -> str:
    """Get path for SQLite agent session database (separate from main db to avoid locking conflicts)."""
    try:
        url = make_url(DATABASE_URL or get_database_url())
        if url.drivername.startswith("sqlite"):
            db_path = url.database

            if not db_path or db_path == ":memory:":
                return ":memory:"

            db_file = Path(db_path)
            parent_dir = db_file.parent
            return str(parent_dir / "agent_sessions.db")

    except Exception as e:
        logger.warning("Failed to derive SQLite path from DATABASE_URL: %s", e)

    return ".data/agent_sessions.db"


def _create_sqlite_backend(session_id: str) -> Any:
    from agents import SQLiteSession

    db_path = _get_sqlite_agent_db_path()
    logger.debug("Creating SQLite agent session: %s at %s", session_id, db_path)
    return SQLiteSession(session_id, db_path)


async def _create_postgresql_backend(session_id: str) -> Any:
    from agents.extensions.memory import SQLAlchemySession

    logger.debug("Creating PostgreSQL agent session: %s", session_id)
    return SQLAlchemySession(
        session_id,
        engine=get_async_engine(),
        create_tables=False,
        sessions_table="agent_sessions",
        messages_table="agent_messages",
    )


async def create_agent_session(session_id: str) -> ConversationStateSession:
    """Create an agent session with SQLite (local) or PostgreSQL (hosted) backend."""
    if is_self_hosted():
        backend = await _create_postgresql_backend(session_id)
    else:
        backend = _create_sqlite_backend(session_id)

    return ConversationStateSession(session_id, backend)


def create_agent_session_sync(session_id: str) -> ConversationStateSession:
    """Synchronous version for SQLite sessions only. Warns if called in hosted mode."""
    if is_self_hosted():
        logger.warning(
            "create_agent_session_sync called in hosted mode - falling back to SQLite. "
            "Use create_agent_session() for PostgreSQL support."
        )

    backend = _create_sqlite_backend(session_id)
    return ConversationStateSession(session_id, backend)


def get_session_backend_info() -> dict[str, str]:
    if is_self_hosted():
        return {
            "backend": "postgresql",
            "engine": "SQLAlchemySession",
            "note": "Using shared lazy async_engine from main application",
        }
    return {
        "backend": "sqlite",
        "engine": "SQLiteSession",
        "database_path": _get_sqlite_agent_db_path(),
    }
