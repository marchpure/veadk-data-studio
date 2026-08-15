from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from server.models.datasets import Dataset
from server.models.queries import Query
from server.repositories.base import AsyncCRUDRepository


class QueryRepository(AsyncCRUDRepository[Query]):
    def __init__(self, session):
        super().__init__(session, Query)

    async def get_with_relations(self, query_id: str) -> Query | None:
        """Get query with dataset and its related connection/files."""
        result = await self._session.execute(
            select(Query)
            .options(
                selectinload(Query.dataset).selectinload(Dataset.connection),  # For connection datasets
                selectinload(Query.dataset).selectinload(Dataset.files),  # For file datasets
                selectinload(Query.notebook),
            )
            .where(Query.id == query_id)
        )
        return result.scalar_one_or_none()

    async def get_all_with_type(self, created_by: str | None = None) -> list[tuple[str, str, str, str | None]]:
        """Get all queries with dataset type info. Returns (id, name, dataset_type, skill_name)."""
        stmt = select(Query.id, Query.name, Dataset.type, Dataset.skill_name).join(
            Dataset, Query.dataset_id == Dataset.id
        )
        if created_by:
            stmt = stmt.where(Query.created_by == created_by)
        result = await self._session.execute(stmt)
        return list(result.all())

    async def get_all_id_and_name(self, created_by: str | None = None) -> list[tuple[str, str]]:
        stmt = select(Query.id, Query.name)
        if created_by:
            stmt = stmt.where(Query.created_by == created_by)
        result = await self._session.execute(stmt)
        return list(result.all())

    async def get_by_notebook_id(self, notebook_id: str) -> list[tuple[str, str]]:
        """Get all queries for a specific notebook. Returns list of (id, name) tuples."""
        result = await self._session.execute(
            select(Query.id, Query.name).where(Query.notebook_id == notebook_id).order_by(Query.created_at.desc())
        )
        return list(result.all())

    async def delete_by_id(self, query_id: str) -> bool:
        """Delete a query by its ID. Returns True if deleted, False if not found."""
        query = await self.get(query_id)
        if not query:
            return False
        await self.delete(query_id)
        return True

    async def delete_all(self) -> int:
        """Delete all queries. Returns the number of deleted queries."""
        result = await self._session.execute(delete(Query))
        await self._session.commit()
        return result.rowcount
