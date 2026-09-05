from __future__ import annotations

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
