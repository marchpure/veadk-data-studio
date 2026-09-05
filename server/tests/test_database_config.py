from server.utils.database_config import async_connect_args, async_database_url, sync_database_url


def test_sync_database_url_translates_boolean_ssl_query() -> None:
    url = "postgresql+asyncpg://user:pass@db.example.test/app?ssl=true&application_name=studio"

    assert sync_database_url(url) == (
        "postgresql://user:pass@db.example.test/app?"
        "sslmode=require&application_name=studio"
    )


def test_sync_database_url_translates_false_ssl_query() -> None:
    url = "postgresql+asyncpg://user:pass@db.example.test/app?ssl=false"

    assert sync_database_url(url) == "postgresql://user:pass@db.example.test/app?sslmode=disable"


def test_sync_database_url_preserves_explicit_sslmode() -> None:
    url = "postgresql+asyncpg://user:pass@db.example.test/app?ssl=true&sslmode=verify-full"

    assert sync_database_url(url) == "postgresql://user:pass@db.example.test/app?ssl=true&sslmode=verify-full"


def test_async_database_url_moves_disable_ssl_to_connect_args() -> None:
    url = (
        "postgresql+asyncpg://user:pass@db.example.test/app?"
        "sslmode=disable&options=-csearch_path%3Ddata_studio"
    )

    assert async_database_url(url) == "postgresql+asyncpg://user:pass@db.example.test/app"
    assert async_connect_args(url)["ssl"] is False


def test_openviking_repository_accepts_asyncpg_postgres_url(monkeypatch) -> None:
    import sys
    import types

    captured = {}

    class Connection:
        autocommit = False

        def cursor(self, **_kwargs):
            class Cursor:
                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return None

                def execute(self, *_args):
                    return None

                def fetchone(self):
                    return (
                        "openviking_profiles",
                        "openviking_task_history",
                        "openviking_idempotency",
                        "openviking_resource_refs",
                    )

            return Cursor()

        def commit(self):
            return None

    module = types.SimpleNamespace(
        connect=lambda url, **kwargs: captured.update(url=url, kwargs=kwargs) or Connection()
    )
    monkeypatch.setitem(sys.modules, "psycopg2", module)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", types.SimpleNamespace(RealDictCursor=object))
    monkeypatch.setenv("DWV1_DATABASE_SCHEMA", "data_studio")

    from server.services.openviking_service import OpenVikingProfileRepository

    OpenVikingProfileRepository("postgresql+asyncpg://user:pass@db.example.test/app?sslmode=disable")
    assert captured["url"].startswith("postgresql://user:pass@db.example.test/app")
