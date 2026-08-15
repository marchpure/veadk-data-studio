from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.services.agent_session_factory import (
    _get_sqlite_agent_db_path,
    create_agent_session,
    create_agent_session_sync,
    get_session_backend_info,
)


class TestGetSqliteAgentDbPath:
    def test_returns_memory_for_memory_database(self):
        with patch("server.services.agent_session_factory.DATABASE_URL", "sqlite+aiosqlite:///:memory:"):
            path = _get_sqlite_agent_db_path()
            assert path == ":memory:"

    def test_returns_sibling_path_for_file_database(self):
        with patch("server.services.agent_session_factory.DATABASE_URL", "sqlite+aiosqlite:////path/to/app.db"):
            path = _get_sqlite_agent_db_path()
            assert path == "/path/to/agent_sessions.db"

    def test_fallback_on_error(self):
        with patch("server.services.agent_session_factory.DATABASE_URL", "invalid://url"):
            path = _get_sqlite_agent_db_path()
            assert path == ".data/agent_sessions.db"


class TestSessionFactory:
    @pytest.mark.asyncio
    async def test_creates_sqlite_session_in_local_mode(self):
        with patch("server.services.agent_session_factory.is_self_hosted", return_value=False):
            with patch("server.services.agent_session_factory._get_sqlite_agent_db_path", return_value=":memory:"):
                session = await create_agent_session("test-notebook-123")

                assert session is not None
                assert session.session_id == "test-notebook-123"

    @pytest.mark.asyncio
    async def test_creates_postgresql_session_in_hosted_mode(self):
        mock_backend = MagicMock()
        mock_backend.get_items = AsyncMock(return_value=[])
        mock_backend.add_items = AsyncMock()
        mock_backend.clear_session = AsyncMock()

        with patch("server.services.agent_session_factory.is_self_hosted", return_value=True):
            with patch(
                "server.services.agent_session_factory._create_postgresql_backend",
                return_value=mock_backend,
            ):
                session = await create_agent_session("test-notebook-456")

                assert session is not None
                assert session.session_id == "test-notebook-456"

    def test_sync_creates_sqlite_in_local_mode(self):
        with patch("server.services.agent_session_factory.is_self_hosted", return_value=False):
            with patch("server.services.agent_session_factory._get_sqlite_agent_db_path", return_value=":memory:"):
                session = create_agent_session_sync("test-notebook-789")

                assert session is not None
                assert session.session_id == "test-notebook-789"

    def test_sync_warns_and_falls_back_in_hosted_mode(self):
        with patch("server.services.agent_session_factory.is_self_hosted", return_value=True):
            with patch("server.services.agent_session_factory._get_sqlite_agent_db_path", return_value=":memory:"):
                with patch("server.services.agent_session_factory.logger") as mock_logger:
                    session = create_agent_session_sync("test-notebook-sync")

                    mock_logger.warning.assert_called_once()
                    assert session is not None


class TestBackendInfo:
    def test_backend_info_local_mode(self):
        with patch("server.services.agent_session_factory.is_self_hosted", return_value=False):
            with patch("server.services.agent_session_factory._get_sqlite_agent_db_path", return_value=".data/test.db"):
                info = get_session_backend_info()

                assert info["backend"] == "sqlite"
                assert info["engine"] == "SQLiteSession"
                assert "database_path" in info

    def test_backend_info_hosted_mode(self):
        with patch("server.services.agent_session_factory.is_self_hosted", return_value=True):
            info = get_session_backend_info()

            assert info["backend"] == "postgresql"
            assert info["engine"] == "SQLAlchemySession"


@pytest.mark.asyncio
class TestSessionOperations:
    async def test_session_add_and_get_items_sqlite(self):
        with patch("server.services.agent_session_factory.is_self_hosted", return_value=False):
            with patch("server.services.agent_session_factory._get_sqlite_agent_db_path", return_value=":memory:"):
                session = await create_agent_session("test-ops-sqlite")

                items = [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there!"},
                ]
                await session.add_items(items)

                retrieved = await session.get_items()
                assert len(retrieved) == 2

    async def test_session_clear_sqlite(self):
        with patch("server.services.agent_session_factory.is_self_hosted", return_value=False):
            with patch("server.services.agent_session_factory._get_sqlite_agent_db_path", return_value=":memory:"):
                session = await create_agent_session("test-clear-sqlite")

                await session.add_items([{"role": "user", "content": "Test"}])
                await session.clear_session()

                retrieved = await session.get_items()
                assert len(retrieved) == 0

    async def test_blocked_tools_are_filtered(self):
        with patch("server.services.agent_session_factory.is_self_hosted", return_value=False):
            with patch("server.services.agent_session_factory._get_sqlite_agent_db_path", return_value=":memory:"):
                session = await create_agent_session("test-filter")

                items = [
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {
                                    "name": "get_existing_html",
                                    "arguments": '{"dashboard_id": "123"}',
                                },
                            }
                        ],
                    }
                ]
                await session.add_items(items)

                retrieved = await session.get_items()
                assert len(retrieved) == 1
                tool_call = retrieved[0]["tool_calls"][0]
                assert tool_call["function"]["arguments"] == "{}"
