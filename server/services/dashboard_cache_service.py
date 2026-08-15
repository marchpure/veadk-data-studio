from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.repositories.queries import QueryRepository
from server.repositories.query_cache import QueryCacheRepository
from server.services.query_cache import query_result_cache
from server.services.query_service import QueryService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

STALE_THRESHOLD_SECONDS = 3600


def _is_cache_stale_from_datetime(last_refreshed: datetime | None) -> bool:
    """Check if cache is considered stale based on last refresh time."""
    if not last_refreshed:
        return True

    try:
        if last_refreshed.tzinfo is None:
            last_refreshed = last_refreshed.replace(tzinfo=UTC)
        age = (datetime.now(UTC) - last_refreshed).total_seconds()
        return age > STALE_THRESHOLD_SECONDS
    except Exception:
        return True


class DashboardCacheService:
    @staticmethod
    async def refresh_dashboard_cache(
        session: AsyncSession,
        dashboard_id: str,
        notebook_id: str | None = None,
        triggered_by: str = "api",
    ) -> dict[str, Any]:
        """
        Refresh cache for all queries in a dashboard.

        If notebook_id is not provided, it will be looked up from the dashboard.
        Only unfiltered queries are refreshed (proactive caching).
        Filtered queries are cached lazily on demand.
        """
        try:
            if not notebook_id:
                from server.repositories.dashboard import DashboardRepository

                dash_repo = DashboardRepository(session)
                dashboard = await dash_repo.get(dashboard_id)
                if not dashboard:
                    return {"success": False, "error": "Dashboard not found"}
                notebook_id = str(dashboard.notebook_id)

            query_repo = QueryRepository(session)
            queries = await query_repo.get_by_notebook_id(notebook_id)

            refreshed_count = 0
            failed_count = 0

            for query_id, query_name in queries:
                try:
                    await query_result_cache.invalidate_query(str(query_id), session=session)
                    result = await QueryService.execute_saved_query(session, str(query_id), filters=None)
                    if result.get("success"):
                        refreshed_count += 1
                        logger.debug(f"Refreshed cache for query {query_id} ({query_name})")
                    else:
                        try:
                            await session.rollback()
                        except Exception:
                            pass
                        failed_count += 1
                        logger.warning(f"Failed to refresh cache for query {query_id}: {result.get('error')}")
                except Exception as e:
                    try:
                        await session.rollback()
                    except Exception:
                        pass
                    failed_count += 1
                    logger.warning(f"Error refreshing cache for query {query_id}: {e}")

            metadata = {
                "last_refreshed_at": datetime.now(UTC).isoformat(),
                "refreshed_by": triggered_by,
                "query_count": refreshed_count,
                "failed_count": failed_count,
            }
            await query_result_cache.set_dashboard_metadata(dashboard_id, metadata)

            return {
                "success": True,
                "refreshed_queries": refreshed_count,
                "failed_queries": failed_count,
                "total_queries": len(queries),
                "refreshed_at": metadata["last_refreshed_at"],
            }

        except Exception as e:
            try:
                await session.rollback()
            except Exception:
                pass
            logger.error(f"Failed to refresh dashboard cache for {dashboard_id}: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    async def get_cache_status(session: AsyncSession, dashboard_id: str) -> dict[str, Any]:
        """Get cache status for a dashboard from the database."""
        try:
            from server.repositories.dashboard import DashboardRepository

            dash_repo = DashboardRepository(session)
            dashboard = await dash_repo.get(dashboard_id)
            if not dashboard:
                return {
                    "dashboard_id": dashboard_id,
                    "last_refreshed_at": None,
                    "refreshed_by": None,
                    "query_count": None,
                    "is_stale": True,
                }

            query_repo = QueryRepository(session)
            queries = await query_repo.get_by_notebook_id(str(dashboard.notebook_id))
            query_ids = [UUID(str(q[0])) for q in queries]

            cache_repo = QueryCacheRepository(session)
            last_refreshed = await cache_repo.get_latest_cache_time_for_queries(query_ids)
            cache_count = await cache_repo.get_cache_count_for_queries(query_ids)

            return {
                "dashboard_id": dashboard_id,
                "last_refreshed_at": last_refreshed.isoformat() if last_refreshed else None,
                "refreshed_by": None,
                "query_count": cache_count,
                "is_stale": _is_cache_stale_from_datetime(last_refreshed),
            }
        except Exception as e:
            try:
                await session.rollback()
            except Exception:
                pass
            logger.error(f"Failed to get cache status for dashboard {dashboard_id}: {e}")
            return {
                "dashboard_id": dashboard_id,
                "last_refreshed_at": None,
                "refreshed_by": None,
                "query_count": None,
                "is_stale": True,
            }

    @staticmethod
    async def invalidate_dashboard_cache(
        session: AsyncSession,
        dashboard_id: str,
        notebook_id: str | None = None,
    ) -> dict[str, Any]:
        """Invalidate all cached queries for a dashboard without re-executing."""
        try:
            if not notebook_id:
                from server.repositories.dashboard import DashboardRepository

                dash_repo = DashboardRepository(session)
                dashboard = await dash_repo.get(dashboard_id)
                if not dashboard:
                    return {"success": False, "error": "Dashboard not found"}
                notebook_id = str(dashboard.notebook_id)

            query_repo = QueryRepository(session)
            queries = await query_repo.get_by_notebook_id(notebook_id)

            invalidated_count = 0
            for query_id, _ in queries:
                count = await query_result_cache.invalidate_query(str(query_id), session=session)
                invalidated_count += count

            return {
                "success": True,
                "invalidated_queries": len(queries),
                "invalidated_cache_entries": invalidated_count,
            }

        except Exception as e:
            try:
                await session.rollback()
            except Exception:
                pass
            logger.error(f"Failed to invalidate dashboard cache for {dashboard_id}: {e}")
            return {"success": False, "error": str(e)}
