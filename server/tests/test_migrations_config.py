from server.utils.migrations import _alembic_config_value


def test_alembic_config_value_escapes_percent_encoded_password() -> None:
    value = "postgresql://user:encoded%21password@db.example.test/app?sslmode=disable"

    assert _alembic_config_value(value) == (
        "postgresql://user:encoded%%21password@db.example.test/app?sslmode=disable"
    )
