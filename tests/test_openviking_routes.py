import base64
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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
    service.repository.save(
        type(profile)(**{**profile.__dict__, "status": "ready"})
    )

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
    service.repository.save(
        type(profile)(**{**profile.__dict__, "status": "ready"})
    )

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
