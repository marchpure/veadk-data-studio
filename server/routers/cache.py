from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.schemas.cache import (
    CacheRefreshResponse,
    CacheStatsResponse,
    DashboardCacheStatusResponse,
    DashboardRefreshResponse,
    SharedDashboardsRefreshResponse,
)
from server.schemas.standard_response import error_response, success_response
from server.services.dashboard_cache_service import DashboardCacheService
from server.services.query_cache import query_result_cache
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/cache", tags=["cache"])


@router.get("/stats", response_model=CacheStatsResponse)
async def get_cache_stats(
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """Get global cache statistics."""
    stats = await query_result_cache.get_stats(session=session)
    return stats


@router.post("/queries/{query_id}/refresh", response_model=CacheRefreshResponse)
async def refresh_query_cache(
    query_id: str,
    auth: AuthContext = Depends(require_scope(Scope.QUERY_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    """Invalidate all cached results for a query (unfiltered + all filtered variants)."""
    count = await query_result_cache.invalidate_query(query_id, session=session)
    return {
        "success": True,
        "invalidated_count": count,
        "message": f"Invalidated {count} cache entries for query {query_id}",
    }


@router.get("/dashboards/{dashboard_id}/status", response_model=DashboardCacheStatusResponse)
async def get_dashboard_cache_status(
    dashboard_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """Get cache status for a dashboard (last refresh time, staleness)."""
    status = await DashboardCacheService.get_cache_status(session, dashboard_id)
    return status


@router.post("/dashboards/{dashboard_id}/refresh", response_model=DashboardRefreshResponse)
async def refresh_dashboard_cache(
    dashboard_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """Manually refresh all query caches for a dashboard."""
    result = await DashboardCacheService.refresh_dashboard_cache(session, dashboard_id, triggered_by="user")

    if not result.get("success"):
        return error_response(message=result.get("error", "Failed to refresh dashboard cache"))

    return result


@router.post("/dashboards/{dashboard_id}/invalidate")
async def invalidate_dashboard_cache(
    dashboard_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DASHBOARD_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """Invalidate all cached queries for a dashboard without re-executing."""
    result = await DashboardCacheService.invalidate_dashboard_cache(session, dashboard_id)

    if not result.get("success"):
        return error_response(message=result.get("error", "Failed to invalidate dashboard cache"))

    return success_response(data=result, message="Dashboard cache invalidated successfully")


@router.post("/shared-dashboards/refresh", response_model=SharedDashboardsRefreshResponse)
async def refresh_all_shared_dashboards(
    auth: AuthContext = Depends(require_scope(Scope.TENANT_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Manually trigger refresh of all shared dashboards (admin operation)."""
    from server.repositories.folder_dashboard import FolderDashboardRepository

    folder_dashboard_repo = FolderDashboardRepository(session)
    shared_dashboards = await folder_dashboard_repo.get_all_shared()

    seen_dashboards: set[str] = set()
    unique_dashboards = []
    for fd in shared_dashboards:
        dashboard_id = str(fd.dashboard_id)
        if dashboard_id not in seen_dashboards:
            seen_dashboards.add(dashboard_id)
            unique_dashboards.append(fd)

    logger.info(f"Manual refresh triggered for {len(unique_dashboards)} shared dashboards")

    refreshed = 0
    failed = 0
    for fd in unique_dashboards:
        try:
            notebook_id = str(fd.dashboard.notebook_id) if fd.dashboard and fd.dashboard.notebook else None
            result = await DashboardCacheService.refresh_dashboard_cache(
                session,
                str(fd.dashboard_id),
                notebook_id=notebook_id,
                triggered_by="admin",
            )
            if result.get("success"):
                refreshed += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Failed to refresh dashboard {fd.dashboard_id}: {e}")

    return {
        "success": True,
        "message": f"Refreshed {refreshed} of {len(unique_dashboards)} shared dashboards",
        "refreshed": refreshed,
        "failed": failed,
        "total": len(unique_dashboards),
    }
