from server.utils.database_config import sync_database_url


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
