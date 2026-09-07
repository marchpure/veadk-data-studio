from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from server.services import external_oidc
from server.services.runtime_secrets import RuntimeSecretError, get_runtime_secret


def test_callback_uri_requires_final_https_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DWV1_OIDC_PUBLIC_ORIGIN", "https://studio.example.test")
    assert external_oidc.callback_uri() == "https://studio.example.test/api/auth/external/callback"
    monkeypatch.setenv("DWV1_OIDC_PUBLIC_ORIGIN", "http://localhost:8080")
    with pytest.raises(external_oidc.ExternalOIDCError):
        external_oidc.callback_uri()


def test_runtime_secret_does_not_fallback_to_env_in_external_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DWV1_EXTERNAL_OIDC_ENABLED", "true")
    monkeypatch.delenv("DWV1_RUNTIME_SECRET_NAME", raising=False)
    monkeypatch.setenv("APP_SECRET", "must-not-be-used")
    with pytest.raises(RuntimeSecretError):
        get_runtime_secret("app_secret", env_name="APP_SECRET")


def test_runtime_secret_domains_are_independent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DWV1_ALLOW_ENV_SECRETS", "true")
    monkeypatch.setenv("DWV1_EXTERNAL_OIDC_ENABLED", "true")
    monkeypatch.setenv("DATA_STUDIO_SECRET", "studio")
    monkeypatch.setenv("SKILL_SECRET", "skill")
    assert get_runtime_secret("x", env_name="DATA_STUDIO_SECRET") == "studio"
    assert (
        get_runtime_secret("x", env_name="SKILL_SECRET", secret_name_env="DWV1_SKILL_AGENT_SECRET_NAME")
        == "skill"
    )


def test_userpool_group_uid_claim_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DWV1_OIDC_GROUPS_CLAIM", "groups")
    assert external_oidc._groups(
        {"identity_userpool_group_uids": ["group-a", "group-b"], "groups": []}
    ) == ["group-a", "group-b"]


def test_missing_email_uses_non_routable_subject_association(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DWV1_OIDC_ISSUER",
        "https://userpool-f69c17b4-d030-43bc-b4a7-9cae0f6370c3.userpool.auth.id.cn-beijing.volces.com",
    )
    subject = "external-subject"
    address = f"oidc-{external_oidc._hash(f'{external_oidc._issuer()}:{subject}')[:32]}@external.invalid"
    assert address.endswith("@external.invalid")
    assert "external-subject" not in address


