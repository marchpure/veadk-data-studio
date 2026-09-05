from __future__ import annotations

from types import SimpleNamespace

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
async def test_same_origin_frontend_serves_spa_deep_links(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from server.main import serve_frontend

    (tmp_path / "index.html").write_text("<html>studio</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('studio')")
    monkeypatch.setenv("DWV1_FRONTEND_DIST", str(tmp_path))

    deep_link = await serve_frontend("connections/docs")
    asset = await serve_frontend("assets/app.js")
    api_path = await serve_frontend("api/unknown")

    assert deep_link.path == tmp_path / "index.html"
    assert asset.path == tmp_path / "assets" / "app.js"
    assert api_path.status_code == 404
