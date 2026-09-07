from __future__ import annotations

import json
from types import SimpleNamespace

from server.services.faas_runtime import (
    FaaSCredentials,
    deferred_runtime_enabled,
    get_faas_credentials,
    request_faas_credentials,
)


def test_request_faas_credentials_is_scoped_to_request(monkeypatch):
    monkeypatch.setenv("DWV1_EXTERNAL_OIDC_ENABLED", "true")
    monkeypatch.setenv("VOLCENGINE_OIDC_ROLE_TRN", "trn:iam::1:role/test")
    request = SimpleNamespace(
        headers={
            "x-faas-access-key-id": "temporary-ak",
            "x-faas-secret-access-key": "temporary-sk",
            "x-faas-session-token": "temporary-session",
        }
    )

    assert deferred_runtime_enabled()
    assert get_faas_credentials() is None
    with request_faas_credentials(request):
        credentials = get_faas_credentials()
        assert credentials == FaaSCredentials("temporary-ak", "temporary-sk", "temporary-session")
    assert get_faas_credentials() is None


def test_incomplete_faas_headers_fail_closed():
    request = SimpleNamespace(
        headers={
            "x-faas-access-key-id": "temporary-ak",
            "x-faas-secret-access-key": "temporary-sk",
        }
    )

    with request_faas_credentials(request):
        assert get_faas_credentials() is None


def test_request_faas_credentials_reads_vefaas_iam_file(tmp_path):
    from server.services import faas_runtime

    path = tmp_path / "credential"
    path.write_text(
        json.dumps(
            {
                "access_key_id": "file-ak",
                "secret_access_key": "file-sk",
                "session_token": "file-session",
            }
        )
    )

    original = faas_runtime._VEFAAS_IAM_CREDENTIAL_PATH
    faas_runtime._VEFAAS_IAM_CREDENTIAL_PATH = path
    try:
        request = SimpleNamespace(headers={})
        with request_faas_credentials(request):
            assert get_faas_credentials() == FaaSCredentials("file-ak", "file-sk", "file-session")
    finally:
        faas_runtime._VEFAAS_IAM_CREDENTIAL_PATH = original


def test_runtime_secret_startup_reads_mounted_iam_credentials(monkeypatch, tmp_path):
    from server.services import faas_runtime, runtime_secrets

    path = tmp_path / "credential"
    path.write_text(
        '{"access_key_id":"ak","secret_access_key":"sk","session_token":"token"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(faas_runtime, "_VEFAAS_IAM_CREDENTIAL_PATH", path)
    monkeypatch.setattr(faas_runtime, "get_faas_credentials", lambda: None)
    captured = {}

    class Provider:
        def credential_provider(self):
            return "provider"

    class FakeConfiguration:
        region = None
        connect_timeout = None
        read_timeout = None
        credential_provider = None

    class FakeApiClient:
        def __init__(self, configuration):
            captured["configuration"] = configuration

    class FakeKms:
        def __init__(self, _client):
            pass

        def get_secret_value(self, _request):
            return type("Response", (), {"secret_value": '{"database_url":"postgresql://db"}'})()

    monkeypatch.setattr(runtime_secrets, "_load_secret_document", runtime_secrets._load_secret_document.__wrapped__)
    monkeypatch.setitem(__import__("sys").modules, "volcenginesdkcore", type("Core", (), {
        "ApiClient": FakeApiClient,
        "Configuration": FakeConfiguration,
    })())
    class SecretRequest:
        def __init__(self, *, secret_name):
            self.secret_name = secret_name

    monkeypatch.setitem(__import__("sys").modules, "volcenginesdkkms", type("Kms", (), {
        "GetSecretValueRequest": SecretRequest,
        "KMSApi": FakeKms,
    })())
    monkeypatch.setattr(faas_runtime, "_read_vefaas_iam_credentials", lambda: Provider())

    assert runtime_secrets._load_secret_document("secret")["database_url"] == "postgresql://db"
    assert captured["configuration"].credential_provider == "provider"
