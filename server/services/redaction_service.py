from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.repositories.datasource_annotations import DatasourceAnnotationRepository
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

REDACTION_MASK = "****"


class RedactionService:
    @staticmethod
    async def get_redacted_columns(datasource_id: str | UUID, session: AsyncSession) -> dict[str, set[str]]:
        """Returns mapping of table_name -> set of redacted column names."""
        repo = DatasourceAnnotationRepository(session)
        annotations = await repo.get_all_by_datasource(datasource_id)

        redacted: dict[str, set[str]] = {}
        for ann in annotations:
            if ann.annotation_type == "column_redaction" and ann.column_name:
                redacted.setdefault(ann.table_name, set()).add(ann.column_name)

        if redacted:
            for table, cols in redacted.items():
                logger.info(f"[COLUMN REDACTION] datasource={datasource_id} table={table} columns={cols}")
        else:
            logger.debug(f"[COLUMN REDACTION] datasource={datasource_id} no column redactions found")

        return redacted

    @staticmethod
    async def get_redacted_tables(datasource_id: str | UUID, session: AsyncSession) -> set[str]:
        """Returns set of table names that are fully redacted."""
        repo = DatasourceAnnotationRepository(session)
        annotations = await repo.get_all_by_datasource(datasource_id)

        tables = {
            ann.table_name
            for ann in annotations
            if ann.annotation_type == "table_redaction" and ann.column_name is None
        }

        if tables:
            logger.info(f"[TABLE REDACTION] datasource={datasource_id} redacted_tables={tables}")
        else:
            logger.debug(f"[TABLE REDACTION] datasource={datasource_id} no table redactions found")

        return tables

    @staticmethod
    def get_all_redacted_column_names(redacted_columns: dict[str, set[str]]) -> set[str]:
        """Flatten all redacted column names across all tables (conservative approach for cross-table queries)."""
        all_names: set[str] = set()
        for cols in redacted_columns.values():
            all_names.update(cols)
        return all_names

    @staticmethod
    def redact_result_rows(
        results: Any,
        redacted_columns: dict[str, set[str]],
        redacted_tables: set[str] | None = None,
        table_name: str | None = None,
    ) -> Any:
        """Replace values with '****' for all redacted columns (or all columns if table is redacted)."""
        if table_name is not None:
            mask_all = table_name in (redacted_tables or set())
        else:
            mask_all = bool(redacted_tables)

        if not mask_all and not redacted_columns:
            logger.debug("[REDACT ROWS] no redactions to apply, returning results unchanged")
            return results
        if not results and not isinstance(results, (int, float)):
            return results

        if mask_all:
            redacted_names = None
            logger.info(f"[REDACT ROWS] masking ALL columns (table-level redaction) table_name={table_name}")
        else:
            redacted_names = RedactionService.get_all_redacted_column_names(redacted_columns)
            if not redacted_names:
                return results
            logger.info(f"[REDACT ROWS] masking columns={redacted_names}")

        if isinstance(results, (int, float)):
            return REDACTION_MASK if mask_all else results

        if isinstance(results, list):
            if mask_all and results and not isinstance(results[0], dict):
                return [REDACTION_MASK for _ in results]
            for row in results:
                if isinstance(row, dict):
                    if mask_all:
                        for key in row:
                            row[key] = REDACTION_MASK
                    else:
                        for col_name in redacted_names:
                            if col_name in row:
                                row[col_name] = REDACTION_MASK
        elif isinstance(results, dict):
            columns = results.get("columns", [])
            rows = results.get("rows", [])
            if columns and rows:
                if mask_all:
                    redacted_indices = list(range(len(columns)))
                else:
                    redacted_indices = [i for i, col in enumerate(columns) if col in redacted_names]
                for row in rows:
                    if isinstance(row, list):
                        for idx in redacted_indices:
                            if idx < len(row):
                                row[idx] = REDACTION_MASK
                    elif isinstance(row, dict):
                        if mask_all:
                            for key in row:
                                row[key] = REDACTION_MASK
                        else:
                            for col_name in redacted_names:
                                if col_name in row:
                                    row[col_name] = REDACTION_MASK

        return results
