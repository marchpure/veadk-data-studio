from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class DatasourceAnnotationBase(BaseModel):
    """Base schema for datasource annotations."""

    datasource_id: UUID = Field(..., description="ID of the datasource this annotation belongs to")
    table_name: str = Field(..., description="Name of the table being annotated")
    column_name: str | None = Field(None, description="Name of the column (null for table-level annotations)")
    annotation_type: Literal["table_description", "column_annotation", "column_redaction", "table_redaction"] = Field(
        ...,
        description="Type of annotation: 'table_description', 'column_annotation', 'column_redaction', or 'table_redaction'",
    )
    content: str = Field(..., description="The annotation content/text")


class DatasourceAnnotationCreate(BaseModel):
    """Schema for creating a new annotation."""

    table_name: str = Field(..., description="Name of the table being annotated")
    column_name: str | None = Field(None, description="Name of the column (null for table-level annotations)")
    annotation_type: Literal["table_description", "column_annotation", "column_redaction", "table_redaction"] = Field(
        ...,
        description="Type of annotation: 'table_description', 'column_annotation', 'column_redaction', or 'table_redaction'",
    )
    content: str = Field(..., description="The annotation content/text")


class DatasourceAnnotationUpdate(BaseModel):
    """Schema for updating an existing annotation."""

    content: str = Field(..., description="The updated annotation content/text")


class DatasourceAnnotationResponse(DatasourceAnnotationBase):
    """Schema for annotation responses."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
