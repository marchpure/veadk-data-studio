from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.schemas.standard_response import success_response
from server.services.external_oidc import enabled as external_oidc_enabled
from server.services.openviking_access import (
    ROLE_ACTIONS,
    OpenVikingAccessGrant,
    authorize,
    grant_view,
)
from server.services.openviking_service import (
    OpenVikingConfig,
    OpenVikingError,
    OpenVikingProfile,
    OpenVikingProfileRepository,
    OpenVikingService,
    openviking_credential_policy,
)
from server.services.runtime_secrets import RuntimeSecretError, get_runtime_secret
from server.services.source_resources import SourceResourceService

router = APIRouter(prefix="/knowledge/openviking", tags=["openviking"])
source_resource_service = SourceResourceService()


def _service() -> OpenVikingService:
    database = os.getenv("OPENVIKING_PROFILE_DATABASE")
    if not database and external_oidc_enabled():
        try:
            database = get_runtime_secret("database_url")
        except RuntimeSecretError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "BLOCKED_CONFIG", "message": "Data Studio database is not configured"},
            ) from exc
    if not database:
        data_dir = Path(os.getenv("DATA_DIR", ".data"))
        database = str(data_dir / "openviking-profiles.sqlite3")
    try:
        config = OpenVikingConfig.from_env()
    except OpenVikingError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    return OpenVikingService(OpenVikingProfileRepository(database), config)


class ProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=2048)
    api_key: str = Field(min_length=1, max_length=4096)
    credential_mode: Literal["byok"] | None = None
    workspace_uri: str = Field(default="viking://resources/", max_length=2048)


class ManagedProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    credential_mode: Literal["managed"] | None = None
    workspace_uri: str = Field(default="viking://resources/", max_length=2048)


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    credential_mode: Literal["managed", "byok"] | None = None
    workspace_uri: str | None = Field(default=None, max_length=2048)


class OperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload: dict[str, Any] = Field(default_factory=dict)


class TextImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_ref: str = Field(min_length=1, max_length=4096)
    filename: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=1_048_576)


class ContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_ref: str = Field(min_length=1, max_length=4096)


class ConnectionResourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_ref: str = Field(min_length=1, max_length=4096)
    filename: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=1, max_length=128)


class AccessGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_type: Literal["user", "group"]
    subject: str = Field(min_length=1, max_length=256)
    role: Literal["Reader", "Contributor", "Manager", "Custom"] = "Reader"
    effect: Literal["allow", "deny"] = "allow"
    actions: list[str] = Field(default_factory=list, max_length=32)
    conditions: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="", max_length=500)


def _scope(auth: AuthContext) -> tuple[str, str, str]:
    return str(auth.tenant_id), f"tenant:{auth.tenant_id}", str(auth.user_id)


def _get_profile(service: OpenVikingService, profile_id: str, auth: AuthContext) -> OpenVikingProfile:
    tenant_id, workspace_id, principal_id = _scope(auth)
    profile = service.repository.get_any(profile_id, tenant_id, workspace_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="OpenViking profile not found")
    return profile


def _ready(
    service: OpenVikingService,
    profile_id: str,
    auth: AuthContext,
    action: str = "read",
) -> OpenVikingProfile:
    profile = _get_profile(service, profile_id, auth)
    if not authorize(service.repository.access, profile=profile, auth=auth, action=action):
        raise HTTPException(status_code=403, detail="Knowledge profile access denied")
    if profile.status != "ready":
        raise HTTPException(status_code=409, detail="OpenViking profile must be validated before use")
    return profile


def _error(exc: OpenVikingError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)})


