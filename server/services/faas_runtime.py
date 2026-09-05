"""Request-scoped credentials and lazy-start helpers for VeFaaS Web functions."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import Request


@dataclass(frozen=True)
class FaaSCredentials:
    """Short-lived STS credentials injected by VeFaaS for one request."""

    access_key_id: str
    secret_access_key: str
    session_token: str

    def credential_provider(self):
        from volcenginesdkcore.auth.providers import StaticCredentialProvider

        return StaticCredentialProvider(
            self.access_key_id,
            self.secret_access_key,
            self.session_token,
        )


_credentials: ContextVar[FaaSCredentials | None] = ContextVar("faas_credentials", default=None)


def get_faas_credentials() -> FaaSCredentials | None:
    return _credentials.get()


def deferred_runtime_enabled() -> bool:
    """Return true for the cloud function path receiving credentials per request."""

    return (
        os.getenv("DWV1_EXTERNAL_OIDC_ENABLED", "").strip().lower() in {"1", "true", "yes"}
        and bool(os.getenv("VOLCENGINE_OIDC_ROLE_TRN", "").strip())
    )


@contextmanager
def request_faas_credentials(request: Request) -> Iterator[None]:
    """Expose platform-injected credentials only while handling this request."""

    access_key_id = request.headers.get("x-faas-access-key-id", "").strip()
    secret_access_key = request.headers.get("x-faas-secret-access-key", "").strip()
    session_token = request.headers.get("x-faas-session-token", "").strip()
    credentials = (
        FaaSCredentials(access_key_id, secret_access_key, session_token)
        if access_key_id and secret_access_key and session_token
        else None
    )
    token = _credentials.set(credentials)
    try:
        yield
    finally:
        _credentials.reset(token)
