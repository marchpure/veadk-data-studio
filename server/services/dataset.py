"""Service layer for Dataset operations."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from server.auth.tenant_context import get_tenant_id
from server.config.storage import dataset_directory
from server.models.datasets import Dataset
from server.models.notebooks import NotebookDataset
from server.repositories.connections import ConnectionRepository
from server.services.dataset_storage import DatasetStorageService

logger = logging.getLogger(__name__)


class DatasetService:
    """Service for managing datasets and their data sources."""

    @staticmethod
    async def create_dataset(
        session: AsyncSession,
        type: str,
        connection_id: str | None = None,
        notebook_id: str | None = None,
        name: str | None = None,
        tenant_id: UUID | None = None,
        created_by: UUID | None = None,
        skill_name: str | None = None,
        skill_scope: str | None = None,
    ) -> Dataset:
        """
        Create a new dataset (independent from notebooks).

        Args:
            session: Database session
            type: Dataset type ('connection', 'file', or 'skill_api')
            connection_id: Connection ID (required for type='connection')
            notebook_id: Optional notebook ID to associate immediately
            name: Optional name for the dataset (especially for file datasets)
            tenant_id: Optional tenant ID to associate the dataset with
            skill_name: Skill name (required for type='skill_api')
            skill_scope: Scope preference for skill credentials ('user' or 'org')

        Returns:
            Created dataset

        Raises:
            ValueError: If validation fails
        """
        if type == "connection" and not connection_id:
            raise ValueError("connection_id is required for connection-type datasets")

        if type == "skill_api" and not skill_name:
            raise ValueError("skill_name is required for skill_api-type datasets")

        if type == "connection" and connection_id:
            # Verify connection exists
            conn_repo = ConnectionRepository(session)
            connection = await conn_repo.get(connection_id)
            if not connection:
                raise ValueError(f"Connection {connection_id} not found")

            # Check if a Dataset already exists for this connection_id
            # Use .first() since there may be multiple datasets per connection (from different notebooks)
            existing_dataset_stmt = select(Dataset).where(Dataset.connection_id == connection_id)
            existing_result = await session.execute(existing_dataset_stmt)
            existing_dataset = existing_result.scalars().first()

            if existing_dataset:
                if notebook_id:
                    try:
                        await DatasetService.associate_dataset_with_notebook(session, existing_dataset.id, notebook_id)
                    except ValueError as e:
                        if "already associated" in str(e):
                            logger.info(f"Dataset {existing_dataset.id} already associated with notebook {notebook_id}")
                        else:
                            raise
                logger.info(f"Reusing existing dataset {existing_dataset.id} for connection {connection_id}")
                return existing_dataset

        # Use tenant_id from context if not explicitly provided
        effective_tenant_id = tenant_id or get_tenant_id()
        dataset = Dataset(
            type=type,
            name=name,
            connection_id=connection_id,
            tenant_id=effective_tenant_id,
            created_by=created_by,
            skill_name=skill_name if type == "skill_api" else None,
            skill_scope=skill_scope or "user" if type == "skill_api" else None,
        )

        try:
            session.add(dataset)
            await session.flush()

            if type == "file":
                dataset_dir = dataset_directory(str(dataset.id))
                dataset.storage_path = str(dataset_dir)
                dataset.duckdb_path = str(dataset_dir / "duckdb" / "dataset.duckdb")

            await session.commit()
            await session.refresh(dataset)
        except Exception:
            await session.rollback()
            raise

        # If notebook_id provided, also create junction table entry
        if notebook_id:
            await DatasetService.associate_dataset_with_notebook(session, dataset.id, notebook_id)

        logger.info(f"Created dataset {dataset.id} (type: {type})")
        return dataset

    @staticmethod
    async def get_datasets_by_notebook(
        session: AsyncSession,
        notebook_id: str,
    ) -> list[Dataset]:
        """
        Get all datasets for a notebook with their files loaded.

        Args:
            session: Database session
            notebook_id: Notebook ID

        Returns:
            List of datasets
        """
        from server.repositories.datasets import DatasetRepository

        # Use repository for tenant-filtered query
        repo = DatasetRepository(session)
        return await repo.get_by_notebook(notebook_id)

    @staticmethod
    async def get_dataset_with_details(
        session: AsyncSession,
        dataset_id: str,
    ) -> dict[str, Any] | None:
        """
        Get dataset with full details including connection info or files.

        Args:
            session: Database session
            dataset_id: Dataset ID

        Returns:
            Dict with dataset details or None if not found
        """
        stmt = select(Dataset).where(Dataset.id == dataset_id).options(joinedload(Dataset.files))
        result = await session.execute(stmt)
        dataset = result.unique().scalar_one_or_none()

        if not dataset:
            return None

        dataset_dict = {
            "id": dataset.id,
            # Note: notebook_id removed as datasets use junction table (notebook_datasets)
            # to support many-to-many relationship with notebooks
            "type": dataset.type,
            "connection_id": dataset.connection_id,
            "created_at": dataset.created_at,
            "files": [],
            "connection_details": None,
            "schema": None,
        }

        # Load files if file-type dataset
        if dataset.type == "file" and dataset.files:
            from server.services.file_operations import DataFrameFileService

            dataset_dict["db_type"] = "duckdb"
            dataset_dict["files"] = [
                {
                    "id": f.id,
                    "file_id": f.id,  # Add for frontend compatibility
                    "name": f.name,
                    "type": f.type,
                    "size": f.size,
                    "uploaded_at": f.uploaded_at,
                    "filename": f.name,  # Add for compatibility
                    "storage_path": f.storage_path,
                    "alias": DataFrameFileService._alias_from_filename(f.name),  # Use SQL-safe alias
                }
                for f in dataset.files
            ]

            # Generate schema using DuckDB with caching
            try:
                schema_data = await DataFrameFileService.get_file_schema_multi(
                    dataset.files,
                    session=session,
                    dataset=dataset,
                    use_cache=True,
                    save_to_cache=True,
                )
                # Return FULL schema object (same format as database connections)
                # Must include: datasource_type, datasource_name, and schema
                dataset_dict["schema"] = schema_data
            except Exception as e:
                logger.error(f"Error generating schema for file dataset {dataset_id}: {str(e)}")
                # Return empty schema in same format as successful response
                dataset_dict["schema"] = {"datasource_type": "file", "datasource_name": "File Database", "schema": {}}

        # Load connection details if connection-type dataset
        if dataset.type == "connection" and dataset.connection_id:
            conn_repo = ConnectionRepository(session)
            connection = await conn_repo.get(dataset.connection_id)
            if connection:
                dataset_dict["connection_details"] = {
                    "id": connection.id,
                    "type": connection.type,
                    "name": connection.name,
                }

                # Include cached schema if available
                if connection.schema_cache:
                    try:
                        dataset_dict["schema"] = json.loads(connection.schema_cache)
                    except:
                        pass

        return dataset_dict

    @staticmethod
    async def delete_dataset(
        session: AsyncSession,
        dataset_id: str,
    ) -> bool:
        """
        Delete a dataset (cascades to files).

        Args:
            session: Database session
            dataset_id: Dataset ID

        Returns:
            True if deleted, False if not found
        """
        dataset = await session.get(Dataset, dataset_id)
        if not dataset:
            return False

        is_file_dataset = dataset.type == "file"

        await session.delete(dataset)
        await session.commit()

        if is_file_dataset:
            try:
                await DatasetStorageService.delete_dataset(dataset_id)
            except Exception as exc:
                logger.warning(
                    "Failed to remove filesystem artifacts for dataset %s: %s",
                    dataset_id,
                    exc,
                )

        logger.info(f"Deleted dataset {dataset_id}")
        return True

    @staticmethod
    async def get_dataset(
        session: AsyncSession,
        dataset_id: str,
    ) -> Dataset | None:
        """
        Get a dataset by ID with files and connection loaded.

        Args:
            session: Database session
            dataset_id: Dataset ID

        Returns:
            Dataset or None if not found
        """
        stmt = (
            select(Dataset)
            .where(Dataset.id == dataset_id)
            .options(joinedload(Dataset.files), joinedload(Dataset.connection))
        )
        result = await session.execute(stmt)
        return result.unique().scalar_one_or_none()

    @staticmethod
    async def associate_dataset_with_notebook(
        session: AsyncSession,
        dataset_id: str,
        notebook_id: str,
    ) -> NotebookDataset:
        """
        Associate a dataset with a notebook.

        Args:
            session: Database session
            dataset_id: Dataset ID
            notebook_id: Notebook ID

        Returns:
            Created NotebookDataset junction record

        Raises:
            ValueError: If dataset doesn't exist or already associated
        """
        # Check if dataset exists
        dataset = await DatasetService.get_dataset(session, dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        # Check if already associated
        existing = await session.execute(
            select(NotebookDataset).where(
                NotebookDataset.dataset_id == dataset_id, NotebookDataset.notebook_id == notebook_id
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Dataset {dataset_id} already associated with notebook {notebook_id}")

        # Create association
        from uuid import uuid4

        notebook_dataset = NotebookDataset(id=str(uuid4()), notebook_id=notebook_id, dataset_id=dataset_id)
        session.add(notebook_dataset)
        await session.commit()
        await session.refresh(notebook_dataset)

        logger.info(f"Associated dataset {dataset_id} with notebook {notebook_id}")
        return notebook_dataset

    @staticmethod
    async def dissociate_dataset_from_notebook(
        session: AsyncSession,
        dataset_id: str,
        notebook_id: str,
    ) -> bool:
        """
        Dissociate a dataset from a notebook.

        Args:
            session: Database session
            dataset_id: Dataset ID
            notebook_id: Notebook ID

        Returns:
            True if dissociated, False if not found
        """
        result = await session.execute(
            select(NotebookDataset).where(
                NotebookDataset.dataset_id == dataset_id, NotebookDataset.notebook_id == notebook_id
            )
        )
        notebook_dataset = result.scalar_one_or_none()

        if not notebook_dataset:
            return False

        await session.delete(notebook_dataset)
        await session.commit()

        logger.info(f"Dissociated dataset {dataset_id} from notebook {notebook_id}")
        return True

    @staticmethod
    async def update_dataset_files(
        session: AsyncSession,
        dataset_id: str,
        files_to_keep: list[str],
        name: str | None = None,
        is_public: bool | None = None,
    ) -> Dataset:
        """
        Update a file dataset by removing files not in the keep list and optionally updating name/visibility.

        Args:
            session: Database session
            dataset_id: Dataset ID
            files_to_keep: List of file IDs to keep
            name: Optional new name for the dataset
            is_public: Optional visibility flag

        Returns:
            Updated Dataset

        Raises:
            ValueError: If dataset not found or is not a file-type dataset
        """
        # Get dataset
        dataset = await DatasetService.get_dataset(session, dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        if dataset.type != "file":
            raise ValueError(f"Dataset {dataset_id} is not a file-type dataset")

        # Update name if provided
        if name is not None:
            dataset.name = name
            logger.info(f"Updated dataset {dataset_id} name to: {name}")

        # Update visibility if provided
        if is_public is not None:
            dataset.is_public = is_public
            logger.info(f"Updated dataset {dataset_id} is_public to: {is_public}")

        # Delete files not in the keep list (normalize to strings for comparison)
        files_to_keep_str = {str(fid) for fid in files_to_keep}
        files_to_delete = [f for f in dataset.files if str(f.id) not in files_to_keep_str]

        for file in files_to_delete:
            if file.storage_path:
                try:
                    await DatasetStorageService.delete_file(dataset_id, file.storage_path)
                except Exception as exc:
                    logger.warning(
                        "Failed to remove file %s from filesystem (dataset=%s): %s",
                        file.id,
                        dataset_id,
                        exc,
                    )
            await session.delete(file)
            logger.info(f"Deleted file {file.id} ({file.name}) from dataset {dataset_id}")

        await session.commit()
        await session.refresh(dataset)

        # Refresh schema with new file list if files were deleted
        if files_to_delete and dataset.files:
            from server.services.file_operations import DataFrameFileService

            await DataFrameFileService.get_file_schema_multi(
                dataset.files,
                session=session,
                dataset=dataset,
                use_cache=False,
                save_to_cache=True,
            )

        logger.info(
            f"Updated dataset {dataset_id}: kept {len(files_to_keep)} files, removed {len(files_to_delete)} files"
        )
        return dataset

    @staticmethod
    async def refresh_dataset_schema(
        session: AsyncSession,
        dataset_id: str,
    ) -> tuple[Dataset, dict[str, Any]]:
        """
        Refresh schema cache for a file dataset.

        Args:
            session: Database session
            dataset_id: Dataset ID

        Returns:
            Tuple of (dataset, schema)

        Raises:
            ValueError: If dataset not found or not a file-type dataset
        """
        from server.services.file_operations import DataFrameFileService

        dataset = await DatasetService.get_dataset(session, dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        if dataset.type != "file":
            raise ValueError(f"Cannot refresh schema for non-file dataset type: {dataset.type}")

        if not dataset.files:
            raise ValueError(f"No files found in dataset {dataset_id}")

        # Force regenerate schema (use_cache=False) and save to cache
        schema = await DataFrameFileService.get_file_schema_multi(
            dataset.files,
            session=session,
            dataset=dataset,
            use_cache=False,
            save_to_cache=True,
        )

        logger.info(f"Successfully refreshed schema for dataset {dataset_id}")
        return dataset, schema