def _managed_credentials() -> tuple[str, str]:
    base_url = os.getenv("OPENVIKING_MANAGED_BASE_URL", "").strip()
    try:
        api_key = get_runtime_secret("openviking_api_key", env_name="OPENVIKING_API_KEY") or ""
    except RuntimeSecretError as exc:
        raise OpenVikingError(
            "OPENVIKING_UNAVAILABLE",
            "Managed OpenViking credentials are not configured",
            503,
        ) from exc
    if not base_url or not api_key:
        raise OpenVikingError("OPENVIKING_UNAVAILABLE", "Managed OpenViking credentials are not configured", 503)
    return base_url, api_key


def _profile_credentials(values: dict[str, Any]) -> tuple[str, str, str]:
    policy = openviking_credential_policy()
    requested_mode = values.get("credential_mode")
    if policy == "hybrid" and requested_mode is None:
        raise HTTPException(status_code=400, detail="credential_mode is required for hybrid policy")
    mode = policy if policy != "hybrid" else requested_mode
    if requested_mode is not None and requested_mode != mode:
        raise HTTPException(status_code=400, detail="Requested credential_mode is not allowed")
    if mode == "managed":
        if values.get("base_url") or values.get("api_key"):
            raise HTTPException(status_code=400, detail="Managed OpenViking credentials are server-controlled")
        base_url, api_key = _managed_credentials()
        return base_url, api_key, mode
    base_url = str(values.get("base_url") or "")
    api_key = str(values.get("api_key") or "")
    if not base_url or not api_key:
        raise HTTPException(status_code=400, detail="BYOK requires Base URL and API Key")
    if urlsplit(base_url).scheme != "https":
        raise HTTPException(status_code=400, detail="BYOK Base URL must use HTTPS")
    return base_url, api_key, mode


@router.get("/profiles")
async def list_profiles(auth: AuthContext = Depends(require_scope(Scope.DATASET_READ))):
    service = _service()
    tenant_id, workspace_id, principal_id = _scope(auth)
    profiles = service.repository.list(tenant_id, workspace_id, principal_id)
    # Existing creator-scoped profiles remain visible; shared profiles are
    # resolved by tenant/workspace and filtered through the same policy engine.
    profiles += [
        item
        for item in (
            service.repository.get_any(profile_id, tenant_id, workspace_id)
            for profile_id in {
                grant.profile_id for grant in service.repository.access.list(tenant_id, None, include_revoked=False)
            }
        )
        if item is not None
        and item.principal_id != principal_id
        and authorize(service.repository.access, profile=item, auth=auth, action="list")
    ]
    unique = {item.profile_id: item for item in profiles}
    return success_response(data=[service.public(item) for item in unique.values()], message="Profiles retrieved")


@router.get("/profiles/{profile_id}/access-grants")
async def list_access_grants(profile_id: str, auth: AuthContext = Depends(require_scope(Scope.DATASET_READ))):
    service = _service()
    profile = _get_profile(service, profile_id, auth)
    if not authorize(service.repository.access, profile=profile, auth=auth, action="grant_manage"):
        raise HTTPException(status_code=403, detail="Knowledge profile grant management denied")
    return success_response(
        data=[grant_view(item) for item in service.repository.access.list(str(profile.tenant_id), profile.profile_id)],
        message="Access grants retrieved",
    )


