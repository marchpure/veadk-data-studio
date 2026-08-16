from __future__ import annotations

from server.utils.error_sanitizer import sanitize_error_message, sanitize_error_payload

SENSITIVE_VALUES = [
    "plain-password",
    "argon2id-verifier",
    "raw-token",
    "worker-credential",
    "select * from other_tenant.secret_orders",
]


def _assert_no_sensitive_values(value: object) -> None:
    text = str(value)
    for sensitive in SENSITIVE_VALUES:
        assert sensitive not in text


def test_sanitize_error_message_redacts_share_and_sql_sensitive_values() -> None:
    error = RuntimeError(
        "worker failed password=plain-password verifier=argon2id-verifier "
        "token=raw-token credential=worker-credential sql=select * from other_tenant.secret_orders"
    )

    sanitized = sanitize_error_message(error)

    _assert_no_sensitive_values(sanitized)
    assert sanitized.count("[REDACTED]") >= 5


def test_sanitize_error_payload_redacts_nested_values_and_sensitive_keys() -> None:
    payload = {
        "password": "plain-password",
        "meta": {
            "verifier": "argon2id-verifier",
            "token": "raw-token",
            "credential": "worker-credential",
            "sql": "select * from other_tenant.secret_orders",
            "safe": "kept",
        },
        "items": [{"raw_token": "raw-token"}],
    }

    sanitized = sanitize_error_payload(payload)

    _assert_no_sensitive_values(sanitized)
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["meta"]["safe"] == "kept"
    assert sanitized["items"][0]["raw_token"] == "[REDACTED]"
