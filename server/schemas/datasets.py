"""Schemas for Dataset API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FileInfo(BaseModel):
    """File information for dataset responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    type: str
    size: int | None
    source_url: str | None = None
    uploaded_at: datetime


class DatasetCreate(BaseModel):
    """Schema for creating a new dataset."""

    type: Literal["connection", "file"]
    name: str | None = None
    connection_id: str | UUID | None = None
    notebook_id: str | UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class DatasetUpdate(BaseModel):
    """Schema for updating a dataset (file-based datasets only).

    Note: new_files are handled via FastAPI File() parameter in the endpoint,
    not as part of this Pydantic schema.
    """

    name: str | None = None
    files: list[dict] | None = None  # List of files to keep/update with their metadata
    is_public: bool | None = None

    model_config = ConfigDict(from_attributes=True)


class DatasetRead(BaseModel):
    """Schema for reading dataset information."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    name: str | None
    connection_id: UUID | None
    files: list[FileInfo] | None = None
    created_at: datetime


class ConnectionDetails(BaseModel):
    """Connection details for dataset response."""

    id: UUID
    type: str
    name: str | None
    schema: dict | None = None


class DatasetWithDetails(DatasetRead):
    """Schema for dataset with full connection or file details."""

    connection_details: ConnectionDetails | None = None
    schema: dict | None = None  # Cached schema for the dataset

    model_config = ConfigDict(from_attributes=True)


class DatasetListResponse(BaseModel):
    """Schema for listing datasets."""

    items: list[DatasetRead]
    total: int

    model_config = ConfigDict(from_attributes=True)
