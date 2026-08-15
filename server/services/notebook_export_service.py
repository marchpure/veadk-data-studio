"""
Notebook Export Service

Handles exporting notebooks to JSON format for sharing.
This service serializes all notebook data (chat history, dashboards, queries, datasets)
into a portable format that can be shared via Cloudflare D1.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from server.models.connections import Connection
from server.models.files import File
from server.models.messages import Message
from server.models.notebooks import Notebook, NotebookDataset
from server.models.queries import Query
from server.models.threads import Thread
from server.schemas.notebook_export import (
    ExportedDashboard,
    ExportedDataset,
    ExportedMessage,
    ExportedQuery,
    NotebookExport,
    map_connection_type,
)
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


class NotebookExportService:
    """Service for exporting notebooks to shareable JSON format."""

    @staticmethod
    async def export_notebook(session: AsyncSession, notebook_id: str) -> NotebookExport:
        """
        Export a notebook to JSON format for sharing.

        Args:
            session: Database session
            notebook_id: UUID of the notebook to export

        Returns:
            NotebookExport model containing all notebook data

        Raises:
            ValueError: If notebook not found
        """
        logger.info(f"Exporting notebook {notebook_id}")

        # Fetch notebook with eager loading
        result = await session.execute(
            select(Notebook)
            .where(Notebook.id == notebook_id)
            .options(
                selectinload(Notebook.notebook_datasets).selectinload(NotebookDataset.dataset),
                selectinload(Notebook.dashboards),
            )
        )
        notebook = result.scalar_one_or_none()

        if not notebook:
            raise ValueError(f"Notebook with ID {notebook_id} not found")

        # Export chat history
        chat_history = await NotebookExportService._export_chat_history(session, notebook_id)

        # Export dashboards
        dashboards = await NotebookExportService._export_dashboards(notebook)

        # Export datasets with their queries
        datasets = await NotebookExportService._export_datasets(session, notebook)

        return NotebookExport(
            id=str(notebook.id),
            title=notebook.notebook_name,
            description=notebook.description,
            chat_history=chat_history,
            dashboards=dashboards,
            datasets=datasets,
            exported_at=datetime.now(UTC).isoformat(),
            byaan_version="1.0",
        )

    @staticmethod
    async def _export_chat_history(session: AsyncSession, notebook_id: str) -> list[ExportedMessage]:
        """Export conversation history from the notebook's thread."""
        # Get the first thread for this notebook
        threads_result = await session.execute(select(Thread).where(Thread.notebook_id == notebook_id))
        threads = list(threads_result.scalars().all())

        messages = []
        if threads:
            thread = threads[0]
            messages_result = await session.execute(
                select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)
            )
            db_messages = list(messages_result.scalars().all())

            for msg in db_messages:
                # Only export user and assistant messages (skip tool messages)
                if msg.role in ("user", "assistant"):
                    messages.append(
                        ExportedMessage(
                            role=msg.role,
                            content=msg.content or "",
                            created_at=msg.created_at.isoformat() if msg.created_at else None,
                        )
                    )

        logger.info(f"Exported {len(messages)} messages from chat history")
        return messages

    @staticmethod
    async def _export_dashboards(notebook: Notebook) -> list[ExportedDashboard]:
        """Export all dashboard versions."""
        dashboards = []
        for dashboard in notebook.dashboards:
            dashboards.append(
                ExportedDashboard(
                    version=dashboard.version_num,
                    html_content=dashboard.html_content or "",
                )
            )

        # Sort by version
        dashboards.sort(key=lambda d: d.version)
        logger.info(f"Exported {len(dashboards)} dashboard versions")
        return dashboards

    @staticmethod
    async def _export_datasets(session: AsyncSession, notebook: Notebook) -> list[ExportedDataset]:
        """Export datasets with their queries, grouped by data source."""
        datasets = []

        for nb_dataset in notebook.notebook_datasets:
            dataset = nb_dataset.dataset

            # Determine the type and name
            if dataset.type == "connection" and dataset.connection_id:
                # Fetch connection to get type
                conn_result = await session.execute(select(Connection).where(Connection.id == dataset.connection_id))
                connection = conn_result.scalar_one_or_none()

                if connection:
                    export_type = map_connection_type(connection.type)
                    original_name = connection.name or dataset.name or f"{export_type} Connection"
                else:
                    export_type = "unknown"
                    original_name = dataset.name or "Unknown Connection"

                # Get queries for this dataset
                queries = await NotebookExportService._export_queries_for_dataset(session, dataset.id, notebook.id)

                datasets.append(
                    ExportedDataset(
                        original_name=original_name,
                        type=export_type,
                        queries=queries,
                        files=None,
                    )
                )

            elif dataset.type == "file":
                # Fetch files for this dataset
                files_result = await session.execute(select(File).where(File.dataset_id == dataset.id))
                files = list(files_result.scalars().all())

                # Determine file bundle type based on file extensions
                file_names = [f.name for f in files]
                export_type = NotebookExportService._determine_file_bundle_type(file_names)
                original_name = dataset.name or "File Dataset"

                # Get queries for this dataset
                queries = await NotebookExportService._export_queries_for_dataset(session, dataset.id, notebook.id)

                datasets.append(
                    ExportedDataset(
                        original_name=original_name,
                        type=export_type,
                        queries=queries,
                        files=file_names,
                    )
                )

        logger.info(f"Exported {len(datasets)} datasets")
        return datasets

    @staticmethod
    async def _export_queries_for_dataset(
        session: AsyncSession, dataset_id: str, notebook_id: str
    ) -> list[ExportedQuery]:
        """Export all queries associated with a dataset in a notebook."""
        queries_result = await session.execute(
            select(Query).where(Query.dataset_id == dataset_id, Query.notebook_id == notebook_id)
        )
        queries = list(queries_result.scalars().all())

        exported = []
        for query in queries:
            exported.append(
                ExportedQuery(
                    id=str(query.id),
                    name=query.name,
                    query=query.query,
                    output_schema=query.output_schema,
                    description=None,  # Queries don't have descriptions in the current model
                )
            )

        return exported

    @staticmethod
    def _determine_file_bundle_type(file_names: list[str]) -> str:
        """Determine the bundle type based on file extensions."""
        if not file_names:
            return "file_bundle"

        # Get unique extensions
        extensions = {name.rsplit(".", 1)[-1].lower() for name in file_names if "." in name}

        if extensions == {"csv"}:
            return "csv_bundle"
        elif extensions <= {"xlsx", "xls"}:
            return "excel_bundle"
        return "file_bundle"