@router.post("/profiles/{profile_id}/access-grants", status_code=201)
async def create_access_grant(
    profile_id: str,
    body: AccessGrantRequest,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_UPDATE)),
):
    service = _service()
    profile = _get_profile(service, profile_id, auth)
    if not authorize(service.repository.access, profile=profile, auth=auth, action="grant_manage"):
        raise HTTPException(status_code=403, detail="Knowledge profile grant management denied")
    actions = set(body.actions)
    if body.role != "Custom":
        actions = set(ROLE_ACTIONS[body.role])
    if not actions or not actions.issubset(
        set().union(
            *ROLE_ACTIONS.values(),
            {
                "list",
                "search",
                "read",
                "use_in_skill",
                "import",
                "reindex",
                "sync",
                "settings",
                "credential_rotate",
                "grant_manage",
                "delete",
            },
        )
    ):
        raise HTTPException(status_code=422, detail="Grant actions are invalid")
    now = time.time()
    grant = OpenVikingAccessGrant(
        grant_id="ovg_" + uuid.uuid4().hex,
        tenant_id=str(profile.tenant_id),
        profile_id=profile.profile_id,
        subject_type=body.subject_type,
        subject=body.subject,
        role=body.role,
        effect=body.effect,
        actions=tuple(sorted(actions)),
        conditions=body.conditions,
        reason=body.reason,
        policy_version="v1",
        created_at=now,
        updated_at=now,
    )
    service.repository.access.put(grant)
    service.repository.access.audit(
        str(profile.tenant_id),
        profile.profile_id,
        str(auth.user_id),
        "grant_manage",
        "allow",
        body.subject_type,
        body.subject,
        {"grant_id": grant.grant_id},
    )
    return success_response(data=grant_view(grant), message="Access grant created")


@router.delete("/profiles/{profile_id}/access-grants/{grant_id}", status_code=204)
async def revoke_access_grant(
    profile_id: str, grant_id: str, auth: AuthContext = Depends(require_scope(Scope.DATASET_UPDATE))
):
    service = _service()
    profile = _get_profile(service, profile_id, auth)
    if not authorize(service.repository.access, profile=profile, auth=auth, action="grant_manage"):
        raise HTTPException(status_code=403, detail="Knowledge profile grant management denied")
    if not service.repository.access.revoke(str(profile.tenant_id), profile.profile_id, grant_id):
        raise HTTPException(status_code=404, detail="Access grant not found")
    service.repository.access.audit(
        str(profile.tenant_id),
        profile.profile_id,
        str(auth.user_id),
        "grant_revoke",
        "allow",
        None,
        None,
        {"grant_id": grant_id},
    )


@router.get("/profiles/{profile_id}/access-audit")
async def access_audit(profile_id: str, auth: AuthContext = Depends(require_scope(Scope.DATASET_READ))):
    service = _service()
    profile = _get_profile(service, profile_id, auth)
    if not authorize(service.repository.access, profile=profile, auth=auth, action="grant_manage"):
        raise HTTPException(status_code=403, detail="Knowledge profile audit denied")
    return success_response(
        data=service.repository.access.audits(str(profile.tenant_id), profile.profile_id),
        message="Access audit retrieved",
    )


@router.post("/profiles", status_code=201)
async def create_profile(
    body: ManagedProfileCreate | ProfileCreate,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
):
    try:
        service = _service()
        tenant_id, workspace_id, principal_id = _scope(auth)
        values = body.model_dump()
        values["base_url"], values["api_key"], values["credential_mode"] = _profile_credentials(values)
        profile = service.create(tenant_id, workspace_id, principal_id, **values)
        return success_response(data=service.public(profile), message="Profile created")
    except (OpenVikingError, RuntimeSecretError) as exc:
        raise _error(exc)


@router.patch("/profiles/{profile_id}")
async def update_profile(
    profile_id: str, body: ProfileUpdate, auth: AuthContext = Depends(require_scope(Scope.DATASET_UPDATE))
):
    try:
        service = _service()
        values = body.model_dump(exclude_none=True)
        if values.get("api_key") == "":
            values.pop("api_key")
        if values.get("base_url") == "":
            values.pop("base_url")
        mode = values.pop("credential_mode", None)
        profile = _get_profile(service, profile_id, auth)
        if not authorize(service.repository.access, profile=profile, auth=auth, action="settings"):
            raise HTTPException(status_code=403, detail="Knowledge profile settings denied")
        if mode is not None and mode != profile.credential_mode:
            raise HTTPException(status_code=400, detail="Changing credential_mode is not supported")
        if profile.credential_mode == "managed" and (values.get("base_url") or values.get("api_key")):
            raise HTTPException(status_code=400, detail="Managed OpenViking credentials are server-controlled")
        profile = service.update(profile, **values)
        return success_response(data=service.public(profile), message="Profile updated")
    except (OpenVikingError, RuntimeSecretError) as exc:
        raise _error(exc)


