from __future__ import annotations

import asyncio
import os

from server.db.session import AsyncSessionFactory
from server.repositories.folder_dashboard import FolderDashboardRepository
from server.repositories.query_cache import QueryCacheRepository
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

REFRESH_INTERVAL_SECONDS = int(os.getenv("DASHBOARD_REFRESH_INTERVAL", 3600))


class DashboardRefreshService:
    """Background service for scheduled dashboard cache refresh (CreditSyncService pattern)."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running: bool = False

    async def start(self) -> None:
        if self._running:
            logger.warning("Dashboard refresh service already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._refresh_loop())
        logger.info(f"Dashboard refresh service started (interval: {REFRESH_INTERVAL_SECONDS}s)")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Dashboard refresh service stopped")

    async def _refresh_loop(self) -> None:
        await asyncio.sleep(60)

        while self._running:
            try:
                await self._refresh_shared_dashboards()
                await self._cleanup_expired_cache()
            except Exception as e:
                logger.error(f"Dashboard refresh error: {e}", exc_info=True)

            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)

    async def _refresh_shared_dashboards(self) -> None:
        from server.services.dashboard_cache_service import DashboardCacheService

        # Materialize scalar targets first so scheduler does not depend on ORM objects
        # after a rollback (which can expire attributes and cause MissingGreenlet).
        async with AsyncSessionFactory() as session:
            repo = FolderDashboardRepository(session)
            shared = await repo.get_all_shared()

            targets: list[tuple[str, str | None]] = []
            seen: set[str] = set()
            for fd in shared:
                dashboard_id = str(fd.dashboard_id)
                if dashboard_id in seen:
                    continue
                seen.add(dashboard_id)

                notebook_id: str | None = None
                dashboard = fd.dashboard
                if dashboard is not None:
                    if getattr(dashboard, "notebook_id", None):
                        notebook_id = str(dashboard.notebook_id)
                    elif getattr(dashboard, "notebook", None) and getattr(dashboard.notebook, "id", None):
                        notebook_id = str(dashboard.notebook.id)

                targets.append((dashboard_id, notebook_id))

        refreshed = 0
        failed = 0

        # Isolate each refresh in its own session so one failed transaction cannot poison
        # subsequent dashboard refreshes.
        for dashboard_id, notebook_id in targets:
            try:
                async with AsyncSessionFactory() as refresh_session:
                    result = await DashboardCacheService.refresh_dashboard_cache(
                        refresh_session, dashboard_id, notebook_id=notebook_id, triggered_by="scheduler"
                    )
                    if result.get("success"):
                        refreshed += 1
                    else:
                        failed += 1
            except Exception as e:
                failed += 1
                logger.warning(f"Failed to refresh dashboard {dashboard_id}: {e}")

        if targets:
            logger.info(f"Scheduled refresh: {refreshed} succeeded, {failed} failed out of {len(targets)} dashboards")

    async def _cleanup_expired_cache(self) -> None:
        async with AsyncSessionFactory() as session:
            repo = QueryCacheRepository(session)
            count = await repo.cleanup_expired()
            if count > 0:
                logger.info(f"Cleaned up {count} expired cache entries")


dashboard_refresh_service = DashboardRefreshService()
