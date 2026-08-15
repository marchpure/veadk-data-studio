from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_any_scope, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.models.knowledge_resources import KnowledgeResource
from server.models.notebooks import Notebook, NotebookAsset
from server.models.source_snapshots import SourceSnapshot
from server.repositories.source_resources import SourceResourceRepository
from server.repositories.source_snapshots import SourceSnapshotRepository
from server.schemas.notebook_assets import (
    NotebookAssetAssociateRequest,
    NotebookAssetAssociationRead,
    NotebookAssetListResponse,
)
from server.schemas.source_resources import (
    KnowledgeResourceProcessingRead,
    SourceResourceCreate,
    SourceResourceListResponse,
    SourceResourceProcessingRead,
    SourceResourceRead,
    SourceResourceSyncResponse,
    SourceSnapshotListResponse,
    SourceSnapshotRead,
    WebSourceResourceCreate,
)
from server.schemas.standard_response import success_response
from server.services.multi_source_assets import MultiSourceAssetService
from server.services.notebook import NotebookService
from server.services.source_processing import SourceProcessingError, SourceProcessingService

logger = logging.getLogger(__name__)

router = APIRouter()


def _can_access_source_resource(auth: AuthContext, resource) -> bool:
    if str(resource.tenant_id) != str(auth.tenant_id):
        return False
    if resource.visibility == "workspace":
        return True
    if resource.owner_id is None:
        return True
    return str(resource.owner_id) == str(auth.user_id)


def _assert_source_resource_access(auth: AuthContext, resource) -> None:
    if not _can_access_source_resource(auth, resource):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this source resource")


def _can_access_notebook(auth: AuthContext, notebook: Notebook, full_scope: Scope) -> bool:
    if auth.has_scope(full_scope):
        return True
    return notebook.created_by is not None and str(notebook.created_by) == str(auth.user_id)


async def _get_owned_notebook_or_404(
    *,
    session: AsyncSession,
    notebook_id: str,
    auth: AuthContext,
    full_scope: Scope,
) -> Notebook:
    notebook = await NotebookService.get_notebook(session, notebook_id)
    if notebook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found")
    if not _can_access_notebook(auth, notebook, full_scope):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only access notebooks you created")
    return notebook