@router.post("/profiles/{profile_id}/validate")
async def validate_profile(profile_id: str, auth: AuthContext = Depends(require_scope(Scope.DATASET_UPDATE))):
    try:
        service = _service()
        profile = _get_profile(service, profile_id, auth)
        if not authorize(service.repository.access, profile=profile, auth=auth, action="settings"):
            raise HTTPException(status_code=403, detail="Knowledge profile settings denied")
        profile = await service.validate(profile)
        return success_response(data=service.public(profile), message="Profile validated")
    except OpenVikingError as exc:
        raise _error(exc)


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(profile_id: str, auth: AuthContext = Depends(require_scope(Scope.DATASET_DELETE))):
    service = _service()
    profile = _get_profile(service, profile_id, auth)
    if not authorize(service.repository.access, profile=profile, auth=auth, action="delete"):
        raise HTTPException(status_code=403, detail="Knowledge profile delete denied")
    service.repository.delete(profile.profile_id, profile.tenant_id, profile.workspace_id, profile.principal_id)


@router.post("/profiles/{profile_id}/operations/{operation}")
async def operation(
    profile_id: str,
    operation: str,
    body: OperationRequest,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
):
    try:
        service = _service()
        write_operations = {
            "content_write",
            "content_reindex",
            "resource_import",
            "watch_create",
            "watch_update",
            "watch_delete",
            "watch_trigger",
        }
        action = "read"
        if operation in {"resource_import"}:
            action = "import"
        elif operation in {"content_write", "content_reindex"}:
            action = "reindex"
        elif operation.startswith("watch_") or operation == "session_commit":
            action = "sync"
        if not authorize(
            service.repository.access, profile=_get_profile(service, profile_id, auth), auth=auth, action=action
        ):
            raise HTTPException(status_code=403, detail="Knowledge profile action denied")
        if operation in write_operations and not (
            auth.has_scope(Scope.DATASET_CREATE) or auth.has_scope(Scope.DATASET_UPDATE)
        ):
            raise HTTPException(status_code=403, detail="OpenViking write permission required")
        result = await service.request(
            _ready(service, profile_id, auth, action),
            operation,
            body.payload,
            idempotency_key=None,
        )
        return success_response(data=result, message="OpenViking operation completed")
    except OpenVikingError as exc:
        raise _error(exc)


@router.post("/profiles/{profile_id}/operations/{operation}/{item_id}")
async def item_operation(
    profile_id: str,
    operation: str,
    item_id: str,
    body: OperationRequest,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
):
    try:
        service = _service()
        action = "sync" if operation in {"watch_update", "watch_delete", "watch_trigger", "session_commit"} else "read"
        if not authorize(
            service.repository.access, profile=_get_profile(service, profile_id, auth), auth=auth, action=action
        ):
            raise HTTPException(status_code=403, detail="Knowledge profile action denied")
        if operation in {"watch_update", "watch_delete", "watch_trigger", "session_commit"} and not auth.has_scope(
            Scope.DATASET_UPDATE
        ):
            raise HTTPException(status_code=403, detail="OpenViking update permission required")
        result = await service.item_request(_ready(service, profile_id, auth), operation, item_id, body.payload)
        return success_response(data=result, message="OpenViking item operation completed")
    except OpenVikingError as exc:
        raise _error(exc)


@router.post("/profiles/{profile_id}/resource")
async def delete_resource(
    profile_id: str, body: OperationRequest, auth: AuthContext = Depends(require_scope(Scope.DATASET_DELETE))
):
    try:
        service = _service()
        payload = dict(body.payload)
        payload.setdefault("recursive", True)
        payload.setdefault("wait", True)
        result = await service.request(_ready(service, profile_id, auth, "delete"), "fs_delete", payload)
        return success_response(data=result, message="Resource deleted")
    except OpenVikingError as exc:
        raise _error(exc)


