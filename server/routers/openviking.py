from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.schemas.standard_response import success_response
from server.services.external_oidc import enabled as external_oidc_enabled
from server.services.openviking_service import (
    OpenVikingConfig,
    OpenVikingError,
    OpenVikingProfile,
    OpenVikingProfileRepository,
    OpenVikingService,
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
    workspace_uri: str = Field(default="viking://resources/", max_length=2048)


class ManagedProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    workspace_uri: str = Field(default="viking://resources/", max_length=2048)


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
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


def _scope(auth: AuthContext) -> tuple[str, str, str]:
    return str(auth.tenant_id), f"tenant:{auth.tenant_id}", str(auth.user_id)


def _get_profile(service: OpenVikingService, profile_id: str, auth: AuthContext) -> OpenVikingProfile:
    tenant_id, workspace_id, principal_id = _scope(auth)
    profile = service.repository.get(profile_id, tenant_id, workspace_id, principal_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="OpenViking profile not found")
    return profile


def _ready(service: OpenVikingService, profile_id: str, auth: AuthContext) -> OpenVikingProfile:
    profile = _get_profile(service, profile_id, auth)
    if profile.status != "ready":
        raise HTTPException(status_code=409, detail="OpenViking profile must be validated before use")
    return profile


def _error(exc: OpenVikingError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)})


@router.get("/profiles")
async def list_profiles(auth: AuthContext = Depends(require_scope(Scope.DATASET_READ))):
    service = _service()
    tenant_id, workspace_id, principal_id = _scope(auth)
    return success_response(data=[service.public(item) for item in service.repository.list(tenant_id, workspace_id, principal_id)], message="Profiles retrieved")


@router.post("/profiles", status_code=201)
async def create_profile(
    body: ProfileCreate | ManagedProfileCreate,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
):
    try:
        service = _service()
        tenant_id, workspace_id, principal_id = _scope(auth)
        values = body.model_dump()
        if external_oidc_enabled():
            if values.get("base_url") or values.get("api_key"):
                raise HTTPException(status_code=400, detail="Managed OpenViking credentials are server-controlled")
            values["base_url"] = values.get("base_url") or os.getenv("OPENVIKING_MANAGED_BASE_URL")
            values["api_key"] = values.get("api_key") or get_runtime_secret("openviking_api_key")
        if not values.get("base_url") or not values.get("api_key"):
            raise OpenVikingError("OPENVIKING_UNAVAILABLE", "OpenViking profile credentials are required", 503)
        profile = service.create(tenant_id, workspace_id, principal_id, **values)
        return success_response(data=service.public(profile), message="Profile created")
    except (OpenVikingError, RuntimeSecretError) as exc:
        raise _error(exc)


@router.patch("/profiles/{profile_id}")
async def update_profile(profile_id: str, body: ProfileUpdate, auth: AuthContext = Depends(require_scope(Scope.DATASET_UPDATE))):
    try:
        service = _service()
        values = body.model_dump(exclude_none=True)
        if external_oidc_enabled():
            values.pop("base_url", None)
            values.pop("api_key", None)
        profile = service.update(_get_profile(service, profile_id, auth), **values)
        return success_response(data=service.public(profile), message="Profile updated")
    except (OpenVikingError, RuntimeSecretError) as exc:
        raise _error(exc)


@router.post("/profiles/{profile_id}/validate")
async def validate_profile(profile_id: str, auth: AuthContext = Depends(require_scope(Scope.DATASET_UPDATE))):
    try:
        service = _service()
        profile = await service.validate(_get_profile(service, profile_id, auth))
        return success_response(data=service.public(profile), message="Profile validated")
    except OpenVikingError as exc:
        raise _error(exc)


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(profile_id: str, auth: AuthContext = Depends(require_scope(Scope.DATASET_DELETE))):
    service = _service()
    profile = _get_profile(service, profile_id, auth)
    service.repository.delete(profile.profile_id, profile.tenant_id, profile.workspace_id, profile.principal_id)


@router.post("/profiles/{profile_id}/operations/{operation}")
async def operation(profile_id: str, operation: str, body: OperationRequest, auth: AuthContext = Depends(require_scope(Scope.DATASET_READ))):
    try:
        service = _service()
        write_operations = {
            "content_write", "content_reindex", "resource_import",
            "watch_create", "watch_update", "watch_delete", "watch_trigger",
        }
        if operation in write_operations and not (
            auth.has_scope(Scope.DATASET_CREATE) or auth.has_scope(Scope.DATASET_UPDATE)
        ):
            raise HTTPException(status_code=403, detail="OpenViking write permission required")
        result = await service.request(
            _ready(service, profile_id, auth),
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
        if operation in {"watch_update", "watch_delete", "watch_trigger", "session_commit"} and not auth.has_scope(Scope.DATASET_UPDATE):
            raise HTTPException(status_code=403, detail="OpenViking update permission required")
        result = await service.item_request(_ready(service, profile_id, auth), operation, item_id, body.payload)
        return success_response(data=result, message="OpenViking item operation completed")
    except OpenVikingError as exc:
        raise _error(exc)


@router.post("/profiles/{profile_id}/resource")
async def delete_resource(profile_id: str, body: OperationRequest, auth: AuthContext = Depends(require_scope(Scope.DATASET_DELETE))):
    try:
        service = _service()
        payload = dict(body.payload)
        payload.setdefault("recursive", True)
        payload.setdefault("wait", True)
        result = await service.request(_ready(service, profile_id, auth), "fs_delete", payload)
        return success_response(data=result, message="Resource deleted")
    except OpenVikingError as exc:
        raise _error(exc)


@router.post("/profiles/{profile_id}/skill-context")
async def skill_context(profile_id: str, body: ContextRequest, auth: AuthContext = Depends(require_scope(Scope.DATASET_READ))):
    try:
        service = _service()
        profile = _ready(service, profile_id, auth)
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
async def resolve_resource(profile_id: str, body: ContextRequest, auth: AuthContext = Depends(require_scope(Scope.DATASET_READ))):
    try:
        service = _service()
        return success_response(data=await service.resolve_resource(_ready(service, profile_id, auth), body.resource_ref), message="Resource reference resolved")
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
        profile = _ready(service, profile_id, auth)
        return success_response(
            data=await service.read_resource(profile, body.resource_ref, offset, limit),
            message="Resource content read",
        )
    except OpenVikingError as exc:
        raise _error(exc)


@router.post("/profiles/{profile_id}/text")
async def import_text(profile_id: str, body: TextImportRequest, auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE))):
    try:
        service = _service()
        result = await service.import_text(_ready(service, profile_id, auth), body.filename, body.content, body.parent_ref)
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
            _ready(service, profile_id, auth),
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
            _ready(service, profile_id, auth),
            file.filename or "upload",
            file.content_type or "application/octet-stream",
            await file.read(50 * 1024 * 1024 + 1),
            parent_ref,
        )
        return success_response(data=result, message="Temporary file uploaded")
    except OpenVikingError as exc:
        raise _error(exc)
