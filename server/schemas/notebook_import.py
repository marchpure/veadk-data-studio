from __future__ import annotations

from pydantic import BaseModel, Field

from server.schemas.notebook_export import NotebookExport


class NotebookSummary(BaseModel):
    """Summary information about a fetched notebook."""

    title: str
    description: str | None = None
    datasets_count: int
    queries_count: int
    messages_count: int
    dashboards_count: int


class FetchNotebookRequest(BaseModel):
    """Request body for fetching a shared notebook from worker."""

    share_id: str = Field(..., description="UUID of the shared notebook")
    password: str | None = Field(None, description="Password for protected shares")


class FetchNotebookResponse(BaseModel):
    """Response from fetching a shared notebook."""

    notebook_export: NotebookExport
    summary: NotebookSummary


class TestQueryRequest(BaseModel):
    """Request body for testing a query on an existing connection or dataset."""

    connection_id: str | None = Field(None, description="ID of an existing database connection")
    dataset_id: str | None = Field(None, description="ID of a file-based dataset")
    query: str


class TestQueryResponse(BaseModel):
    """Response from testing a query."""

    success: bool
    error: str | None = None


class TestConnectionRequest(BaseModel):
    """Request body for testing a new connection with a query."""

    connection_type: str = Field(..., description="postgresql, mongodb, mysql, sqlite, mssql")
    connection_obj: dict = Field(..., description="Connection parameters (host, port, database, user, password, etc.)")
    test_query: str


class TestConnectionResponse(BaseModel):
    """Response from testing a new connection."""

    success: bool
    connection_valid: bool
    query_valid: bool
    error: str | None = None


class DatasetMapping(BaseModel):
    """Mapping of an exported dataset to a local connection or existing dataset."""

    dataset_index: int = Field(..., description="Index of the dataset in the export")
    connection_id: str | None = Field(None, description="ID of existing connection to use (creates new dataset)")
    dataset_id: str | None = Field(None, description="ID of existing dataset to attach (no creation)")
    skipped: bool = Field(default=False, description="Whether to skip this dataset")


class ImportedCounts(BaseModel):
    """Counts of imported items."""

    datasets: int
    queries: int
    messages: int
    dashboards: int


class ImportNotebookRequest(BaseModel):
    """Request body for importing a notebook."""

    notebook_export: NotebookExport
    dataset_mappings: list[DatasetMapping]


class ImportNotebookResponse(BaseModel):
    """Response from importing a notebook."""

    notebook_id: str
    imported: ImportedCounts
    skipped_datasets: int