@router.post("/source-resources", status_code=status.HTTP_201_CREATED)
async def create_source_resource_endpoint(
    payload: SourceResourceCreate,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        repo = SourceResourceRepository(session)
        initial_status = "needs_confirmation" if payload.resource_type in {"feishu_doc", "feishu_sheet"} else "pending"
        resource = await repo.create(
            {
                "tenant_id": auth.tenant_id,
                "connection_id": payload.connection_id,
                "resource_type": payload.resource_type,
                "name": payload.name,
                "external_id": payload.external_id,
                "source_url": payload.source_url,
                "owner_id": auth.user_id,
                "visibility": payload.visibility,
                "sync_mode": payload.sync_mode,
                "sync_config_json": payload.sync_config_json,
                "status": initial_status,
            }
        )
        data = SourceResourceRead.model_validate(resource).model_dump(mode="json")
        return success_response(data=data, message="Source resource created")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Error creating source resource: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create source resource")


@router.get("/source-resources")
async def list_source_resources_endpoint(
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    repo = SourceResourceRepository(session)
    resources = await repo.list(filters={"tenant_id": auth.tenant_id})
    visible = [
        resource
        for resource in resources
        if _can_access_source_resource(auth, resource)
    ]
    visible.sort(key=lambda resource: resource.updated_at, reverse=True)
    response = SourceResourceListResponse(
        items=[SourceResourceRead.model_validate(resource) for resource in visible],
        total=len(visible),
    )
    return success_response(data=response.model_dump(mode="json"), message=f"Retrieved {len(visible)} source resource(s)")


@router.post("/source-resources/pdf", status_code=status.HTTP_201_CREATED)
async def upload_pdf_source_resource_endpoint(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    sync_mode: str = Form("manual"),
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    filename = file.filename or "document.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are supported")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PDF file is empty")

    repo = SourceResourceRepository(session)
    resource = await repo.create(
        {
            "tenant_id": auth.tenant_id,
            "resource_type": "pdf",
            "name": name or filename,
            "external_id": filename,
            "owner_id": auth.user_id,
            "visibility": "workspace",
            "sync_mode": sync_mode,
            "status": "understanding",
        }
    )
    try:
        await SourceProcessingService.ingest_pdf(session=session, resource=resource, filename=filename, data=data)
    except SourceProcessingError as exc:
        await SourceProcessingService.persist_failed_snapshot(
            session=session,
            resource=resource,
            message=str(exc),
            raw_storage_uri=exc.raw_storage_uri or "error://source-processing",
            parser_version=exc.parser_version or SourceProcessingService.PDF_PARSER_VERSION,
            metadata_json=exc.metadata_json or {"filename": filename},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    finally:
        await file.close()

    await session.refresh(resource)
    data_out = SourceResourceRead.model_validate(resource).model_dump(mode="json")
    return success_response(data=data_out, message="PDF source resource created")


@router.post("/source-resources/web", status_code=status.HTTP_201_CREATED)
async def create_web_source_resource_endpoint(
    payload: WebSourceResourceCreate,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    repo = SourceResourceRepository(session)
    resource = await repo.create(
        {
            "tenant_id": auth.tenant_id,
            "resource_type": "web",
            "name": payload.name,
            "source_url": payload.source_url,
            "owner_id": auth.user_id,
            "visibility": "workspace",
            "sync_mode": payload.sync_mode,
            "sync_config_json": payload.sync_config_json,
            "status": "understanding",
        }
    )
    try:
        await SourceProcessingService.ingest_web(session=session, resource=resource)
    except SourceProcessingError as exc:
        await SourceProcessingService.persist_failed_snapshot(
            session=session,
            resource=resource,
            message=str(exc),
            raw_storage_uri=exc.raw_storage_uri or "error://source-processing",
            parser_version=exc.parser_version or SourceProcessingService.WEB_PARSER_VERSION,
            metadata_json=exc.metadata_json or {"source_url": payload.source_url},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    await session.refresh(resource)
    data_out = SourceResourceRead.model_validate(resource).model_dump(mode="json")
    return success_response(data=data_out, message="Web source resource created")


@router.get("/source-resources/{resource_id}")
async def get_source_resource_endpoint(
    resource_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    repo = SourceResourceRepository(session)
    resource = await repo.get(resource_id)
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source resource not found")
    _assert_source_resource_access(auth, resource)
    data = SourceResourceRead.model_validate(resource).model_dump(mode="json")
    return success_response(data=data, message="Source resource retrieved")


@router.post("/source-resources/{resource_id}/sync")
async def sync_source_resource_endpoint(
    resource_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    repo = SourceResourceRepository(session)
    resource = await repo.get(resource_id)
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source resource not found")
    _assert_source_resource_access(auth, resource)
    resource.status = "syncing"
    await session.commit()
    await session.refresh(resource)

    try:
        result = None
        if resource.resource_type == "web":
            resource.status = "understanding"
            await session.commit()
            await session.refresh(resource)
            result = await SourceProcessingService.ingest_web(session=session, resource=resource)
        elif resource.resource_type == "pdf":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PDF resources require re-upload to sync a new snapshot",
            )
        elif resource.resource_type in {"feishu_doc", "feishu_sheet"}:
            resource.status = "needs_confirmation"
            await session.commit()
            await session.refresh(resource)
            data = SourceResourceSyncResponse(
                resource_id=resource.id,
                status=resource.status,
                message="Feishu connector requires production OAuth/configuration before sync can run.",
            ).model_dump(mode="json")
            return success_response(data=data, message="Feishu source requires authorization")
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported source resource type")
    except HTTPException:
        raise
    except SourceProcessingError as exc:
        snapshot = await SourceProcessingService.persist_failed_snapshot(
            session=session,
            resource=resource,
            message=str(exc),
            raw_storage_uri=exc.raw_storage_uri or "error://source-sync",
            parser_version=(
                exc.parser_version
                or (SourceProcessingService.WEB_PARSER_VERSION if resource.resource_type == "web" else None)
            ),
            metadata_json=exc.metadata_json or ({"source_url": resource.source_url} if resource.source_url else None),
        )
        data = SourceResourceSyncResponse(
            resource_id=resource.id,
            status=resource.status,
            message=str(exc),
            snapshot_id=snapshot.id,
        ).model_dump(mode="json")
        return success_response(data=data, message="Source resource sync failed")

    await session.refresh(resource)
    data = SourceResourceSyncResponse(
        resource_id=resource.id,
        status=resource.status,
        message="Source resource synced",
        snapshot_id=result.snapshot.id if result else None,
        knowledge_resource_id=result.knowledge_resource.id if result else None,
    ).model_dump(mode="json")
    return success_response(data=data, message="Source resource synced")


@router.get("/source-resources/{resource_id}/snapshots")
async def list_source_snapshots_endpoint(
    resource_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    resource_repo = SourceResourceRepository(session)
    resource = await resource_repo.get(resource_id)
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source resource not found")
    _assert_source_resource_access(auth, resource)

    snapshot_repo = SourceSnapshotRepository(session)
    snapshots = await snapshot_repo.list(filters={"resource_id": resource_id})
    response = SourceSnapshotListResponse(
        items=[SourceSnapshotRead.model_validate(snapshot) for snapshot in snapshots],
        total=len(snapshots),
    )
    return success_response(data=response.model_dump(mode="json"), message=f"Retrieved {len(snapshots)} snapshot(s)")


@router.get("/source-resources/{resource_id}/processing")
async def get_source_resource_processing_endpoint(
    resource_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    resource_repo = SourceResourceRepository(session)
    resource = await resource_repo.get(resource_id)
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source resource not found")
    _assert_source_resource_access(auth, resource)

    latest_snapshot = None
    if resource.latest_snapshot_id is not None:
        latest_snapshot = await session.get(SourceSnapshot, resource.latest_snapshot_id)

    knowledge_resource = None
    if latest_snapshot is not None:
        knowledge_resource = await session.scalar(
            select(KnowledgeResource).where(KnowledgeResource.snapshot_id == latest_snapshot.id)
        )

    response = SourceResourceProcessingRead(
        resource_id=resource.id,
        status=resource.status,
        latest_snapshot=SourceSnapshotRead.model_validate(latest_snapshot) if latest_snapshot else None,
        knowledge_resource=(
            KnowledgeResourceProcessingRead(
                id=knowledge_resource.id,
                provider=knowledge_resource.provider,
                provider_resource_id=knowledge_resource.provider_resource_id,
                parse_status=knowledge_resource.parse_status,
                index_status=knowledge_resource.index_status,
                completeness_score=knowledge_resource.completeness_score,
            )
            if knowledge_resource
            else None
        ),
    )
    return success_response(data=response.model_dump(mode="json"), message="Source resource processing retrieved")


@router.delete("/source-resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source_resource_endpoint(
    resource_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_DELETE, Scope.DATASET_DELETE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    repo = SourceResourceRepository(session)
    resource = await repo.get(resource_id)
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source resource not found")
    _assert_source_resource_access(auth, resource)
    if not auth.has_scope(Scope.DATASET_DELETE) and resource.owner_id and str(resource.owner_id) != str(auth.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete resources you created")
    await repo.delete(resource_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/notebooks/{notebook_id}/assets", status_code=status.HTTP_201_CREATED)
async def associate_notebook_asset_endpoint(
    notebook_id: str,
    payload: NotebookAssetAssociateRequest,
    auth: AuthContext = Depends(require_any_scope(Scope.NOTEBOOK_UPDATE, Scope.NOTEBOOK_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        await _get_owned_notebook_or_404(
            session=session,
            notebook_id=notebook_id,
            auth=auth,
            full_scope=Scope.NOTEBOOK_UPDATE,
        )
        asset = await MultiSourceAssetService().associate_asset_with_notebook(
            session=session,
            notebook_id=notebook_id,
            asset_type=payload.asset_type,
            asset_id=payload.asset_id,
            usage_policy_json=payload.usage_policy_json,
            added_by=auth.user_id,
        )
        data = NotebookAssetAssociationRead.model_validate(asset).model_dump(mode="json")
        return success_response(data=data, message="Notebook asset associated")
    except HTTPException:
        raise
    except ValueError as exc:
        message = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=message)
    except Exception as exc:
        logger.error("Error associating notebook asset: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to associate asset")


@router.get("/notebooks/{notebook_id}/assets")
async def list_notebook_assets_endpoint(
    notebook_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.NOTEBOOK_READ, Scope.NOTEBOOK_READ_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    await _get_owned_notebook_or_404(
        session=session,
        notebook_id=notebook_id,
        auth=auth,
        full_scope=Scope.NOTEBOOK_READ,
    )
    assets = await MultiSourceAssetService().search_assets(session=session, notebook_id=notebook_id)
    response = NotebookAssetListResponse(items=assets, total=len(assets))
    return success_response(data=response.model_dump(mode="json"), message=f"Retrieved {len(assets)} asset(s)")


@router.delete("/notebooks/{notebook_id}/assets/{asset_type}/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notebook_asset_endpoint(
    notebook_id: str,
    asset_type: str,
    asset_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.NOTEBOOK_UPDATE, Scope.NOTEBOOK_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    await _get_owned_notebook_or_404(
        session=session,
        notebook_id=notebook_id,
        auth=auth,
        full_scope=Scope.NOTEBOOK_UPDATE,
    )
    result = await session.execute(
        select(NotebookAsset).where(
            NotebookAsset.notebook_id == notebook_id,
            NotebookAsset.asset_type == asset_type,
            NotebookAsset.asset_id == asset_id,
        )
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook asset association not found")
    await session.delete(asset)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
