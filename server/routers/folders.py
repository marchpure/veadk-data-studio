from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_any_scope, require_scope
from server.auth.object_authorizer import NotebookAction, authorize_notebook_action
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.models.queries import Query
from server.models.tenant_member import TenantRole
from server.repositories.dashboard import DashboardRepository
from server.repositories.folder import FolderRepository
from server.repositories.folder_dashboard import FolderDashboardRepository
from server.repositories.folder_member import FolderMemberRepository
from server.repositories.notebooks import NotebookRepository
from server.schemas.folder import (
    CloneNotebookRequest,
    CloneNotebookResponse,
    DashboardFolderListResponse,
    DashboardFolderRead,
    FolderCreate,
    FolderDashboardListResponse,
    FolderDashboardRead,
    FolderDashboardShare,
    FolderDashboardUpdate,
    FolderListResponse,
    FolderMemberAdd,
    FolderMemberListResponse,
    FolderMemberRead,
    FolderNotebookListResponse,
    FolderNotebookRead,
    FolderNotebookShare,
    FolderRead,
    FolderUpdate,
    NotebookFolderListResponse,
    NotebookFolderRead,
)
from server.schemas.query import (
    BatchExecuteSavedQueriesRequest,
    BatchExecuteSavedQueriesResponse,
    BatchFilterPreflightResponse,
)
from server.schemas.standard_response import success_response
from server.schemas.tenant import UserInfo
from server.services.filter_config_service import normalize_filters_for_client
from server.services.folder_service import FolderService
from server.services.notebook import NotebookService
from server.services.query_service import QueryService
from server.services.sharing import SharingService
from server.services.viewer_session_service import VIEWER_SESSION_MINUTES, ViewerSessionService
from server.utils.config_loader import is_self_hosted
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


async def _require_viewer_session(
    dashboard_id: UUID,
    viewer_session: str | None,
    session: AsyncSession,
) -> UUID:
    if not viewer_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing viewer session")

    canonical = await SharingService(session).require_viewer_session_for_dashboard(
        token=viewer_session,
        dashboard_id=dashboard_id,
    )
    if canonical is not None:
        return canonical[0]

    payload = ViewerSessionService.verify(viewer_session)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired viewer session")

    user_id = payload.get("uid")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid viewer session payload")

    dashboard_repo = DashboardRepository(session)
    dashboard = await dashboard_repo.get(dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")

    required_claims = ("tid", "grant_id", "asset_id", "version_id", "jti", "iat", "nbf", "exp")
    if any(not payload.get(claim) for claim in required_claims):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid viewer session payload")

    if str(payload.get("tid")) != str(dashboard.tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Viewer session tenant mismatch")
    if str(payload.get("version_id")) != str(dashboard.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="viewer session is not valid for this dashboard",
        )
    if str(payload.get("asset_id")) != str(dashboard.asset_id or dashboard.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="viewer session is not valid for this dashboard asset",
        )

    try:
        grant_id = UUID(str(payload["grant_id"]))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid viewer session payload") from None

    folder_dashboard_repo = FolderDashboardRepository(session)
    grant = await folder_dashboard_repo.get(grant_id)
    if not grant or grant.dashboard_id != dashboard.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="viewer session grant has been revoked or rotated",
        )

    return UUID(str(user_id))


async def _dashboard_folder_grant_for_user(
    *,
    dashboard_id: UUID,
    user_id: UUID,
    session: AsyncSession,
) -> FolderDashboard | None:
    folder_dashboard_repo = FolderDashboardRepository(session)
    folder_dashboards = await folder_dashboard_repo.list_by_dashboard(dashboard_id)
    if not folder_dashboards:
        return None

    folder_repo = FolderRepository(session)
    member_repo = FolderMemberRepository(session)
    for grant in folder_dashboards:
        folder = await folder_repo.get(grant.folder_id)
        if folder and folder.is_public:
            return grant
        if await member_repo.is_member(grant.folder_id, user_id):
            return grant
    return None


def _batch_request_query_ids(request: BatchExecuteSavedQueriesRequest) -> list[str]:
    if request.queries_with_filters:
        return [str(query.query_id) for query in request.queries_with_filters]
    return [str(query_id) for query_id in (request.query_ids or [])]


async def _require_viewer_dashboard_query_bindings(
    dashboard_id: UUID,
    request: BatchExecuteSavedQueriesRequest,
    session: AsyncSession,
) -> None:
    query_ids = _batch_request_query_ids(request)
    if not query_ids:
        return
    try:
        parsed_query_ids = [UUID(str(query_id)) for query_id in query_ids]
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="One or more queries are not available for this dashboard",
        ) from None

    dashboard_repo = DashboardRepository(session)
    dashboard = await dashboard_repo.get(dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")

    result = await session.execute(
        select(Query.id).where(
            Query.id.in_(parsed_query_ids),
            Query.notebook_id == dashboard.notebook_id,
            Query.tenant_id == dashboard.tenant_id,
        )
    )
    bound_query_ids = {str(query_id) for query_id in result.scalars().all()}
    requested_query_ids = {str(query_id) for query_id in query_ids}
    if bound_query_ids != requested_query_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="One or more queries are not available for this dashboard",
        )