@router.post("/profiles/{profile_id}/skill-context")
async def skill_context(
    profile_id: str, body: ContextRequest, auth: AuthContext = Depends(require_scope(Scope.DATASET_READ))
):
    try:
        service = _service()
        profile = _ready(service, profile_id, auth, "use_in_skill")
        resolved = await service.resolve_resource(profile, body.resource_ref)
        return success_response(
            data={
                "provider": "openviking",
                "profile_ref": profile.profile_id,
                "resource_ref": body.resource_ref,
                "display_name": resolved["display_name"],
                "resource_type": resolved["resource_type"],
                "summary": resolved["summary"],
                "profile_name": resolved["profile_name"],
                "version": "v1",
            },
            message="Resource context authorized",
        )
    except OpenVikingError as exc:
        raise _error(exc)


@router.post("/profiles/{profile_id}/resource/resolve")
async def resolve_resource(
    profile_id: str, body: ContextRequest, auth: AuthContext = Depends(require_scope(Scope.DATASET_READ))
):
    try:
        service = _service()
        return success_response(
            data=await service.resolve_resource(_ready(service, profile_id, auth, "read"), body.resource_ref),
            message="Resource reference resolved",
        )
    except OpenVikingError as exc:
        raise _error(exc)


@router.post("/profiles/{profile_id}/resource/read")
async def read_resource(
    profile_id: str,
    body: ContextRequest,
    offset: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=1_000_000, ge=1, le=1_000_000),
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
):
    try:
        service = _service()
        profile = _ready(service, profile_id, auth, "read")
        return success_response(
            data=await service.read_resource(profile, body.resource_ref, offset, limit),
            message="Resource content read",
        )
    except OpenVikingError as exc:
        raise _error(exc)


@router.post("/profiles/{profile_id}/text")
async def import_text(
    profile_id: str, body: TextImportRequest, auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE))
):
    try:
        service = _service()
        result = await service.import_text(
            _ready(service, profile_id, auth, "import"), body.filename, body.content, body.parent_ref
        )
        return success_response(data=result, message="Text import started")
    except OpenVikingError as exc:
        raise _error(exc)


@router.post("/profiles/{profile_id}/connection-resource")
async def import_connection_resource(
    profile_id: str,
    body: ConnectionResourceRequest,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        service = _service()
        resource = await source_resource_service.get_resource(
            session=session,
            tenant_id=auth.tenant_id,
            resource_id=body.resource_id,
        )
        if resource is None:
            raise HTTPException(status_code=404, detail="Connection resource not found")
        if resource.status != "ready":
            raise HTTPException(status_code=409, detail="Connection resource is not ready")
        document = {
            "kind": resource.resource_type,
            "display_name": resource.name,
            "description": {
                "external_id": resource.external_id,
                "selection": resource.selection_config_json or {},
            },
        }
        result = await service.import_connection_resource(
            _ready(service, profile_id, auth, "import"),
            filename=body.filename,
            parent_ref=body.parent_ref,
            document=document,
        )
        return success_response(data=result, message="Connection resource import started")
    except OpenVikingError as exc:
        raise _error(exc)


@router.post("/profiles/{profile_id}/upload")
async def upload(
    profile_id: str,
    parent_ref: str | None = Form(default=None),
    file: UploadFile = File(...),
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
):
    try:
        service = _service()
        result = await service.upload(
            _ready(service, profile_id, auth, "import"),
            file.filename or "upload",
            file.content_type or "application/octet-stream",
            await file.read(50 * 1024 * 1024 + 1),
            parent_ref,
        )
        return success_response(data=result, message="Temporary file uploaded")
    except OpenVikingError as exc:
        raise _error(exc)
