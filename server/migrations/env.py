from __future__ import annotations

import asyncio
import logging
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql import text

config = context.config
if config.config_file_name is not None:
    # Preserve existing logger configuration so Alembic doesn't silence app logs
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    fileConfig(config.config_file_name, disable_existing_loggers=False)
    root_logger.setLevel(previous_level)


BASE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BASE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=str(ENV_PATH), override=False)

import server.models  # noqa: F401,E402
from server.db.base import Base  # noqa: E402
from server.utils.database_config import (  # noqa: E402
    add_schema_query,
    async_connect_args,
    configured_database_url,
    database_schema,
)

target_metadata = Base.metadata


def _get_database_url() -> str:
    url = configured_database_url()
    if not url:
        url = f"sqlite+aiosqlite:///{BASE_DIR / '.data' / 'app.db'}"
    return url


async def _ensure_wide_alembic_version_column(connection: AsyncConnection, url: str) -> None:
    """Allow human-readable Alembic revision ids on PostgreSQL.

    Alembic creates ``alembic_version.version_num`` as VARCHAR(32), but this
    repository has legacy semantic-modeling revision ids longer than that. The
    self-hosted entrypoint invokes Alembic directly, so this preflight must live
    in env.py instead of only in application startup migration helpers.
    """
    if "postgresql" not in url:
        return

    await connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(255) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
    )
    await connection.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"))
    await connection.commit()


def run_migrations_offline() -> None:
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    connectable = create_async_engine(
        add_schema_query(_get_database_url()),
        poolclass=pool.NullPool,
        connect_args=async_connect_args(),
    )

    async with connectable.connect() as connection:  # type: ignore[assignment]
        if database_schema() != "public":
            schema = database_schema()
            exists = await connection.execute(
                text("SELECT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema)"),
                {"schema": schema},
            )
            if not exists.scalar():
                raise RuntimeError(f"Required PostgreSQL schema {schema!r} does not exist")
            await connection.execute(text(f'SET search_path TO "{schema}"'))
            await connection.commit()
        await _ensure_wide_alembic_version_column(connection, _get_database_url())
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
