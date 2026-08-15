from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from server.schemas.connections import ConnectionCreate, ConnectionRead


class NotebookDatasetRead(BaseModel):
    """
    Response schema for notebook-dataset associations.
    Represents the junction between notebooks and datasets (unified abstraction for connections and files).
    """

    id: UUID  # Dataset ID
    notebook_id: UUID
    dataset_id: UUID
    dataset_type: str  # "connection" | "file"
    connection_id: UUID | None = None  # Present for connection-type datasets
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class DatasetConnectRequest(BaseModel):
    """
    Request schema for connecting a notebook to a datasource.
    Supports both creating a new connection or using an existing one.
    Also supports multiple connections for multi-database notebooks.
    """

    # Single connection (backward compatibility)
    connection_id: str | UUID | None = None  # ID of existing connection
    connection: ConnectionCreate | None = None  # New connection to create
    # Multiple connections (multi-database support)
    connection_ids: list[str | UUID] | None = None  # IDs of existing connections
    connections: list[ConnectionCreate] | None = None  # New connections to create


class DatasetConnectResponse(BaseModel):
    """
    Response schema for datasource connection operations.
    Returns the dataset association and connection details.
    Also supports multiple datasets for multi-database notebooks.
    """

    # Single dataset (backward compatibility)
    dataset: NotebookDatasetRead | None = None
    connection: ConnectionRead | None = None
    # Multiple datasets (multi-database support)
    datasets: list[NotebookDatasetRead] | None = None
    connections: list[ConnectionRead] | None = None


class DatasetAssociateRequest(BaseModel):
    """
    Request schema for associating an existing dataset (connection or files) with a notebook.
    Supports batch association for both datasets and connections.
    """

    dataset_id: str | UUID | None = None  # For associating single existing dataset
    connection_id: str | UUID | None = None  # For backward compatibility - creates dataset from connection
    # Batch association (multi-database support)
    dataset_ids: list[str | UUID] | None = None  # IDs of existing datasets to associate
    connection_ids: list[str | UUID] | None = None  # IDs of existing connections to associate