def test_jwt_validation_does_not_require_optional_nbf(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class Key:
        key = "public-key"

    class KeyClient:
        def __init__(self, _url: str) -> None:
            pass

        def get_signing_key_from_jwt(self, _token: str) -> Key:
            return Key()

    def decode(_token: str, _key: str, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"sub": "subject", "client_id": "client"}

    monkeypatch.setattr(external_oidc.jwt, "PyJWKClient", KeyClient)
    monkeypatch.setattr(external_oidc.jwt, "decode", decode)
    monkeypatch.setenv("DWV1_OIDC_ISSUER", "https://issuer.example.test")
    monkeypatch.setenv("DWV1_OIDC_CLIENT_ID", "client")

    import asyncio

    claims = asyncio.run(
        external_oidc._verify_jwt(
            "header.payload.signature",
            {"jwks_uri": "https://issuer.example.test/keys"},
            audience="audience",
        )
    )
    assert claims["sub"] == "subject"
    assert captured["options"] == {
        "require": ["exp", "iss", "aud", "sub"],
        "verify_nbf": True,
    }


def test_database_joined_at_timestamp_is_normalized_to_naive_utc() -> None:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    normalized = now.replace(tzinfo=None)
    assert normalized.tzinfo is None
    assert normalized == now.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_external_cookie_context_rejects_missing_session() -> None:
    class Result:
        def one_or_none(self):
            return None

    class Database:
        async def execute(self, _query):
            return Result()

    request = SimpleNamespace(cookies={external_oidc.LOGIN_COOKIE: "opaque-session"})
    with pytest.raises(HTTPException) as error:
        await external_oidc.auth_context_from_cookie(request, Database(), None)
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_external_bearer_context_requires_matching_active_session(monkeypatch) -> None:
    user = SimpleNamespace(id="user-1")
    session = SimpleNamespace(
        subject="subject-1",
        issuer="https://issuer.example.test",
        audience="data-studio-client",
        user_pool="pool-1",
        revoked_at=None,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        encrypted_tokens="encrypted",
        groups='["group-1"]',
    )

    class Result:
        def all(self):
            return [(session, user)]

    class Database:
        async def execute(self, _query):
            return Result()

    monkeypatch.setenv("DWV1_OIDC_ISSUER", session.issuer)
    monkeypatch.setenv("DWV1_OIDC_AUDIENCE", session.audience)
    monkeypatch.setenv("DWV1_OIDC_USER_POOL", session.user_pool)
    monkeypatch.setattr(external_oidc, "_discovery", AsyncMock(return_value={"jwks_uri": "https://issuer/keys"}))
    monkeypatch.setattr(
        external_oidc,
        "_verify_jwt",
        AsyncMock(return_value={"sub": session.subject}),
    )
    monkeypatch.setattr(
        external_oidc.CryptoService,
        "decrypt_config",
        AsyncMock(return_value={"access_token": "verified-user-token"}),
    )
    expected = SimpleNamespace()
    monkeypatch.setattr(external_oidc, "_get_auth_context_hosted", AsyncMock(return_value=expected))

    request = SimpleNamespace(headers={"authorization": "Bearer verified-user-token"}, cookies={})
    result = await external_oidc.auth_context_from_cookie(request, Database(), None)

    assert result is expected
    assert result.external_subject == session.subject
    assert result.external_groups == ("group-1",)
    assert result.access_token == "verified-user-token"


@pytest.mark.asyncio
async def test_external_bearer_context_rejects_token_not_bound_to_session(monkeypatch) -> None:
    user = SimpleNamespace(id="user-1")
    session = SimpleNamespace(
        subject="subject-1",
        issuer="https://issuer.example.test",
        audience="data-studio-client",
        user_pool="pool-1",
        revoked_at=None,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        encrypted_tokens="encrypted",
    )

    class Result:
        def all(self):
            return [(session, user)]

    class Database:
        async def execute(self, _query):
            return Result()

    monkeypatch.setenv("DWV1_OIDC_ISSUER", session.issuer)
    monkeypatch.setenv("DWV1_OIDC_AUDIENCE", session.audience)
    monkeypatch.setenv("DWV1_OIDC_USER_POOL", session.user_pool)
    monkeypatch.setattr(external_oidc, "_discovery", AsyncMock(return_value={"jwks_uri": "https://issuer/keys"}))
    monkeypatch.setattr(
        external_oidc,
        "_verify_jwt",
        AsyncMock(return_value={"sub": session.subject}),
    )
    monkeypatch.setattr(
        external_oidc.CryptoService,
        "decrypt_config",
        AsyncMock(return_value={"access_token": "different-token"}),
    )

    request = SimpleNamespace(headers={"authorization": "Bearer unbound-token"}, cookies={})
    with pytest.raises(HTTPException) as error:
        await external_oidc.auth_context_from_cookie(request, Database(), None)
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_same_origin_frontend_serves_spa_deep_links(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from server.main import serve_frontend

    (tmp_path / "index.html").write_text("<html>studio</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app-ABC123xy.js").write_text("console.log('studio')")
    (tmp_path / "config.js").write_text("window.__RUNTIME_CONFIG__ = {}")
    monkeypatch.setenv("DWV1_FRONTEND_DIST", str(tmp_path))

    deep_link = await serve_frontend("connections/docs")
    index = await serve_frontend("index.html")
    config = await serve_frontend("config.js")
    asset = await serve_frontend("assets/app-ABC123xy.js")
    api_path = await serve_frontend("api/unknown")

    assert deep_link.path == tmp_path / "index.html"
    assert deep_link.headers["cache-control"] == "no-store, must-revalidate"
    assert index.headers["cache-control"] == "no-store, must-revalidate"
    assert config.headers["cache-control"] == "no-store, must-revalidate"
    assert asset.path == tmp_path / "assets" / "app-ABC123xy.js"
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert api_path.status_code == 404
