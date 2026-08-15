from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from server.schemas.tenant import UserInfo

# ==================== Folder Schemas ====================


class FolderCreate(BaseModel):
    """Request schema for creating a new folder."""

    name: str
    description: str | None = None
    is_public: bool = False


class FolderUpdate(BaseModel):
    """Request schema for updating a folder."""

    name: str | None = None
    description: str | None = None
    is_public: bool | None = None


class FolderRead(BaseModel):
    """Response schema for folder details."""

    id: UUID
    tenant_id: UUID
    created_by: UUID
    name: str
    description: str | None = None
    is_public: bool = False
    created_at: datetime
    updated_at: datetime
    creator: UserInfo | None = None
    member_count: int | None = None
    notebook_count: int | None = None

    model_config = {
        "from_attributes": True,
    }


class FolderListResponse(BaseModel):
    """Response schema for listing folders."""

    items: list[FolderRead]
    total: int


# ==================== Folder Member Schemas ====================


class FolderMemberAdd(BaseModel):
    """Request schema for adding a member to a folder."""

    user_id: UUID


class FolderMemberBulkAdd(BaseModel):
    """Request schema for adding multiple members to a folder."""

    user_ids: list[UUID]


class FolderMemberRead(BaseModel):
    """Response schema for folder member details."""

    id: UUID
    folder_id: UUID
    user_id: UUID
    added_by: UUID | None = None
    created_at: datetime
    user: UserInfo | None = None
    added_by_user: UserInfo | None = None

    model_config = {
        "from_attributes": True,
    }


class FolderMemberListResponse(BaseModel):
    """Response schema for listing folder members."""

    items: list[FolderMemberRead]
    total: int


# ==================== Folder Notebook Schemas ====================


class FolderNotebookShare(BaseModel):
    """Request schema for sharing a notebook to a folder."""

    notebook_id: UUID
    is_snapshot: bool = False  # False = live share, True = frozen snapshot


class FolderNotebookRead(BaseModel):
    """Response schema for folder notebook details."""

    id: UUID
    folder_id: UUID
    notebook_id: UUID
    shared_by: UUID | None = None
    created_at: datetime
    notebook_name: str | None = None
    notebook_description: str | None = None
    notebook_created_by: UUID | None = None
    shared_by_user: UserInfo | None = None
    is_snapshot: bool = False
    snapshot_updated_at: datetime | None = None

    model_config = {
        "from_attributes": True,
    }


class FolderNotebookListResponse(BaseModel):
    """Response schema for listing folder notebooks."""

    items: list[FolderNotebookRead]
    total: int


# ==================== Notebook Folders Schemas ====================


class NotebookFolderRead(BaseModel):
    """Response schema for listing folders a notebook is shared to."""

    id: UUID  # folder_notebook.id
    folder_id: UUID
    folder_name: str
    folder_description: str | None = None
    shared_by: UUID | None = None
    shared_by_user: UserInfo | None = None
    created_at: datetime
    is_snapshot: bool = False
    snapshot_updated_at: datetime | None = None

    model_config = {
        "from_attributes": True,
    }


class NotebookFolderListResponse(BaseModel):
    """Response schema for listing folders a notebook is shared to."""

    items: list[NotebookFolderRead]
    total: int


# ==================== Folder Dashboard Schemas ====================


class FolderDashboardShare(BaseModel):
    """Request schema for sharing a dashboard to a folder."""

    dashboard_id: UUID
    is_snapshot: bool = False  # Deprecated - dashboards are always version-based now


class FolderDashboardUpdate(BaseModel):
    """Request schema for updating a shared dashboard's version."""

    new_dashboard_id: UUID  # The dashboard ID with the new version


class FolderDashboardRead(BaseModel):
    """Response schema for folder dashboard details."""

    id: UUID
    folder_id: UUID
    dashboard_id: UUID
    shared_by: UUID | None = None
    shared_by_user: UserInfo | None = None
    created_at: datetime
    is_snapshot: bool = False
    snapshot_updated_at: datetime | None = None
    # Dashboard info
    dashboard_version: int | None = None
    dashboard_notebook_id: UUID | None = None
    dashboard_notebook_name: str | None = None

    model_config = {
        "from_attributes": True,
    }


class FolderDashboardListResponse(BaseModel):
    """Response schema for listing folder dashboards."""

    items: list[FolderDashboardRead]
    total: int


# ==================== Dashboard Folders Schemas ====================


class DashboardFolderRead(BaseModel):
    """Response schema for listing folders a dashboard is shared to."""

    id: UUID  # folder_dashboard.id
    folder_id: UUID
    folder_name: str
    folder_description: str | None = None
    shared_by: UUID | None = None
    shared_by_user: UserInfo | None = None
    created_at: datetime
    is_snapshot: bool = False
    snapshot_updated_at: datetime | None = None

    model_config = {
        "from_attributes": True,
    }


class DashboardFolderListResponse(BaseModel):
    """Response schema for listing folders a dashboard is shared to."""

    items: list[DashboardFolderRead]
    total: int


# ==================== Clone Notebook Schemas ====================


class CloneNotebookRequest(BaseModel):
    """Request schema for cloning a notebook from a folder."""

    new_name: str | None = None  # Optional, defaults to "Copy of {original_name}"


class CloneNotebookResponse(BaseModel):
    """Response schema for cloned notebook."""

    notebook_id: UUID
    notebook_name: str
    messages_cloned: int = 0
    queries_cloned: int = 0
    dashboards_cloned: int = 0
    datasets_cloned: int = 0
    connection_access_warnings: list[str] | None = None  # Warnings about missing connection access