# ==================== Folder CRUD ====================


@router.post("/folders", status_code=status.HTTP_201_CREATED)
async def create_folder(
    payload: FolderCreate,
    auth: AuthContext = Depends(require_scope(Scope.FOLDER_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Create a new folder. Only admin/owner can create folders."""
    try:
        folder = await FolderService.create_folder(
            tenant_id=auth.tenant_id,
            created_by=auth.user_id,
            name=payload.name,
            description=payload.description,
            is_public=payload.is_public,
            session=session,
        )

        folder_read = FolderRead.model_validate(folder)
        return success_response(
            data=folder_read.model_dump(),
            message=f"Folder '{payload.name}' created successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating folder: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the folder",
        )


@router.get("/folders")
async def list_folders(
    auth: AuthContext = Depends(require_scope(Scope.FOLDER_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """List folders. All users see only folders they're members of + public folders."""
    try:
        folders = await FolderService.list_folders_for_user(
            user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            session=session,
        )

        folder_reads = []
        folder_repo = FolderRepository(session)
        for folder in folders:
            folder_data = await folder_repo.get_with_counts(folder.id)
            if folder_data:
                read = FolderRead(
                    id=folder.id,
                    tenant_id=folder.tenant_id,
                    created_by=folder.created_by,
                    name=folder.name,
                    description=folder.description,
                    created_at=folder.created_at,
                    updated_at=folder.updated_at,
                    creator=UserInfo.model_validate(folder.creator) if folder.creator else None,
                    member_count=folder_data["member_count"],
                    notebook_count=folder_data["notebook_count"],
                )
                folder_reads.append(read)

        response = FolderListResponse(items=folder_reads, total=len(folder_reads))
        return success_response(data=response.model_dump(), message=f"Retrieved {len(folder_reads)} folder(s)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing folders: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while listing folders",
        )


@router.get("/folders/all-notebooks")
async def list_all_notebooks(
    auth: AuthContext = Depends(require_scope(Scope.FOLDER_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """List all notebooks accessible to the current user, grouped by folder.

    Returns folders user is member of + public folders, with their shared notebooks.
    """
    try:
        result = await FolderService.list_all_accessible_notebooks(
            user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            session=session,
        )
        return success_response(
            data=result,
            message=f"Retrieved {result['total_notebooks']} notebook(s) across {len(result['folders'])} folder(s)",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing all notebooks: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while listing notebooks",
        )


@router.get("/folders/{folder_id}")
async def get_folder(
    folder_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.FOLDER_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """Get folder details. Must be a member or admin."""
    try:
        folder = await FolderService.get_folder_with_creator(folder_id, session)
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

        # Check access (member or public folder only - no admin bypass)
        if not folder.is_public:
            is_member = await FolderService.is_folder_member(folder_id, auth.user_id, session)
            if not is_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this folder"
                )

        folder_repo = FolderRepository(session)
        folder_data = await folder_repo.get_with_counts(folder_id)
        folder_read = FolderRead(
            id=folder.id,
            tenant_id=folder.tenant_id,
            created_by=folder.created_by,
            name=folder.name,
            description=folder.description,
            created_at=folder.created_at,
            updated_at=folder.updated_at,
            creator=UserInfo.model_validate(folder.creator) if folder.creator else None,
            member_count=folder_data["member_count"] if folder_data else None,
            notebook_count=folder_data["notebook_count"] if folder_data else None,
        )

        return success_response(data=folder_read.model_dump(), message="Folder retrieved successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting folder {folder_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving the folder",
        )


@router.patch("/folders/{folder_id}")
async def update_folder(
    folder_id: UUID,
    payload: FolderUpdate,
    auth: AuthContext = Depends(require_scope(Scope.FOLDER_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Update folder. Only creator or admin can update."""
    try:
        folder = await FolderService.get_folder(folder_id, session)
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

        if not await FolderService.can_manage_folder_members(folder, auth.user_id, auth.role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot update this folder")

        updated = await FolderService.update_folder(
            folder_id, payload.name, payload.description, payload.is_public, session
        )
        folder_read = FolderRead.model_validate(updated)

        return success_response(data=folder_read.model_dump(), message="Folder updated successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating folder {folder_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the folder",
        )


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.FOLDER_DELETE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete folder. Only creator or admin can delete."""
    try:
        folder = await FolderService.get_folder(folder_id, session)
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

        if not await FolderService.can_manage_folder_members(folder, auth.user_id, auth.role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot delete this folder")

        await FolderService.delete_folder(folder_id, session)
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting folder {folder_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the folder",
        )


# ==================== Folder Members ====================


@router.get("/folders/{folder_id}/members")
async def list_folder_members(
    folder_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.FOLDER_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """List folder members."""
    try:
        folder = await FolderService.get_folder(folder_id, session)
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

        # Check access
        is_admin = auth.role in (TenantRole.OWNER, TenantRole.ADMIN)
        if not is_admin:
            is_member = await FolderService.is_folder_member(folder_id, auth.user_id, session)
            if not is_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this folder"
                )

        members = await FolderService.list_folder_members(folder_id, session)
        member_reads = [
            FolderMemberRead(
                id=m.id,
                folder_id=m.folder_id,
                user_id=m.user_id,
                added_by=m.added_by,
                created_at=m.created_at,
                user=UserInfo.model_validate(m.user) if m.user else None,
                added_by_user=UserInfo.model_validate(m.added_by_user) if m.added_by_user else None,
            )
            for m in members
        ]

        response = FolderMemberListResponse(items=member_reads, total=len(member_reads))
        return success_response(data=response.model_dump(), message=f"Retrieved {len(member_reads)} member(s)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing folder members for {folder_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while listing folder members",
        )


@router.post("/folders/{folder_id}/members", status_code=status.HTTP_201_CREATED)
async def add_folder_member(
    folder_id: UUID,
    payload: FolderMemberAdd,
    auth: AuthContext = Depends(require_scope(Scope.FOLDER_MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_async_session),
):
    """Add a member to a folder. Only creator or admin can add members."""
    try:
        folder = await FolderService.get_folder(folder_id, session)
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

        if not await FolderService.can_manage_folder_members(folder, auth.user_id, auth.role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot manage folder members")

        member = await FolderService.add_folder_member(
            folder_id=folder_id,
            user_id=payload.user_id,
            added_by=auth.user_id,
            tenant_id=auth.tenant_id,
            session=session,
        )

        member_read = FolderMemberRead.model_validate(member)
        return success_response(data=member_read.model_dump(), message="Member added successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding member to folder {folder_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while adding the member",
        )


@router.delete("/folders/{folder_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_folder_member(
    folder_id: UUID,
    member_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.FOLDER_MANAGE_MEMBERS)),
    session: AsyncSession = Depends(get_async_session),
):
    """Remove a member from a folder."""
    try:
        folder = await FolderService.get_folder(folder_id, session)
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

        if not await FolderService.can_manage_folder_members(folder, auth.user_id, auth.role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot manage folder members")

        await FolderService.remove_folder_member(folder_id, member_id, session)
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing member {member_id} from folder {folder_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while removing the member",
        )


# ==================== Notebook Sharing ====================


@router.get("/folders/{folder_id}/notebooks")
async def list_folder_notebooks(
    folder_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.FOLDER_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """List notebooks shared to a folder."""
    try:
        folder = await FolderService.get_folder(folder_id, session)
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

        # Check access (member or public folder only - no admin bypass)
        if not folder.is_public:
            is_member = await FolderService.is_folder_member(folder_id, auth.user_id, session)
            if not is_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this folder"
                )

        folder_notebooks = await FolderService.list_folder_notebooks(folder_id, session)
        notebook_reads = [
            FolderNotebookRead(
                id=fn.id,
                folder_id=fn.folder_id,
                notebook_id=fn.notebook_id,
                shared_by=fn.shared_by,
                created_at=fn.created_at,
                notebook_name=fn.notebook.notebook_name if fn.notebook else None,
                notebook_description=fn.notebook.description if fn.notebook else None,
                notebook_created_by=fn.notebook.created_by if fn.notebook else None,
                shared_by_user=UserInfo.model_validate(fn.shared_by_user) if fn.shared_by_user else None,
                is_snapshot=fn.is_snapshot,
                snapshot_updated_at=fn.snapshot_updated_at,
            )
            for fn in folder_notebooks
        ]

        response = FolderNotebookListResponse(items=notebook_reads, total=len(notebook_reads))
        return success_response(data=response.model_dump(), message=f"Retrieved {len(notebook_reads)} notebook(s)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing folder notebooks for {folder_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while listing folder notebooks",
        )


@router.post("/folders/{folder_id}/notebooks", status_code=status.HTTP_201_CREATED)
async def share_notebook_to_folder(
    folder_id: UUID,
    payload: FolderNotebookShare,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_SHARE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Share a notebook to a folder. User must own the notebook and be a folder member (or folder must be public)."""
    try:
        await authorize_notebook_action(
            session=session,
            auth=auth,
            notebook_id=str(payload.notebook_id),
            action=NotebookAction.SHARE_MANAGE,
        )
        if payload.is_snapshot:
            await authorize_notebook_action(
                session=session,
                auth=auth,
                notebook_id=str(payload.notebook_id),
                action=NotebookAction.EXPORT,
            )

        folder = await FolderService.get_folder(folder_id, session)
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

        is_member = await FolderService.is_folder_member(folder_id, auth.user_id, session)
        if not is_member and not folder.is_public:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="You must be a folder member to share to private folders"
            )

        folder_notebook = await FolderService.share_notebook_to_folder(
            folder_id=folder_id,
            notebook_id=payload.notebook_id,
            shared_by=auth.user_id,
            is_snapshot=payload.is_snapshot,
            session=session,
        )

        return success_response(data={"id": str(folder_notebook.id)}, message="Notebook shared successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sharing notebook to folder {folder_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while sharing the notebook",
        )


@router.delete("/folders/{folder_id}/notebooks/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unshare_notebook_from_folder(
    folder_id: UUID,
    notebook_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_SHARE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Remove a notebook from a folder. Only the notebook creator can do this."""
    try:
        await authorize_notebook_action(
            session=session,
            auth=auth,
            notebook_id=str(notebook_id),
            action=NotebookAction.SHARE_MANAGE,
        )
        await FolderService.unshare_notebook_from_folder(
            folder_id=folder_id,
            notebook_id=notebook_id,
            user_id=auth.user_id,
            session=session,
        )
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unsharing notebook {notebook_id} from folder {folder_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while unsharing the notebook",
        )


@router.put("/folders/{folder_id}/notebooks/{notebook_id}/snapshot")
async def update_snapshot(
    folder_id: UUID,
    notebook_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_EXPORT)),
    session: AsyncSession = Depends(get_async_session),
):
    """Refresh a snapshot share to the current notebook state. Only the owner who shared can do this."""
    try:
        await authorize_notebook_action(
            session=session,
            auth=auth,
            notebook_id=str(notebook_id),
            action=NotebookAction.EXPORT,
        )
        folder_notebook = await FolderService.update_snapshot(
            folder_id=folder_id,
            notebook_id=notebook_id,
            user_id=auth.user_id,
            session=session,
        )

        return success_response(
            data={
                "snapshot_updated_at": folder_notebook.snapshot_updated_at.isoformat()
                if folder_notebook.snapshot_updated_at
                else None
            },
            message="Snapshot updated successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating snapshot for notebook {notebook_id} in folder {folder_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the snapshot",
        )


@router.post("/folders/{folder_id}/notebooks/{notebook_id}/clone", status_code=status.HTTP_201_CREATED)
async def clone_notebook_from_folder(
    folder_id: UUID,
    notebook_id: UUID,
    payload: CloneNotebookRequest = CloneNotebookRequest(),
    auth: AuthContext = Depends(require_scope(Scope.NOTEBOOK_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Clone a shared notebook. Creates a new notebook owned by the user."""
    try:
        folder = await FolderService.get_folder(folder_id, session)
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

        # Check user can access folder (member, admin, or folder is public)
        is_admin = auth.role in (TenantRole.OWNER, TenantRole.ADMIN)
        is_member = await FolderService.is_folder_member(folder_id, auth.user_id, session)
        is_public = folder.is_public
        if not is_member and not is_admin and not is_public:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="You must be a folder member to clone notebooks"
            )

        result = await FolderService.clone_notebook(
            folder_id=folder_id,
            notebook_id=notebook_id,
            user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            new_name=payload.new_name,
            session=session,
        )

        response = CloneNotebookResponse(**result)
        return success_response(data=response.model_dump(), message="Notebook cloned successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cloning notebook {notebook_id} from folder {folder_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while cloning the notebook",
        )


# ==================== Notebook -> Folders Query ====================


@router.get("/notebooks/{notebook_id}/folders")
async def list_notebook_folders(
    notebook_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.FOLDER_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """List all folders a notebook is shared to. Only notebook owner can see this."""
    try:
        # Get the list of folder_notebooks for this notebook
        folder_notebooks = await FolderService.list_folders_for_notebook(notebook_id, session)

        # Build response with folder details
        folder_reads = [
            NotebookFolderRead(
                id=fn.id,
                folder_id=fn.folder_id,
                folder_name=fn.folder.name if fn.folder else "Unknown",
                folder_description=fn.folder.description if fn.folder else None,
                shared_by=fn.shared_by,
                shared_by_user=UserInfo.model_validate(fn.shared_by_user) if fn.shared_by_user else None,
                created_at=fn.created_at,
                is_snapshot=fn.is_snapshot,
                snapshot_updated_at=fn.snapshot_updated_at,
            )
            for fn in folder_notebooks
        ]

        response = NotebookFolderListResponse(items=folder_reads, total=len(folder_reads))
        return success_response(data=response.model_dump(), message=f"Retrieved {len(folder_reads)} folder(s)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing folders for notebook {notebook_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while listing notebook folders",
        )


# ==================== Dashboard Sharing ====================


@router.get("/folders/{folder_id}/dashboards")
async def list_folder_dashboards(
    folder_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.FOLDER_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """List dashboards shared to a folder."""
    try:
        folder = await FolderService.get_folder(folder_id, session)
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

        # Check access (member or public folder only - no admin bypass)
        if not folder.is_public:
            is_member = await FolderService.is_folder_member(folder_id, auth.user_id, session)
            if not is_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this folder"
                )

        folder_dashboards = await FolderService.list_folder_dashboards(folder_id, session)
        dashboard_reads = [
            FolderDashboardRead(
                id=fd.id,
                folder_id=fd.folder_id,
                dashboard_id=fd.dashboard_id,
                shared_by=fd.shared_by,
                shared_by_user=UserInfo.model_validate(fd.shared_by_user) if fd.shared_by_user else None,
                created_at=fd.created_at,
                is_snapshot=fd.is_snapshot,
                snapshot_updated_at=fd.snapshot_updated_at,
                dashboard_version=fd.dashboard.version_num if fd.dashboard else None,
                dashboard_notebook_id=fd.dashboard.notebook_id if fd.dashboard else None,
                dashboard_notebook_name=None,  # Would need to join notebook to get this
            )
            for fd in folder_dashboards
        ]

        response = FolderDashboardListResponse(items=dashboard_reads, total=len(dashboard_reads))
        return success_response(data=response.model_dump(), message=f"Retrieved {len(dashboard_reads)} dashboard(s)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing folder dashboards for {folder_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while listing folder dashboards",
        )


@router.post("/folders/{folder_id}/dashboards", status_code=status.HTTP_201_CREATED)
async def share_dashboard_to_folder(
    folder_id: UUID,
    payload: FolderDashboardShare,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_SHARE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Share a dashboard to a folder. User must own the notebook that contains the dashboard."""
    try:
        dashboard_repo = DashboardRepository(session)
        dashboard = await dashboard_repo.get(payload.dashboard_id)
        if not dashboard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")
        await authorize_notebook_action(
            session=session,
            auth=auth,
            notebook_id=str(dashboard.notebook_id),
            action=NotebookAction.SHARE_MANAGE,
        )

        folder = await FolderService.get_folder(folder_id, session)
        if not folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

        is_member = await FolderService.is_folder_member(folder_id, auth.user_id, session)
        if not is_member and not folder.is_public:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="You must be a folder member to share to private folders"
            )

        folder_dashboard = await FolderService.share_dashboard_to_folder(
            folder_id=folder_id,
            dashboard_id=payload.dashboard_id,
            shared_by=auth.user_id,
            is_snapshot=payload.is_snapshot,
            session=session,
        )

        return success_response(data={"id": str(folder_dashboard.id)}, message="Dashboard shared successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sharing dashboard to folder {folder_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while sharing the dashboard",
        )


@router.delete("/folders/{folder_id}/dashboards/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unshare_dashboard_from_folder(
    folder_id: UUID,
    dashboard_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_SHARE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Remove a dashboard from a folder. Only the notebook creator can do this."""
    try:
        dashboard_repo = DashboardRepository(session)
        dashboard = await dashboard_repo.get(dashboard_id)
        if not dashboard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")
        await authorize_notebook_action(
            session=session,
            auth=auth,
            notebook_id=str(dashboard.notebook_id),
            action=NotebookAction.SHARE_MANAGE,
        )
        await FolderService.unshare_dashboard_from_folder(
            folder_id=folder_id,
            dashboard_id=dashboard_id,
            user_id=auth.user_id,
            session=session,
        )
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unsharing dashboard {dashboard_id} from folder {folder_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while unsharing the dashboard",
        )


@router.put("/folders/{folder_id}/dashboards/{dashboard_id}")
async def update_folder_dashboard_version(
    folder_id: UUID,
    dashboard_id: UUID,
    payload: FolderDashboardUpdate,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_SHARE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Update a shared dashboard to a different version. Only the notebook creator can do this."""
    try:
        dashboard_repo = DashboardRepository(session)
        old_dashboard = await dashboard_repo.get(dashboard_id)
        if not old_dashboard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original dashboard not found")
        new_dashboard = await dashboard_repo.get(payload.new_dashboard_id)
        if not new_dashboard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="New dashboard not found")
        await authorize_notebook_action(
            session=session,
            auth=auth,
            notebook_id=str(old_dashboard.notebook_id),
            action=NotebookAction.SHARE_MANAGE,
        )
        if new_dashboard.notebook_id != old_dashboard.notebook_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New dashboard must be from the same notebook",
            )
        folder_dashboard = await FolderService.update_folder_dashboard_version(
            folder_id=folder_id,
            old_dashboard_id=dashboard_id,
            new_dashboard_id=payload.new_dashboard_id,
            user_id=auth.user_id,
            session=session,
        )
        return success_response(
            data={"id": str(folder_dashboard.id), "new_dashboard_id": str(payload.new_dashboard_id)},
            message="Dashboard version updated successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating dashboard version in folder {folder_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the dashboard version",
        )


# ==================== Dashboard -> Folders Query ====================


@router.get("/dashboards/{dashboard_id}/folders")
async def list_dashboard_folders(
    dashboard_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.FOLDER_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """List all folders a dashboard is shared to. Only dashboard owner can see this."""
    try:
        # Get the list of folder_dashboards for this dashboard
        folder_dashboards = await FolderService.list_folders_for_dashboard(dashboard_id, session)

        # Build response with folder details
        folder_reads = [
            DashboardFolderRead(
                id=fd.id,
                folder_id=fd.folder_id,
                folder_name=fd.folder.name if fd.folder else "Unknown",
                folder_description=fd.folder.description if fd.folder else None,
                shared_by=fd.shared_by,
                shared_by_user=UserInfo.model_validate(fd.shared_by_user) if fd.shared_by_user else None,
                created_at=fd.created_at,
                is_snapshot=fd.is_snapshot,
                snapshot_updated_at=fd.snapshot_updated_at,
            )
            for fd in folder_dashboards
        ]

        response = DashboardFolderListResponse(items=folder_reads, total=len(folder_reads))
        return success_response(data=response.model_dump(), message=f"Retrieved {len(folder_reads)} folder(s)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing folders for dashboard {dashboard_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while listing dashboard folders",
        )


@router.get("/notebooks/{notebook_id}/dashboard-folders")
async def list_notebook_dashboard_folders(
    notebook_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.FOLDER_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """List all folders where any dashboard version of a notebook is shared."""
    try:
        notebook_repo = NotebookRepository(session)
        notebook = await notebook_repo.get(notebook_id)
        if not notebook:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found")
        if notebook.created_by != auth.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Only notebook owner can view dashboard folder shares"
            )

        folders = await FolderService.list_folders_for_notebook_dashboards(notebook_id, session)
        return success_response(data={"items": folders, "total": len(folders)})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing notebook dashboard folders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while listing notebook dashboard folders",
        )


# ==================== All Dashboards Endpoint ====================


@router.get("/dashboards")
async def list_all_dashboards(
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """List all dashboards accessible to the current user, grouped by folder.

    Returns folders user is member of + public folders, with their dashboards.
    """
    try:
        result = await FolderService.list_all_accessible_dashboards(
            user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            session=session,
        )
        return success_response(
            data=result,
            message=f"Retrieved {result['total_dashboards']} dashboard(s) across {len(result['folders'])} folder(s)",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing all dashboards: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while listing dashboards",
        )


# ==================== Viewer Endpoints ====================


@router.get("/viewer/dashboards")
async def list_viewer_dashboards(
    auth: AuthContext = Depends(require_scope(Scope.VIEWER_DASHBOARD_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """List all dashboards accessible to the current viewer through folder membership.

    Returns a flat list of dashboards (no folder navigation).
    """
    try:
        dashboards = await FolderService.list_dashboards_for_viewer(
            user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            session=session,
        )
        return success_response(
            data={"items": dashboards, "total": len(dashboards)},
            message=f"Retrieved {len(dashboards)} accessible dashboard(s)",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing viewer dashboards: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while listing dashboards",
        )


@router.get("/viewer/dashboards/{dashboard_id}")
async def get_viewer_dashboard(
    dashboard_id: UUID,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_any_scope(Scope.DASHBOARD_READ, Scope.VIEWER_DASHBOARD_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """Get dashboard content for any user with dashboard access.

    Returns dashboard if user has access through:
    - Folder membership
    - Public folder
    """

    try:
        # Check access via folder membership or public folder
        folder_grant = await _dashboard_folder_grant_for_user(
            dashboard_id=dashboard_id,
            user_id=auth.user_id,
            session=session,
        )

        if not folder_grant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this dashboard",
            )

        # Fetch dashboard
        dashboard_repo = DashboardRepository(session)
        dashboard = await dashboard_repo.get(dashboard_id)

        if not dashboard:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dashboard not found",
            )

        from server.utils.deployment import should_use_secure_cookie

        canonical_grant = await SharingService(session).ensure_folder_dashboard_grant(
            tenant_id=dashboard.tenant_id,
            actor_id=folder_grant.shared_by or auth.user_id,
            folder_dashboard_id=folder_grant.id,
            dashboard_id=dashboard.id,
        )
        viewer_token, _ = await SharingService(session).issue_viewer_session_for_grant(
            grant=canonical_grant,
            viewer_user_id=auth.user_id,
            principal={"surface": "folder_dashboard", "legacy_grant_id": str(folder_grant.id)},
        )

        response.set_cookie(
            key="viewer_session",
            value=viewer_token,
            httponly=True,
            secure=should_use_secure_cookie(request),
            samesite="lax",
            max_age=VIEWER_SESSION_MINUTES * 60,
            path="/api/viewer",
        )

        return success_response(
            data={
                "id": str(dashboard.id),
                "html_content": dashboard.html_content,
                "version": dashboard.version_num,
                "notebook_id": str(dashboard.notebook_id),
                "created_at": dashboard.created_at.isoformat() if dashboard.created_at else None,
            },
            message="Dashboard retrieved successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching viewer dashboard {dashboard_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching the dashboard",
        )


@router.get("/viewer/dashboards/{dashboard_id}/filters")
async def get_viewer_dashboard_filters(
    dashboard_id: UUID,
    auth: AuthContext = Depends(require_any_scope(Scope.DASHBOARD_READ, Scope.VIEWER_DASHBOARD_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """Get saved filter config for a shared dashboard."""
    try:
        can_access = await FolderService.can_access_dashboard_via_folder(
            dashboard_id=dashboard_id,
            user_id=auth.user_id,
            session=session,
        )

        if not can_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this dashboard",
            )

        dashboard_repo = DashboardRepository(session)
        dashboard = await dashboard_repo.get(dashboard_id)
        if not dashboard:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dashboard not found",
            )

        notebook = await NotebookService.get_notebook(session, str(dashboard.notebook_id))
        if not notebook:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notebook not found for this dashboard",
            )

        config_payload: dict[str, object] = {"filters": [], "version": 1, "created_at": None}
        if notebook.filters_config:
            try:
                parsed = json.loads(notebook.filters_config)
                if isinstance(parsed, dict):
                    raw_filters = parsed.get("filters")
                    if isinstance(raw_filters, list):
                        config_payload["filters"] = normalize_filters_for_client(
                            [f for f in raw_filters if isinstance(f, dict)]
                        )
                    version = parsed.get("version")
                    if isinstance(version, int):
                        config_payload["version"] = version
                    created_at = parsed.get("created_at")
                    if isinstance(created_at, str):
                        config_payload["created_at"] = created_at
            except json.JSONDecodeError:
                logger.warning(
                    "Invalid filters_config JSON for dashboard %s",
                    str(dashboard_id),
                    posthog_context={
                        "function": "get_viewer_dashboard_filters",
                        "dashboard_id": str(dashboard_id),
                    },
                )

        return success_response(data=config_payload, message="Dashboard filters retrieved successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching viewer dashboard filters {dashboard_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching dashboard filters",
        )


@router.post("/viewer/dashboards/{dashboard_id}/queries/batch", response_model=BatchExecuteSavedQueriesResponse)
async def execute_viewer_dashboard_queries(
    dashboard_id: UUID,
    request: BatchExecuteSavedQueriesRequest,
    session: AsyncSession = Depends(get_async_session),
    viewer_session: str | None = Cookie(default=None, alias="viewer_session"),
    origin: str | None = Header(default=None, alias="Origin"),
):
    """Execute batch queries for a shared dashboard.

    Verifies user has access to the dashboard via folder membership or public folder,
    then executes the queries. Query execution validates access at the service level.
    """
    try:
        is_tauri_local = not is_self_hosted() and origin and origin.startswith("tauri://")
        if not is_tauri_local:
            viewer_user_id = await _require_viewer_session(dashboard_id, viewer_session, session)

            can_access = await FolderService.can_access_dashboard_via_folder(
                dashboard_id=dashboard_id,
                user_id=viewer_user_id,
                session=session,
            )
            if not can_access:
                dashboard_repo = DashboardRepository(session)
                dashboard = await dashboard_repo.get(dashboard_id)
                if dashboard:
                    notebook = await NotebookService.get_notebook(session, str(dashboard.notebook_id))
                    if notebook and notebook.created_by and str(notebook.created_by) == str(viewer_user_id):
                        can_access = True

            if not can_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have access to this dashboard",
                )

        await _require_viewer_dashboard_query_bindings(dashboard_id, request, session)

        if request.queries_with_filters:
            result = await QueryService.execute_batch_saved_queries(
                session=session,
                queries_with_filters=[q.dict() for q in request.queries_with_filters],
                max_parallel=request.max_parallel,
            )
        else:
            result = await QueryService.execute_batch_saved_queries(
                session=session,
                query_ids=request.query_ids,
                max_parallel=request.max_parallel,
            )

        return BatchExecuteSavedQueriesResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing viewer dashboard queries {dashboard_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while executing dashboard queries",
        )


@router.post("/viewer/dashboards/{dashboard_id}/queries/batch/preflight", response_model=BatchFilterPreflightResponse)
async def preflight_viewer_dashboard_queries(
    dashboard_id: UUID,
    request: BatchExecuteSavedQueriesRequest,
    session: AsyncSession = Depends(get_async_session),
    viewer_session: str | None = Cookie(default=None, alias="viewer_session"),
    origin: str | None = Header(default=None, alias="Origin"),
):
    """Validate/compile shared-dashboard filters without executing query SQL/Mongo."""
    try:
        is_tauri_local = not is_self_hosted() and origin and origin.startswith("tauri://")
        if not is_tauri_local:
            viewer_user_id = await _require_viewer_session(dashboard_id, viewer_session, session)

            can_access = await FolderService.can_access_dashboard_via_folder(
                dashboard_id=dashboard_id,
                user_id=viewer_user_id,
                session=session,
            )
            if not can_access:
                dashboard_repo = DashboardRepository(session)
                dashboard = await dashboard_repo.get(dashboard_id)
                if dashboard:
                    notebook = await NotebookService.get_notebook(session, str(dashboard.notebook_id))
                    if notebook and notebook.created_by and str(notebook.created_by) == str(viewer_user_id):
                        can_access = True

            if not can_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have access to this dashboard",
                )

        await _require_viewer_dashboard_query_bindings(dashboard_id, request, session)

        result = await QueryService.preflight_batch_query_filters(
            session=session,
            query_ids=request.query_ids,
            queries_with_filters=[q.model_dump() for q in request.queries_with_filters]
            if request.queries_with_filters
            else None,
        )

        return BatchFilterPreflightResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error preflighting viewer dashboard queries {dashboard_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while preflighting dashboard queries",
        )
