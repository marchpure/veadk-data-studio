from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from server.models.connections import Connection
from server.models.datasets import Dataset
from server.models.notebooks import NotebookDataset
from server.repositories.base import AsyncCRUDRepository


class DatasetRepository(AsyncCRUDRepository[Dataset]):
    def __init__(self, session):
        super().__init__(session, Dataset)

    async def get_by_notebook(self, notebook_id: str) -> list[Dataset]:
        """Get datasets for a notebook (tenant-filtered)."""
        stmt = (
            select(Dataset)
            .join(NotebookDataset, NotebookDataset.dataset_id == Dataset.id)
            .where(NotebookDataset.notebook_id == notebook_id)
            .options(joinedload(Dataset.files))
        )
        stmt = self._apply_tenant_filter(stmt)
        result = await self._session.execute(stmt)
        return list(result.scalars().unique().all())

    async def search_by_name(self, query: str) -> list[Dataset]:
        """Search datasets by name, description, connection name, and schema_cache (case-insensitive, tenant-filtered)."""
        search_pattern = f"%{query.lower()}%"
        stmt = (
            select(Dataset)
            .outerjoin(Connection, Dataset.connection_id == Connection.id)
            .where(
                or_(
                    Dataset.name.ilike(search_pattern),
                    Dataset.description.ilike(search_pattern),
                    Dataset.schema_cache.ilike(search_pattern),
                    Connection.name.ilike(search_pattern),
                    Connection.description.ilike(search_pattern),
                    Connection.schema_cache.ilike(search_pattern),
                )
            )
            .options(joinedload(Dataset.files), joinedload(Dataset.connection))
        )
        stmt = self._apply_tenant_filter(stmt)
        result = await self._session.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_all_for_tenant(self) -> list[Dataset]:
        """Get all datasets for the current tenant."""
        stmt = select(Dataset).options(joinedload(Dataset.files), joinedload(Dataset.connection))
        stmt = self._apply_tenant_filter(stmt)
        result = await self._session.execute(stmt)
        return list(result.scalars().unique().all())
