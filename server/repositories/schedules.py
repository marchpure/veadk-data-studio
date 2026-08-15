from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from server.models.schedules import Schedule, ScheduleRun
from server.repositories.base import AsyncCRUDRepository


class ScheduleRepository(AsyncCRUDRepository[Schedule]):
    def __init__(self, session):
        super().__init__(session, Schedule)

    async def get_all_for_tenant(self, tenant_id: UUID) -> list[Schedule]:
        query = (
            select(Schedule)
            .where(Schedule.tenant_id == tenant_id)
            .options(selectinload(Schedule.notebook))
            .order_by(Schedule.created_at.desc())
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_for_notebook(self, notebook_id: str) -> list[Schedule]:
        query = (
            select(Schedule)
            .where(Schedule.notebook_id == notebook_id)
            .options(selectinload(Schedule.notebook))
            .order_by(Schedule.created_at.desc())
        )
        query = self._apply_tenant_filter(query)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_with_notebook(self, schedule_id: str) -> Schedule | None:
        query = select(Schedule).where(Schedule.id == schedule_id).options(selectinload(Schedule.notebook))
        query = self._apply_tenant_filter(query)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_with_notebook_and_dashboards(self, schedule_id: str) -> Schedule | None:
        from server.models.notebooks import Notebook

        query = (
            select(Schedule)
            .where(Schedule.id == schedule_id)
            .options(selectinload(Schedule.notebook).selectinload(Notebook.dashboards))
        )
        query = self._apply_tenant_filter(query)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_due_schedules(self, now: datetime) -> list[Schedule]:
        query = (
            select(Schedule)
            .where(
                Schedule.is_enabled.is_(True),
                Schedule.is_running.is_(False),
                Schedule.next_run_at <= now,
            )
            .options(selectinload(Schedule.notebook))
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def claim_schedule(self, schedule_id: str) -> bool:
        result = await self._session.execute(
            update(Schedule).where(Schedule.id == schedule_id, Schedule.is_running.is_(False)).values(is_running=True)
        )
        await self._session.commit()
        return result.rowcount > 0

    async def release_schedule(self, schedule_id: str, next_run_at: datetime) -> None:
        await self._session.execute(
            update(Schedule).where(Schedule.id == schedule_id).values(is_running=False, next_run_at=next_run_at)
        )
        await self._session.commit()


class ScheduleRunRepository(AsyncCRUDRepository[ScheduleRun]):
    def __init__(self, session):
        super().__init__(session, ScheduleRun)

    async def get_recent_runs(self, schedule_id: str, limit: int = 20) -> list[ScheduleRun]:
        query = (
            select(ScheduleRun)
            .where(ScheduleRun.schedule_id == schedule_id)
            .order_by(ScheduleRun.started_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create_run(self, data: dict[str, Any]) -> ScheduleRun:
        run = ScheduleRun(**data)
        self._session.add(run)
        await self._session.commit()
        await self._session.refresh(run)
        return run
