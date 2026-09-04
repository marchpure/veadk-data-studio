import base64
import asyncio
import json

import pytest

from server.services.openviking_service import (
    OpenVikingConfig,
    OpenVikingError,
    OpenVikingProfileRepository,
    OpenVikingService,
    _sanitize,
)


def service(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENVIKING_ALLOW_LOOPBACK", "1")
    key = base64.urlsafe_b64encode(b"k" * 32).decode()
    return OpenVikingService(
        OpenVikingProfileRepository(tmp_path / "profiles.sqlite3"),
        OpenVikingConfig(base64.urlsafe_b64decode(key), 1, True),
    )


def test_profile_secret_is_encrypted_and_masked(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    public = value.public(profile)
    assert public["api_key_masked"]
    assert "secret-key" not in str(public)
    row = value.repository.get(profile.profile_id, "tenant", "workspace")
    assert row is not None
    assert b"secret-key" not in row.encrypted_api_key


def test_operation_allowlist_rejects_untrusted_operation(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    with pytest.raises(OpenVikingError, match="not allowed"):
        asyncio.run(value.request(profile, "arbitrary", {}))


def test_refs_are_validated_and_nested_secrets_are_redacted(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    with pytest.raises(OpenVikingError, match="signed Viking"):
        asyncio.run(value.request(profile, "fs_stat", {"resource_ref": "https://outside.example/item"}))
    assert _sanitize({"nested": {"token": "secret", "ok": 1}, "items": [{"api_key": "secret"}]}) == {
        "nested": {"ok": 1}, "items": [{}]
    }


def test_operation_payload_allowlist_and_idempotency_store(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    with pytest.raises(OpenVikingError, match="Unsupported"):
        asyncio.run(value.request(profile, "fs_stat", {"resource_ref": "viking://resources/", "arbitrary": True}))
    value.repository.save_idempotent("k", {"status": "submitted"})
    assert value.repository.get_idempotent("k") == {"status": "submitted"}


def test_resource_refs_are_opaque_profile_scoped_and_upstream_refs_are_sanitized(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    first = value.create("tenant", "workspace", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    second = value.create("tenant", "workspace", "Other", "http://127.0.0.1:9000", "other-key", "viking://resources/")
    ref = value.resource_ref(first, "viking://resources/docs/readme.md")
    assert ref.startswith("ovr_")
    assert "viking://resources" not in ref
    assert value.resolve_ref(first, ref) == "viking://resources/docs/readme.md"
    with pytest.raises(OpenVikingError, match="invalid"):
        value.resolve_ref(second, ref)
    safe = value._sanitize_upstream(first, {
        "uri": "viking://resources/docs/readme.md",
        "nested": {"token": "hidden", "owner": "hidden"},
    })
    assert safe["resource_ref"] == ref
    assert safe["uri"] == "viking://workspace/docs/readme.md"
    assert "token" not in json.dumps(safe)


def test_import_validation_and_text_contract(tmp_path, monkeypatch):
    value = service(tmp_path, monkeypatch)
    profile = value.create("tenant", "workspace", "Hosted", "http://127.0.0.1:9000", "secret-key", "viking://resources/")
    root = value.resource_ref(profile, profile.workspace_uri)
    with pytest.raises(OpenVikingError, match="HTTPS"):
        value.validate_import_url("http://example.com")
    with pytest.raises(OpenVikingError, match="Manual text"):
        asyncio.run(value.import_text(profile, "note.pdf", "text", root))
