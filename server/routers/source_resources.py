from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_any_scope, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.schemas.source_resources import (
    EvidenceReadResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    NotebookAssetCreate,
    NotebookAssetRead,
    SourceConsumersRead,
    SourceLineageRead,
    SourceParsedAssetsRead,
    SourceResourceCreate,
    SourceResourceImportRequest,
    SourceResourceProcessingRead,
    SourceResourceRead,
    SourceResourceSyncRequest,
)
from server.schemas.standard_response import StandardResponse, success_response
from server.services.source_resources import SourceResourceService

router = APIRouter()
source_resource_service = SourceResourceService()


def _bad_request_or_not_found(error: ValueError) -> HTTPException:
    message = str(error)
    code = status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail=message)


@router.post("/source-resources", response_model=StandardResponse[SourceResourceRead], status_code=status.HTTP_201_CREATED)
async def create_source_resource(
    payload: SourceResourceCreate,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    data = await source_resource_service.create_resource(
        session=session,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        payload=payload,
    )
    return success_response(data=data, message="Source resource created")


@router.post("/source-resources/pdf", response_model=StandardResponse[SourceResourceRead], status_code=status.HTTP_201_CREATED)
async def create_pdf_source_resource(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    visibility: str = Form("workspace"),
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        data = await file.read()
        payload = await source_resource_service.create_file_resource_from_upload(
            session=session,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            name=name or file.filename or "PDF document",
            filename=file.filename or "document.pdf",
            data=data,
            visibility=visibility,
        )
        return success_response(data=payload, message="PDF source resource created")
    except ValueError as error:
        raise _bad_request_or_not_found(error)


@router.post("/source-resources/files", response_model=StandardResponse[SourceResourceRead], status_code=status.HTTP_201_CREATED)
async def create_file_source_resource(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    visibility: str = Form("workspace"),
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        data = await file.read()
        payload = await source_resource_service.create_file_resource_from_upload(
            session=session,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            name=name or file.filename or "Uploaded source file",
            filename=file.filename or "source-file",
            data=data,
            visibility=visibility,
        )
        return success_response(data=payload, message="File source resource created")
    except ValueError as error:
        raise _bad_request_or_not_found(error)


@router.post("/source-resources/import", response_model=StandardResponse[dict], status_code=status.HTTP_201_CREATED)
async def import_source_resources(
    payload: SourceResourceImportRequest,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        data = await source_resource_service.import_resources(
            session=session,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            payload=payload,
        )
        return success_response(data=data, message="Imported source resources")
    except ValueError as error:
        raise _bad_request_or_not_found(error)


@router.get("/source-resources", response_model=StandardResponse[dict])
async def list_source_resources(
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    items = await source_resource_service.list_resources(session=session, tenant_id=auth.tenant_id)
    return success_response(data={"items": items, "total": len(items)}, message="Retrieved source resources")


@router.get("/source-resources/{resource_id}/snapshots", response_model=StandardResponse[dict])
async def list_source_resource_snapshots(
    resource_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        data = await source_resource_service.list_snapshots(
            session=session,
            tenant_id=auth.tenant_id,
            resource_id=resource_id,
        )
        return success_response(data=data, message="Retrieved source resource snapshots")
    except ValueError as error:
        raise _bad_request_or_not_found(error)


@router.get("/source-resources/{resource_id}/parsed-assets", response_model=StandardResponse[SourceParsedAssetsRead])
async def get_source_resource_parsed_assets(
    resource_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        data = await source_resource_service.parsed_assets_payload(
            session=session,
            tenant_id=auth.tenant_id,
            resource_id=resource_id,
        )
        return success_response(data=data, message="Retrieved source resource parsed assets")
    except ValueError as error:
        raise _bad_request_or_not_found(error)


@router.get("/source-resources/{resource_id}/lineage", response_model=StandardResponse[SourceLineageRead])
async def get_source_resource_lineage(
    resource_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        data = await source_resource_service.lineage_payload(
            session=session,
            tenant_id=auth.tenant_id,
            resource_id=resource_id,
        )
        return success_response(data=data, message="Retrieved source resource lineage")
    except ValueError as error:
        raise _bad_request_or_not_found(error)


@router.get("/source-resources/{resource_id}/consumers", response_model=StandardResponse[SourceConsumersRead])
async def get_source_resource_consumers(
    resource_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        data = await source_resource_service.consumers_payload(
            session=session,
            tenant_id=auth.tenant_id,
            resource_id=resource_id,
        )
        return success_response(data=data, message="Retrieved source resource consumers")
    except ValueError as error:
        raise _bad_request_or_not_found(error)


@router.get("/source-resources/{resource_id}", response_model=StandardResponse[SourceResourceRead])
async def get_source_resource(
    resource_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    resource = await source_resource_service.get_resource(
        session=session,
        tenant_id=auth.tenant_id,
        resource_id=resource_id,
    )
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source resource not found")
    data = await source_resource_service.resource_payload(session=session, resource=resource)
    return success_response(data=data, message="Retrieved source resource")


@router.delete("/source-resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source_resource(
    resource_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_DELETE, Scope.DATASET_DELETE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    resource = await source_resource_service.get_resource(
        session=session,
        tenant_id=auth.tenant_id,
        resource_id=resource_id,
    )
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source resource not found")
    if not auth.has_scope(Scope.DATASET_DELETE):
        if resource.owner_id is None or str(resource.owner_id) != str(auth.user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete source resources you created",
            )
    await source_resource_service.delete_resource(
        session=session,
        tenant_id=auth.tenant_id,
        resource_id=resource_id,
    )


@router.post("/source-resources/{resource_id}/sync", response_model=StandardResponse[SourceResourceRead])
async def sync_source_resource(
    resource_id: str,
    payload: SourceResourceSyncRequest,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        data = await source_resource_service.sync_resource(
            session=session,
            tenant_id=auth.tenant_id,
            resource_id=resource_id,
            payload=payload,
        )
        return success_response(data=data, message="Source resource sync accepted")
    except ValueError as error:
        raise _bad_request_or_not_found(error)


@router.get("/source-resources/{resource_id}/processing", response_model=StandardResponse[SourceResourceProcessingRead])
async def get_source_resource_processing(
    resource_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        data = await source_resource_service.processing_payload(
            session=session,
            tenant_id=auth.tenant_id,
            resource_id=resource_id,
        )
        return success_response(data=data, message="Retrieved source resource processing state")
    except ValueError as error:
        raise _bad_request_or_not_found(error)


@router.post("/knowledge/search", response_model=StandardResponse[KnowledgeSearchResponse])
async def search_knowledge(
    payload: KnowledgeSearchRequest,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    items = await source_resource_service.search_knowledge(
        session=session,
        tenant_id=auth.tenant_id,
        query=payload.query,
        resource_ids=payload.resource_ids,
        limit=payload.limit,
    )
    data = {
        "items": items,
        "total": len(items),
    }
    return success_response(data=data, message="Knowledge search completed")


@router.get("/evidence/{evidence_id}", response_model=StandardResponse[EvidenceReadResponse])
async def read_evidence(
    evidence_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    data = await source_resource_service.read_evidence(
        session=session,
        tenant_id=auth.tenant_id,
        evidence_id=evidence_id,
    )
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence fragment not found")
    return success_response(data=data, message="Retrieved evidence fragment")


@router.post("/notebooks/{notebook_id}/assets", response_model=StandardResponse[NotebookAssetRead])
async def add_notebook_asset(
    notebook_id: str,
    payload: NotebookAssetCreate,
    auth: AuthContext = Depends(require_any_scope(Scope.NOTEBOOK_UPDATE, Scope.NOTEBOOK_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        asset = await source_resource_service.bind_notebook_asset(
            session=session,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            notebook_id=notebook_id,
            asset_type=payload.asset_type,
            asset_id=payload.asset_id,
            usage_policy=payload.usage_policy,
        )
        return success_response(
            data={
                "id": asset.id,
                "notebook_id": asset.notebook_id,
                "asset_type": asset.asset_type,
                "asset_id": asset.asset_id,
                "added_by": asset.added_by,
                "usage_policy_json": asset.usage_policy_json,
                "added_at": asset.added_at,
            },
            message="Notebook asset bound",
        )
    except ValueError as error:
        raise _bad_request_or_not_found(error)


@router.get("/notebooks/{notebook_id}/assets", response_model=StandardResponse[dict])
async def list_notebook_assets(
    notebook_id: str,
    auth: AuthContext = Depends(require_scope(Scope.NOTEBOOK_READ_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    assets = await source_resource_service.list_notebook_assets(
        session=session,
        tenant_id=auth.tenant_id,
        notebook_id=notebook_id,
    )
    items = [
        {
            "id": item.id,
            "notebook_id": item.notebook_id,
            "asset_type": item.asset_type,
            "asset_id": item.asset_id,
            "added_by": item.added_by,
            "usage_policy_json": item.usage_policy_json,
            "added_at": item.added_at,
        }
        for item in assets
    ]
    return success_response(data={"items": items, "total": len(items)}, message="Retrieved notebook assets")
