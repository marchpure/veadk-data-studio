from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from server.auth.tenant_context import set_tenant_id
from server.db.session import AsyncSessionFactory
from server.repositories.schedules import ScheduleRepository, ScheduleRunRepository
from server.services.schedule_service import ScheduleService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

MAX_CONCURRENT = 3
EXECUTION_TIMEOUT = 300
CHECK_INTERVAL = 60


class ScheduleRunnerService:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running: bool = False
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def start(self):
        if self._running:
            logger.warning("Schedule runner already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Schedule runner started (max {MAX_CONCURRENT} concurrent, {EXECUTION_TIMEOUT}s timeout)")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Schedule runner stopped")

    async def _run_loop(self):
        await asyncio.sleep(30)

        while self._running:
            try:
                await self._check_due_schedules()
            except Exception as e:
                logger.error(f"Schedule check error: {e}", exc_info=True)

            await asyncio.sleep(CHECK_INTERVAL)

    async def _check_due_schedules(self):
        async with AsyncSessionFactory() as session:
            repo = ScheduleRepository(session)
            now = datetime.now(UTC).replace(tzinfo=None)
            due = await repo.get_due_schedules(now)

            for schedule in due:
                asyncio.create_task(self._execute_with_controls(str(schedule.id)))

    async def _execute_with_controls(self, schedule_id: str):
        async with self._semaphore:
            async with AsyncSessionFactory() as session:
                repo = ScheduleRepository(session)

                if not await repo.claim_schedule(schedule_id):
                    logger.debug(f"Schedule {schedule_id} already running, skipping")
                    return

                schedule = await repo.get_with_notebook_and_dashboards(schedule_id)
                if not schedule:
                    return

                set_tenant_id(schedule.tenant_id)

                try:
                    result = await asyncio.wait_for(
                        ScheduleService.execute_schedule(session, schedule),
                        timeout=EXECUTION_TIMEOUT,
                    )
                    logger.info(f"Schedule {schedule.name} completed: {result['status']}")

                except TimeoutError:
                    logger.error(f"Schedule {schedule.name} timed out after {EXECUTION_TIMEOUT}s")
                    await self._record_failure(session, schedule, "timeout", f"Timed out after {EXECUTION_TIMEOUT}s")

                except Exception as e:
                    logger.error(f"Schedule {schedule.name} failed: {e}", exc_info=True)
                    await self._record_failure(session, schedule, "failed", str(e))

                finally:
                    next_run = ScheduleService.calculate_next_run(schedule.cron_expression, schedule.timezone)
                    await repo.release_schedule(str(schedule.id), next_run)

    async def _record_failure(self, session, schedule, status: str, error: str):
        run_repo = ScheduleRunRepository(session)
        await run_repo.create_run(
            {
                "schedule_id": schedule.id,
                "status": status,
                "error_message": error,
            }
        )


schedule_runner_service = ScheduleRunnerService()
