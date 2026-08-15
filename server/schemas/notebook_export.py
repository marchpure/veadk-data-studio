from __future__ import annotations

from pydantic import BaseModel, Field


class ExportedQuery(BaseModel):
    """A query exported as part of a notebook share."""

    id: str
    name: str
    query: str
    output_schema: str | None = None
    description: str | None = None


class ExportedDataset(BaseModel):
    """A dataset exported as part of a notebook share.

    Contains metadata about the original data source without credentials.
    Recipients will need to connect their own database of the same type.
    """

    original_name: str = Field(..., description="Display name of the original dataset")
    type: str = Field(
        ..., description="Database type: postgresql, mongodb, mysql, sqlite, mssql, csv_bundle, excel_bundle"
    )
    queries: list[ExportedQuery] = Field(default_factory=list, description="Saved queries for this dataset")
    files: list[str] | None = Field(None, description="File names for csv_bundle/excel_bundle types")


class ExportedMessage(BaseModel):
    """A chat message exported as part of the conversation history."""

    role: str = Field(..., description="Message role: user, assistant, system, tool")
    content: str
    created_at: str | None = Field(None, description="ISO timestamp when message was created (for preserving order)")


class ExportedDashboard(BaseModel):
    """A dashboard version exported as part of a notebook share."""

    version: int
    html_content: str


class NotebookExport(BaseModel):
    """Complete notebook export format for sharing.

    This is the JSON structure stored in Cloudflare D1 and shared via UUID URL.
    Recipients can import this to create a new notebook with their own data sources.
    """

    id: str = Field(..., description="Original notebook UUID")
    title: str = Field(..., description="Notebook name")
    description: str | None = None
    chat_history: list[ExportedMessage] = Field(default_factory=list, description="Conversation history")
    dashboards: list[ExportedDashboard] = Field(default_factory=list, description="All dashboard versions")
    datasets: list[ExportedDataset] = Field(default_factory=list, description="Required data sources")
    exported_at: str = Field(..., description="ISO timestamp of export")
    byaan_version: str = Field(default="1.0", description="Export format version")


# Connection type mapping from internal to export format
CONNECTION_TYPE_MAP = {
    "pg": "postgresql",
    "mysql": "mysql",
    "mongo": "mongodb",
    "sqlite": "sqlite",
    "mssql": "mssql",
}


def map_connection_type(internal_type: str) -> str:
    """Map internal connection type to export format type."""
    return CONNECTION_TYPE_MAP.get(internal_type, internal_type)


# Request/Response schemas for the API endpoints
class ShareNotebookJsonRequest(BaseModel):
    """Request body for sharing a notebook as JSON."""

    password: str | None = Field(None, description="Optional password to protect the share")


class ShareNotebookJsonResponse(BaseModel):
    """Response from sharing a notebook as JSON."""

    share_id: str
