import base64
import socket
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import server.routers.openviking as routes
from server.routers.openviking import ContextRequest, OperationRequest, ProfileCreate
from server.services.openviking_service import (
    OpenVikingConfig,
    OpenVikingProfileRepository,
    OpenVikingService,
)


def _auth(tenant: str, user: str, *, writable: bool = True):
    return SimpleNamespace(
        tenant_id=tenant,
        user_id=user,
        has_scope=lambda _scope: writable,
    )


def _service(tmp_path) -> OpenVikingService:
    return OpenVikingService(
        OpenVikingProfileRepository(tmp_path / "profiles.sqlite3"),
        OpenVikingConfig(base64.urlsafe_b64decode(base64.urlsafe_b64encode(b"k" * 32))),
    )


@pytest.mark.asyncio
async def test_profile_routes_use_standard_envelope_and_owner_scope(tmp_path, monkeypatch):
    service = _service(tmp_path)
    monkeypatch.setattr(routes, "_service", lambda: service)
    monkeypatch.setenv("OPENVIKING_CREDENTIAL_POLICY", "byok")
    monkeypatch.setattr(socket, "gethostbyname", lambda _host: "8.8.8.8")
    owner = _auth("tenant-a", "owner-a")

    created = await routes.create_profile(
        ProfileCreate(
            display_name="Hosted",
            base_url="https://api.vikingdb.cn-beijing.volces.com/openviking",
            api_key="secret-key",
            workspace_uri="viking://resources/",
        ),
        owner,
    )
    profile_id = created["data"]["profile_id"]

    assert created["success"] is True
    assert created["data"]["status"] == "pending"
    assert "secret-key" not in str(created)
    assert (await routes.list_profiles(owner))["data"][0]["profile_id"] == profile_id
    assert (await routes.list_profiles(_auth("tenant-a", "owner-b")))["data"] == []

    with pytest.raises(HTTPException) as hidden:
        routes._get_profile(service, profile_id, _auth("tenant-a", "owner-b"))
    assert hidden.value.status_code == 404


@pytest.mark.asyncio
async def test_public_profile_and_upstream_payload_never_expose_viking_uri(tmp_path, monkeypatch):
    service = _service(tmp_path)
    profile = service.create(
        "tenant-a",
        "tenant:tenant-a",
        "owner-a",
        "Hosted",
        "https://api.vikingdb.cn-beijing.volces.com/openviking",
        "secret-key",
        "viking://resources/",
    )
    public = service.public(profile)
    assert public["workspace_uri"] == f"viking://workspace/{profile.profile_id}/"
    assert "viking://resources/" not in str(public)
    sanitized = service._sanitize_upstream(
        profile,
        {"uri": "viking://resources/readme.md", "display_uri": "viking://resources/readme.md"},
    )
    assert "viking://" not in str(sanitized)
    assert "display_uri" not in sanitized


@pytest.mark.asyncio
async def test_skill_context_rejects_unsigned_resource_ref(tmp_path, monkeypatch):
    service = _service(tmp_path)
    monkeypatch.setattr(routes, "_service", lambda: service)
    auth = _auth("tenant-a", "owner-a")
    profile = service.create(
        "tenant-a",
        "tenant:tenant-a",
        "owner-a",
        "Hosted",
        "https://api.vikingdb.cn-beijing.volces.com/openviking",
        "secret-key",
        "viking://resources/",
    )
    service.repository.save(type(profile)(**{**profile.__dict__, "status": "ready"}))

    with pytest.raises(HTTPException) as rejected:
        await routes.skill_context(
            profile.profile_id,
            ContextRequest(resource_ref="viking://resources/private"),
            auth,
        )
    assert rejected.value.status_code == 422
    assert rejected.value.detail["code"] == "INVALID_RESOURCE_REF"


