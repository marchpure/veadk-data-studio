from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.query_cache import QueryCache
from server.repositories.base import AsyncCRUDRepository


class QueryCacheRepository(AsyncCRUDRepository[QueryCache]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, QueryCache)

    async def _commit_or_rollback(self) -> None:
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

    async def get_valid(self, cache_key: str) -> QueryCache | None:
        """Get cache entry if not expired, delete if expired."""
        result = await self._session.execute(select(QueryCache).where(QueryCache.cache_key == cache_key))
        entry = result.scalar_one_or_none()

        if entry and entry.expires_at <= datetime.now(UTC).replace(tzinfo=None):
            await self._session.delete(entry)
            await self._commit_or_rollback()
            return None

        return entry

    async def get_with_staleness(self, cache_key: str) -> tuple[dict[str, Any] | None, bool]:
        """Get cache entry with staleness indicator for SWR pattern."""
        entry = await self.get_valid(cache_key)
        if not entry:
            return None, False

        age = (datetime.now(UTC).replace(tzinfo=None) - entry.created_at).total_seconds()
        is_stale = age > entry.ttl_seconds

        return entry.result_data, is_stale

    async def set_cache(
        self,
        cache_key: str,
        query_id: str | UUID,
        result_data: dict[str, Any],
        ttl_seconds: int,
        has_filters: bool = False,
    ) -> QueryCache:
        """Atomically set or update cache entry."""
        now = datetime.now(UTC).replace(tzinfo=None)
        expires_at = now + timedelta(seconds=ttl_seconds)
        normalized_query_id = query_id if isinstance(query_id, UUID) else UUID(str(query_id))
        values = {
            "cache_key": cache_key,
            "query_id": normalized_query_id,
            "result_data": result_data,
            "ttl_seconds": ttl_seconds,
            "created_at": now,
            "expires_at": expires_at,
            "has_filters": has_filters,
        }

        bind = self._session.get_bind()
        dialect_name = bind.dialect.name if bind is not None else ""

        if dialect_name in {"postgresql", "sqlite"}:
            insert_builder = pg_insert if dialect_name == "postgresql" else sqlite_insert
            stmt = (
                insert_builder(QueryCache)
                .values(id=uuid4(), **values)
                .on_conflict_do_update(
                    index_elements=["cache_key"],
                    set_={
                        "query_id": normalized_query_id,
                        "result_data": result_data,
                        "ttl_seconds": ttl_seconds,
                        "created_at": now,
                        "expires_at": expires_at,
                        "has_filters": has_filters,
                    },
                )
            )
            await self._session.execute(stmt)
            await self._commit_or_rollback()

            refreshed = await self._session.execute(
                select(QueryCache).where(QueryCache.cache_key == cache_key).execution_options(populate_existing=True)
            )
            entry = refreshed.scalar_one_or_none()
            if entry is None:
                raise RuntimeError(f"Failed to load cache entry after upsert for key '{cache_key}'")
            return entry

        existing = await self.get_valid(cache_key)
        if existing:
            existing.query_id = normalized_query_id
            existing.result_data = result_data
            existing.ttl_seconds = ttl_seconds
            existing.created_at = now
            existing.expires_at = expires_at
            existing.has_filters = has_filters
            await self._commit_or_rollback()
            return existing

        entry = QueryCache(id=uuid4(), **values)
        self._session.add(entry)
        await self._commit_or_rollback()
        return entry

    async def invalidate_by_cache_key(self, cache_key: str) -> bool:
        """Invalidate a single cache entry."""
        result = await self._session.execute(delete(QueryCache).where(QueryCache.cache_key == cache_key))
        await self._commit_or_rollback()
        return result.rowcount > 0

    async def invalidate_by_query_id(self, query_id: str | UUID) -> int:
        """Invalidate all cache entries for a query (all filter variants)."""
        if isinstance(query_id, str):
            query_id = UUID(str(query_id))
        result = await self._session.execute(delete(QueryCache).where(QueryCache.query_id == query_id))
        await self._commit_or_rollback()
        return result.rowcount

    async def cleanup_expired(self, batch_size: int = 500) -> int:
        """Remove expired cache entries."""
        now = datetime.now(UTC).replace(tzinfo=None)
        total_deleted = 0

        while True:
            result = await self._session.execute(delete(QueryCache).where(QueryCache.expires_at <= now))
            await self._commit_or_rollback()
            deleted = result.rowcount
            total_deleted += deleted
            if deleted < batch_size:
                break

        return total_deleted

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        now = datetime.now(UTC).replace(tzinfo=None)

        total_result = await self._session.execute(select(QueryCache.id))
        total = len(total_result.all())

        valid_result = await self._session.execute(select(QueryCache.id).where(QueryCache.expires_at > now))
        valid = len(valid_result.all())

        return {
            "backend": "postgresql",
            "total_entries": total,
            "valid_entries": valid,
            "expired_entries": total - valid,
        }

    async def get_latest_cache_time_for_queries(self, query_ids: list[UUID]) -> datetime | None:
        """Get the most recent cache created_at time for a set of query IDs."""
        if not query_ids:
            return None

        result = await self._session.execute(
            select(func.max(QueryCache.created_at)).where(QueryCache.query_id.in_(query_ids))
        )
        return result.scalar_one_or_none()

    async def get_cache_count_for_queries(self, query_ids: list[UUID]) -> int:
        """Get count of valid cache entries for a set of query IDs."""
        if not query_ids:
            return 0

        now = datetime.now(UTC).replace(tzinfo=None)
        result = await self._session.execute(
            select(func.count(QueryCache.id)).where(
                QueryCache.query_id.in_(query_ids),
                QueryCache.expires_at > now,
            )
        )
        return result.scalar_one() or 0
