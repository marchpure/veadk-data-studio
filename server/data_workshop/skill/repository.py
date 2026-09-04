from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.data_workshop_skill import (
    DataWorkshopSkill,
    DataWorkshopSkillRevision,
    DataWorkshopSkillSession,
)


class SkillWorkbenchRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID, owner_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.owner_id = owner_id

    def _skill_scope(self):
        return (
            DataWorkshopSkill.tenant_id == self.tenant_id,
            DataWorkshopSkill.owner_id == self.owner_id,
        )

    def _session_scope(self):
        return (
            DataWorkshopSkillSession.tenant_id == self.tenant_id,
            DataWorkshopSkillSession.owner_id == self.owner_id,
        )

    async def list_skills(self, search: str | None = None) -> list[DataWorkshopSkill]:
        query = select(DataWorkshopSkill).where(*self._skill_scope())
        if search:
            query = query.where(DataWorkshopSkill.title.ilike(f"%{search.strip()}%"))
        result = await self.session.scalars(
            query.order_by(DataWorkshopSkill.updated_at.desc(), DataWorkshopSkill.id.desc())
        )
        return list(result)

    async def get_skill(self, skill_id: UUID) -> DataWorkshopSkill | None:
        return await self.session.scalar(
            select(DataWorkshopSkill).where(DataWorkshopSkill.id == skill_id, *self._skill_scope())
        )

    async def get_skill_by_target(self, target_skill: str) -> DataWorkshopSkill | None:
        return await self.session.scalar(
            select(DataWorkshopSkill).where(
                DataWorkshopSkill.target_skill == target_skill,
                *self._skill_scope(),
            )
        )

    async def create_skill(
        self,
        *,
        title: str,
        target_skill: str,
        description: str,
        context_refs: dict[str, Any],
    ) -> DataWorkshopSkill:
        skill = DataWorkshopSkill(
            tenant_id=self.tenant_id,
            owner_id=self.owner_id,
            title=title.strip(),
            target_skill=target_skill,
            description=description.strip(),
            context_refs_json=context_refs,
        )
        self.session.add(skill)
        await self.session.flush()
        return skill

    async def list_sessions(self, skill_id: UUID) -> list[DataWorkshopSkillSession]:
        result = await self.session.scalars(
            select(DataWorkshopSkillSession)
            .where(DataWorkshopSkillSession.skill_id == skill_id, *self._session_scope())
            .order_by(DataWorkshopSkillSession.updated_at.desc(), DataWorkshopSkillSession.id.desc())
        )
        return list(result)

    async def get_session(self, session_id: UUID) -> DataWorkshopSkillSession | None:
        return await self.session.scalar(
            select(DataWorkshopSkillSession).where(
                DataWorkshopSkillSession.id == session_id,
                *self._session_scope(),
            )
        )

    async def create_session(
        self,
        *,
        skill_id: UUID,
        title: str,
        context_refs: dict[str, Any],
    ) -> DataWorkshopSkillSession:
        item = DataWorkshopSkillSession(
            tenant_id=self.tenant_id,
            owner_id=self.owner_id,
            skill_id=skill_id,
            title=title.strip(),
            context_refs_json=context_refs,
            messages_json=[],
            events_json=[],
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def list_revisions(self, skill_id: UUID) -> list[DataWorkshopSkillRevision]:
        result = await self.session.scalars(
            select(DataWorkshopSkillRevision)
            .where(
                DataWorkshopSkillRevision.skill_id == skill_id,
                DataWorkshopSkillRevision.tenant_id == self.tenant_id,
                DataWorkshopSkillRevision.owner_id == self.owner_id,
            )
            .order_by(DataWorkshopSkillRevision.created_at.desc(), DataWorkshopSkillRevision.revision.desc())
        )
        return list(result)

    async def get_revision(self, skill_id: UUID, revision: str) -> DataWorkshopSkillRevision | None:
        return await self.session.scalar(
            select(DataWorkshopSkillRevision).where(
                DataWorkshopSkillRevision.skill_id == skill_id,
                DataWorkshopSkillRevision.revision == revision,
                DataWorkshopSkillRevision.tenant_id == self.tenant_id,
                DataWorkshopSkillRevision.owner_id == self.owner_id,
            )
        )

    async def save_revision(
        self,
        *,
        skill: DataWorkshopSkill,
        work_session: DataWorkshopSkillSession,
        revision: str,
        artifact_metadata: dict[str, Any],
        upstream_artifact_url: str | None,
        validation: dict[str, Any] | None,
    ) -> DataWorkshopSkillRevision:
        item = await self.get_revision(skill.id, revision)
        if item is None:
            item = DataWorkshopSkillRevision(
                tenant_id=self.tenant_id,
                owner_id=self.owner_id,
                skill_id=skill.id,
                session_id=work_session.id,
                revision=revision,
                artifact_metadata_json=artifact_metadata,
                upstream_artifact_url=upstream_artifact_url,
                validation_json=validation,
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
            self.session.add(item)
        else:
            item.artifact_metadata_json = artifact_metadata
            item.upstream_artifact_url = upstream_artifact_url
            item.validation_json = validation
            item.updated_at = datetime.now(UTC).replace(tzinfo=None)
        skill.active_revision = revision
        skill.artifact_metadata_json = artifact_metadata
        skill.updated_at = datetime.now(UTC).replace(tzinfo=None)
        work_session.active_revision = revision
        work_session.artifact_metadata_json = artifact_metadata
        return item