@pytest.mark.asyncio
async def test_revoked_profile_hides_previously_issued_resource_ref(tmp_path, monkeypatch):
    service = _service(tmp_path)
    monkeypatch.setattr(routes, "_service", lambda: service)
    auth = _auth("tenant-a", "owner-a")
    profile = service.create(
        "tenant-a",
        "tenant:tenant-a",
        "owner-a",
        "Hosted",
        "https://api.vikingdb.cn-beijing.volces.com/openviking",
        "secret-key",
        "viking://resources/",
    )
    resource_ref = service.resource_ref(profile, "viking://resources/document.md")
    service.repository.delete(
        profile.profile_id,
        profile.tenant_id,
        profile.workspace_id,
        profile.principal_id,
    )

    with pytest.raises(HTTPException) as rejected:
        await routes.skill_context(
            profile.profile_id,
            ContextRequest(resource_ref=resource_ref),
            auth,
        )
    assert rejected.value.status_code == 404


@pytest.mark.asyncio
async def test_write_operation_requires_write_scope(tmp_path, monkeypatch):
    service = _service(tmp_path)
    monkeypatch.setattr(routes, "_service", lambda: service)
    auth = _auth("tenant-a", "owner-a", writable=False)
    profile = service.create(
        "tenant-a",
        "tenant:tenant-a",
        "owner-a",
        "Hosted",
        "https://api.vikingdb.cn-beijing.volces.com/openviking",
        "secret-key",
        "viking://resources/",
    )
    service.repository.save(type(profile)(**{**profile.__dict__, "status": "ready"}))

    with pytest.raises(HTTPException) as rejected:
        await routes.operation(
            profile.profile_id,
            "resource_import",
            OperationRequest(payload={}),
            auth,
        )
    assert rejected.value.status_code == 403


