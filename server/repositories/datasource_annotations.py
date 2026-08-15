from __future__ import annotations

from typing import Literal
from uuid import UUID

from sqlalchemy import and_, delete, select

from server.models.datasource_annotations import DatasourceAnnotation
from server.repositories.base import AsyncCRUDRepository


class DatasourceAnnotationRepository(AsyncCRUDRepository[DatasourceAnnotation]):
    """Repository for datasource annotation operations."""

    def __init__(self, session):
        super().__init__(session, DatasourceAnnotation)

    async def get_all_by_datasource(self, datasource_id: str | UUID) -> list[DatasourceAnnotation]:
        """Get all annotations for a specific datasource."""
        stmt = select(DatasourceAnnotation).where(DatasourceAnnotation.datasource_id == datasource_id)
        # Apply tenant filter
        stmt = self._apply_tenant_filter(stmt)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_table(self, datasource_id: str | UUID, table_name: str) -> list[DatasourceAnnotation]:
        """Get all annotations for a specific table (includes table description and all column annotations)."""
        stmt = select(DatasourceAnnotation).where(
            and_(DatasourceAnnotation.datasource_id == datasource_id, DatasourceAnnotation.table_name == table_name)
        )
        # Apply tenant filter
        stmt = self._apply_tenant_filter(stmt)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_specific_annotation(
        self,
        datasource_id: str | UUID,
        table_name: str,
        annotation_type: Literal["table_description", "column_annotation", "column_redaction", "table_redaction"],
        column_name: str | None = None,
    ) -> DatasourceAnnotation | None:
        """Get a specific annotation by datasource, table, type, and optional column."""
        stmt = select(DatasourceAnnotation).where(
            and_(
                DatasourceAnnotation.datasource_id == datasource_id,
                DatasourceAnnotation.table_name == table_name,
                DatasourceAnnotation.annotation_type == annotation_type,
                DatasourceAnnotation.column_name == column_name,
            )
        )
        # Apply tenant filter
        stmt = self._apply_tenant_filter(stmt)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        datasource_id: str | UUID,
        table_name: str,
        annotation_type: Literal["table_description", "column_annotation", "column_redaction", "table_redaction"],
        content: str,
        column_name: str | None = None,
    ) -> DatasourceAnnotation:
        """Create or update an annotation."""
        existing = await self.get_specific_annotation(datasource_id, table_name, annotation_type, column_name)

        if existing:
            existing.content = content
            await self._session.commit()
            await self._session.refresh(existing)
            return existing
        else:
            # Use base repository's create() which auto-injects tenant_id from context
            new_data = {
                "datasource_id": datasource_id,
                "table_name": table_name,
                "column_name": column_name,
                "annotation_type": annotation_type,
                "content": content,
            }
            return await self.create(new_data)

    async def delete_by_id(self, annotation_id: str | UUID) -> bool:
        """Delete an annotation by ID."""
        stmt = delete(DatasourceAnnotation).where(DatasourceAnnotation.id == annotation_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    async def delete_all_for_datasource(self, datasource_id: str | UUID) -> int:
        """Delete all annotations for a datasource. Returns count of deleted records."""
        stmt = delete(DatasourceAnnotation).where(DatasourceAnnotation.datasource_id == datasource_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount
