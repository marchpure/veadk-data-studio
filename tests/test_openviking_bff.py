import asyncio
import base64
import json

import httpx
import pytest

import server.services.openviking_service as openviking_module
from server.services.openviking_service import (
    OpenVikingConfig,
    OpenVikingError,
    OpenVikingProfileRepository,
    OpenVikingService,
    _sanitize,
)

REAL_ASYNC_CLIENT = httpx.AsyncClient


def service(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENVIKING_ALLOW_LOOPBACK", "1")
    key = base64.urlsafe_b64encode(b"k" * 32).decode()
    return OpenVikingService(
        OpenVikingProfileRepository(tmp_path / "profiles.sqlite3"),
        OpenVikingConfig(base64.urlsafe_b64decode(key), 1, True),
    )


def test_profile_secret_is_encrypted_and_masked(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "owner", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    public = value.public(profile)
    assert public["api_key_masked"]
    assert "secret-key" not in str(public)
    row = value.repository.get(profile.profile_id, "tenant", "workspace", "owner")
    assert row is not None
    assert b"secret-key" not in row.encrypted_api_key


def test_operation_allowlist_rejects_untrusted_operation(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "owner", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    with pytest.raises(OpenVikingError, match="not allowed"):
        asyncio.run(value.request(profile, "arbitrary", {}))


def test_refs_are_validated_and_nested_secrets_are_redacted(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "owner", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    with pytest.raises(OpenVikingError, match="signed Viking"):
        asyncio.run(value.request(profile, "fs_stat", {"resource_ref": "https://outside.example/item"}))
    assert _sanitize({"nested": {"token": "secret", "ok": 1}, "items": [{"api_key": "secret"}]}) == {
        "nested": {"ok": 1}, "items": [{}]
    }


def test_operation_payload_allowlist_and_idempotency_store(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "owner", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    with pytest.raises(OpenVikingError, match="Unsupported"):
        asyncio.run(value.request(profile, "fs_stat", {"resource_ref": "viking://resources/", "arbitrary": True}))
    value.repository.save_idempotent("k", {"status": "submitted"})
    assert value.repository.get_idempotent("k") == {"status": "submitted"}


def test_donor_retrieval_fields_are_forwarded(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "owner", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"status": "ok", "result": []})

    _mock_client(monkeypatch, handler)
    common = {
        "query": "needle",
        "include_provenance": False,
        "time_field": "updated_at",
        "context_type": ["resource"],
        "level": [0, 1],
        "filter": {"category": "docs"},
        "telemetry": False,
    }
    asyncio.run(value.request(profile, "find", common))
    asyncio.run(value.request(profile, "search", {**common, "session_id": "session-1"}))

    assert calls[0] == common
    assert calls[1] == {**common, "session_id": "session-1"}


def test_profile_repository_is_tenant_and_owner_scoped(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "owner-a", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    assert value.repository.get(profile.profile_id, "tenant", "workspace", "owner-a") == profile
    assert value.repository.get(profile.profile_id, "tenant", "workspace", "owner-b") is None
    assert value.repository.get(profile.profile_id, "other", "workspace", "owner-a") is None
    assert value.repository.list("tenant", "workspace", "owner-b") == []


def test_resource_refs_are_opaque_and_profile_scoped(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    first = value.create("tenant", "workspace", "owner", "First", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    second = value.create("tenant", "workspace", "owner", "Second", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    ref = value.resource_ref(first, "viking://resources/docs/readme.md")
    assert ref.startswith("ovr_")
    assert "viking://resources" not in ref
    assert value.resolve_ref(first, ref) == "viking://resources/docs/readme.md"
    with pytest.raises(OpenVikingError, match="invalid"):
        value.resolve_ref(second, ref)
    with pytest.raises(OpenVikingError, match="invalid"):
        value.resolve_ref(first, ref[:-1] + ("0" if ref[-1] != "0" else "1"))


def test_upstream_refs_and_sensitive_fields_are_recursively_sanitized(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "owner", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    safe = value._sanitize_upstream(profile, {
        "result": [{"uri": "viking://resources/docs/readme.md", "owner": "hidden"}],
        "nested": {"token": "hidden", "path": "/tmp/upstream-secret/file.txt"},
    })
    serialized = json.dumps(safe)
    assert safe["result"][0]["resource_ref"].startswith("ovr_")
    assert safe["result"][0]["uri"] == "viking://workspace/docs/readme.md"
    assert safe["nested"]["path"] == "file.txt"
    assert all(word not in serialized for word in ("hidden", "/tmp/upstream-secret"))


def test_upstream_global_context_is_an_opaque_profile_capability(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "owner", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    safe = value._sanitize_upstream(profile, {
        "uri": "viking://user/memories/preference-1",
        "abstract": "Preferred output format",
    })

    assert safe["resource_ref"].startswith("ovr_")
    assert value.resolve_ref(profile, safe["resource_ref"]) == "viking://user/memories/preference-1"
    with pytest.raises(OpenVikingError, match="outside workspace"):
        value.resource_ref(profile, "viking://user/memories/preference-1")


def test_watch_and_task_display_uris_keep_their_original_field(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "owner", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    safe = value._sanitize_upstream(profile, {
        "to_uri": "viking://resources/watch",
        "resource_id": "viking://resources/task.md",
    })
    assert safe["to_uri"] == "viking://workspace/watch"
    assert safe["to_ref"].startswith("ovr_")
    assert safe["resource_id"] == "viking://workspace/task.md"
    assert safe["resource_id_ref"].startswith("ovr_")


def test_file_and_url_validation_fail_closed(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "owner", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    root = value.resource_ref(profile, profile.workspace_uri)
    with pytest.raises(OpenVikingError, match="HTTPS"):
        value.validate_import_url("http://example.com")
    with pytest.raises(OpenVikingError, match="filename"):
        asyncio.run(value.upload(profile, "../secret.txt", "text/plain", b"value", root))
    with pytest.raises(OpenVikingError, match="malformed"):
        asyncio.run(value.upload(profile, "bad.json", "application/json", b"{", root))
    with pytest.raises(OpenVikingError, match="Manual text"):
        asyncio.run(value.import_text(profile, "note.pdf", "value", root))


def test_import_url_rejects_private_network_resolution(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    monkeypatch.setattr(
        openviking_module.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (openviking_module.socket.AF_INET, openviking_module.socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443)),
        ],
    )

    with pytest.raises(OpenVikingError) as raised:
        value.validate_import_url("https://internal.example/resource")

    assert raised.value.code == "SSRF_BLOCKED"
    assert raised.value.status_code == 422


def test_upload_rejects_unsupported_and_oversized_files(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "owner", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    root = value.resource_ref(profile, profile.workspace_uri)

    with pytest.raises(OpenVikingError) as unsupported:
        asyncio.run(value.upload(profile, "payload.exe", "application/octet-stream", b"value", root))
    assert unsupported.value.code == "UNSUPPORTED_FILE_TYPE"
    assert unsupported.value.status_code == 415

    monkeypatch.setattr(openviking_module, "MAX_UPLOAD_BYTES", 4)
    with pytest.raises(OpenVikingError) as oversized:
        asyncio.run(value.upload(profile, "payload.txt", "text/plain", b"value", root))
    assert oversized.value.code == "PAYLOAD_TOO_LARGE"
    assert oversized.value.status_code == 413


def _mock_client(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        openviking_module.httpx,
        "AsyncClient",
        lambda *args, **kwargs: REAL_ASYNC_CLIENT(transport=transport),
    )


@pytest.mark.parametrize(
    ("status_code", "expected_code", "expected_status"),
    [
        (401, "OPENVIKING_AUTH_FAILED", 401),
        (403, "OPENVIKING_AUTH_FAILED", 401),
        (404, "OPENVIKING_NOT_FOUND", 404),
        (429, "OPENVIKING_RATE_LIMITED", 429),
        (500, "OPENVIKING_UPSTREAM_ERROR", 502),
    ],
)
def test_upstream_status_mapping(tmp_path, monkeypatch, status_code, expected_code, expected_status):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "owner", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    root = value.resource_ref(profile, profile.workspace_uri)
    _mock_client(monkeypatch, lambda request: httpx.Response(status_code, json={"detail": "must not leak"}))
    with pytest.raises(OpenVikingError) as raised:
        asyncio.run(value.request(profile, "fs_stat", {"resource_ref": root}))
    assert raised.value.code == expected_code
    assert raised.value.status_code == expected_status
    assert "must not leak" not in str(raised.value)


def test_timeout_and_two_stage_import_are_stable(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "owner", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    root = value.resource_ref(profile, profile.workspace_uri)
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/temp_upload"):
            return httpx.Response(200, json={"result": {"temp_file_id": "temp_123"}})
        return httpx.Response(200, json={"status": "ok", "result": {"task_id": "task_123"}})

    _mock_client(monkeypatch, handler)
    result = asyncio.run(value.import_text(profile, "note.md", "safe text", root))
    assert result["result"]["task_id"] == "task_123"
    assert [request.url.path for request in calls] == [
        "/api/v1/resources/temp_upload",
        "/api/v1/resources",
    ]

    def timeout_handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    _mock_client(monkeypatch, timeout_handler)
    with pytest.raises(OpenVikingError) as raised:
        asyncio.run(value.request(profile, "fs_stat", {"resource_ref": root}))
    assert raised.value.code == "OPENVIKING_TIMEOUT"
    assert raised.value.status_code == 504


def test_idempotent_write_only_calls_upstream_once(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "owner", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    root = value.resource_ref(profile, profile.workspace_uri)
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"status": "ok", "result": {"task_id": "task_123"}})

    _mock_client(monkeypatch, handler)
    payload = {"path": "https://example.com", "parent_ref": root, "wait": False}
    first = asyncio.run(value.request(profile, "resource_import", payload))
    second = asyncio.run(value.request(profile, "resource_import", payload))
    assert first == second
    assert calls == 1
