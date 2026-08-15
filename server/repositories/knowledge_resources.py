from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from server.models.knowledge_resources import EvidenceFragment, KnowledgeResource
from server.repositories.base import AsyncCRUDRepository


class KnowledgeResourceRepository(AsyncCRUDRepository[KnowledgeResource]):
    def __init__(self, session):
        super().__init__(session, KnowledgeResource)

    async def get_with_source(self, id) -> KnowledgeResource | None:
        query = (
            select(KnowledgeResource)
            .where(KnowledgeResource.id == id)
            .options(
                joinedload(KnowledgeResource.resource),
                joinedload(KnowledgeResource.snapshot),
                joinedload(KnowledgeResource.evidence_fragments),
            )
        )
        query = self._apply_tenant_filter(query)
        result = await self._session.execute(query)
        return result.scalars().unique().one_or_none()


class EvidenceFragmentRepository(AsyncCRUDRepository[EvidenceFragment]):
    def __init__(self, session):
        super().__init__(session, EvidenceFragment)