def test_missing_encryption_key_is_stable_configuration_error(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENVIKING_PROFILE_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("OPENVIKING_PROFILE_DATABASE", str(tmp_path / "profiles.sqlite3"))

    with pytest.raises(HTTPException) as unavailable:
        routes._service()

    assert unavailable.value.status_code == 503
    assert unavailable.value.detail["code"] == "OPENVIKING_UNAVAILABLE"
    assert "BLOCKED_UPSTREAM" not in str(unavailable.value.detail)


def test_profile_create_rejects_missing_api_key():
    with pytest.raises(ValidationError):
        ProfileCreate(
            display_name="Hosted",
            base_url="https://api.vikingdb.cn-beijing.volces.com/openviking",
            api_key="",
            workspace_uri="viking://resources/",
        )


@pytest.mark.asyncio
async def test_byok_policy_is_independent_of_external_oidc(tmp_path, monkeypatch):
    value = _service(tmp_path)
    monkeypatch.setattr(routes, "_service", lambda: value)
    monkeypatch.setattr(routes, "external_oidc_enabled", lambda: True)
    monkeypatch.setenv("OPENVIKING_CREDENTIAL_POLICY", "byok")
    monkeypatch.setattr(socket, "gethostbyname", lambda _host: "8.8.8.8")

    created = await routes.create_profile(
        ProfileCreate(
            credential_mode="byok",
            display_name="自有知识库",
            base_url="https://openviking.example.test",
            api_key="one-time-secret",
            workspace_uri="viking://resources/team/",
        ),
        _auth("tenant-a", "owner-a"),
    )

    assert created["data"]["credential_mode"] == "byok"
    assert created["data"]["workspace_uri"].startswith("viking://workspace/")
    assert "one-time-secret" not in str(created)
    assert "openviking.example.test" not in str(created)


@pytest.mark.asyncio
async def test_managed_policy_uses_only_server_credentials(tmp_path, monkeypatch):
    value = _service(tmp_path)
    monkeypatch.setattr(routes, "_service", lambda: value)
    monkeypatch.setenv("OPENVIKING_CREDENTIAL_POLICY", "managed")
    monkeypatch.setenv("OPENVIKING_MANAGED_BASE_URL", "https://managed.example.test")
    monkeypatch.setenv("DWV1_ALLOW_ENV_SECRETS", "true")
    monkeypatch.setenv("OPENVIKING_API_KEY", "server-managed-secret")
    monkeypatch.setattr(socket, "gethostbyname", lambda _host: "8.8.8.8")

    created = await routes.create_profile(
        routes.ManagedProfileCreate(
            display_name="托管知识库",
            workspace_uri="viking://resources/",
        ),
        _auth("tenant-a", "owner-a"),
    )

    assert created["data"]["credential_mode"] == "managed"
    assert "server-managed-secret" not in str(created)
    assert "managed.example.test" not in str(created)


@pytest.mark.asyncio
async def test_hybrid_policy_creates_managed_and_byok_profiles(tmp_path, monkeypatch):
    value = _service(tmp_path)
    monkeypatch.setattr(routes, "_service", lambda: value)
    monkeypatch.setenv("OPENVIKING_CREDENTIAL_POLICY", "hybrid")
    monkeypatch.setenv("OPENVIKING_MANAGED_BASE_URL", "https://managed.example.test")
    monkeypatch.setenv("DWV1_ALLOW_ENV_SECRETS", "true")
    monkeypatch.setenv("OPENVIKING_API_KEY", "server-managed-secret")
    monkeypatch.setattr(socket, "gethostbyname", lambda _host: "8.8.8.8")
    auth = _auth("tenant-a", "owner-a")

    managed = await routes.create_profile(
        routes.ManagedProfileCreate(
            credential_mode="managed",
            display_name="托管知识库",
            workspace_uri="viking://resources/",
        ),
        auth,
    )
    byok = await routes.create_profile(
        ProfileCreate(
            credential_mode="byok",
            display_name="自有知识库",
            base_url="https://openviking.example.test",
            api_key="one-time-secret",
            workspace_uri="viking://resources/",
        ),
        auth,
    )

    assert managed["data"]["credential_mode"] == "managed"
    assert byok["data"]["credential_mode"] == "byok"
    assert "server-managed-secret" not in str(managed)
    assert "one-time-secret" not in str(byok)


@pytest.mark.asyncio
async def test_byok_rotation_does_not_echo_the_new_key(tmp_path, monkeypatch):
    value = _service(tmp_path)
    monkeypatch.setattr(routes, "_service", lambda: value)
    monkeypatch.setenv("OPENVIKING_CREDENTIAL_POLICY", "byok")
    monkeypatch.setattr(socket, "gethostbyname", lambda _host: "8.8.8.8")
    auth = _auth("tenant-a", "owner-a")
    created = await routes.create_profile(
        ProfileCreate(
            credential_mode="byok",
            display_name="自有知识库",
            base_url="https://openviking.example.test",
            api_key="first-secret",
            workspace_uri="viking://resources/",
        ),
        auth,
    )

    updated = await routes.update_profile(
        created["data"]["profile_id"],
        routes.ProfileUpdate(api_key="rotated-secret"),
        auth,
    )

    assert updated["data"]["credential_mode"] == "byok"
    assert "rotated-secret" not in str(updated)
    assert "openviking.example.test" not in str(updated)


@pytest.mark.asyncio
async def test_managed_policy_rejects_browser_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(routes, "_service", lambda: _service(tmp_path))
    monkeypatch.setenv("OPENVIKING_CREDENTIAL_POLICY", "managed")

    with pytest.raises(HTTPException) as rejected:
        await routes.create_profile(
            ProfileCreate(
                display_name="托管知识库",
                base_url="https://attacker.example.test",
                api_key="must-not-be-accepted",
                workspace_uri="viking://resources/",
            ),
            _auth("tenant-a", "owner-a"),
        )

    assert rejected.value.status_code == 400
    assert "must-not-be-accepted" not in str(rejected.value.detail)


def test_hybrid_policy_requires_an_explicit_profile_credential_mode(monkeypatch):
    monkeypatch.setenv("OPENVIKING_CREDENTIAL_POLICY", "hybrid")

    with pytest.raises(HTTPException) as rejected:
        routes._profile_credentials(
            {
                "display_name": "Hybrid",
                "workspace_uri": "viking://resources/",
            }
        )

    assert rejected.value.status_code == 400
