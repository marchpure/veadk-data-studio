from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.knowledge_resources import EvidenceFragment, KnowledgeResource
from server.models.source_resources import SourceResource
from server.models.source_snapshots import SourceSnapshot


def stable_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class KnowledgeIngestResult:
    knowledge_resource_id: UUID
    evidence_ids: list[UUID]
    parse_status: str
    index_status: str
    completeness_score: float


@dataclass(frozen=True)
class KnowledgeSearchInput:
    tenant_id: UUID
    query: str
    resource_ids: tuple[UUID, ...] = ()
    limit: int = 10


class KnowledgeProvider(Protocol):
    provider: str

    async def ingest(
        self,
        *,
        session: AsyncSession,
        resource: SourceResource,
        snapshot: SourceSnapshot,
        content: str,
    ) -> KnowledgeIngestResult:
        ...

    async def search(
        self,
        *,
        session: AsyncSession,
        input: KnowledgeSearchInput,
    ) -> list[EvidenceFragment]:
        ...

    async def read(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        evidence_id: UUID,
    ) -> EvidenceFragment | None:
        ...

    async def refresh(
        self,
        *,
        session: AsyncSession,
        resource_id: UUID,
    ) -> KnowledgeIngestResult:
        ...

    async def delete(
        self,
        *,
        session: AsyncSession,
        resource_id: UUID,
    ) -> None:
        ...


class NativeKnowledgeProvider:
    """Minimal local provider.

    It indexes caller-supplied text into evidence fragments. It deliberately does not
    fetch PDFs, Feishu docs, or web pages by itself; external connectors should
    capture content and pass a SourceSnapshot into this provider.
    """

    provider = "byaan-native"
    parser_version = "byaan-native-text-v1"

    async def ingest(
        self,
        *,
        session: AsyncSession,
        resource: SourceResource,
        snapshot: SourceSnapshot,
        content: str,
    ) -> KnowledgeIngestResult:
        existing = await session.scalar(
            select(KnowledgeResource).where(
                KnowledgeResource.tenant_id == resource.tenant_id,
                KnowledgeResource.resource_id == resource.id,
                KnowledgeResource.snapshot_id == snapshot.id,
                KnowledgeResource.provider == self.provider,
            )
        )
        if existing is None:
            knowledge_resource = KnowledgeResource(
                tenant_id=resource.tenant_id,
                resource_id=resource.id,
                snapshot_id=snapshot.id,
                provider=self.provider,
                provider_resource_id=f"{self.provider}:{resource.id}:{snapshot.id}",
                parse_status="parsed",
                index_status="indexed",
                completeness_score=1.0 if content.strip() else 0.0,
            )
            session.add(knowledge_resource)
            await session.flush()
        else:
            knowledge_resource = existing
            knowledge_resource.parse_status = "parsed"
            knowledge_resource.index_status = "indexed"
            knowledge_resource.completeness_score = 1.0 if content.strip() else 0.0

        fragments = self._fragment_content(resource=resource, snapshot=snapshot, content=content)
        evidence_ids: list[UUID] = []
        for fragment in fragments:
            evidence = EvidenceFragment(
                tenant_id=resource.tenant_id,
                knowledge_resource_id=knowledge_resource.id,
                snapshot_id=snapshot.id,
                fragment_type=fragment["fragment_type"],
                title_path=fragment["title_path"],
                text=fragment["text"],
                locator_json=fragment["locator_json"],
                confidence=fragment["confidence"],
                content_hash=stable_hash(fragment["text"]),
            )
            session.add(evidence)
            await session.flush()
            evidence_ids.append(evidence.id)

        await session.flush()
        return KnowledgeIngestResult(
            knowledge_resource_id=knowledge_resource.id,
            evidence_ids=evidence_ids,
            parse_status=knowledge_resource.parse_status,
            index_status=knowledge_resource.index_status,
            completeness_score=knowledge_resource.completeness_score or 0.0,
        )

    async def search(
        self,
        *,
        session: AsyncSession,
        input: KnowledgeSearchInput,
    ) -> list[EvidenceFragment]:
        query = input.query.strip()
        stmt = (
            select(EvidenceFragment)
            .join(KnowledgeResource, KnowledgeResource.id == EvidenceFragment.knowledge_resource_id)
            .where(EvidenceFragment.tenant_id == input.tenant_id)
            .order_by(EvidenceFragment.created_at.desc())
            .limit(input.limit)
        )
        if input.resource_ids:
            stmt = stmt.where(KnowledgeResource.resource_id.in_(input.resource_ids))
        if query:
            terms = [term for term in re.split(r"\s+", query) if term]
            if terms:
                stmt = stmt.where(or_(*[EvidenceFragment.text.ilike(f"%{term}%") for term in terms]))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def read(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        evidence_id: UUID,
    ) -> EvidenceFragment | None:
        return await session.scalar(
            select(EvidenceFragment).where(EvidenceFragment.tenant_id == tenant_id, EvidenceFragment.id == evidence_id)
        )

    async def refresh(
        self,
        *,
        session: AsyncSession,
        resource_id: UUID,
    ) -> KnowledgeIngestResult:
        raise NotImplementedError("NativeKnowledgeProvider refresh requires connector-supplied content")

    async def delete(
        self,
        *,
        session: AsyncSession,
        resource_id: UUID,
    ) -> None:
        resources = await session.execute(
            select(KnowledgeResource).where(KnowledgeResource.resource_id == resource_id)
        )
        for resource in resources.scalars().all():
            await session.delete(resource)
        await session.flush()

    def _fragment_content(
        self,
        *,
        resource: SourceResource,
        snapshot: SourceSnapshot,
        content: str,
    ) -> list[dict[str, Any]]:
        normalized = content.strip()
        if not normalized:
            return []

        chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n+", normalized) if chunk.strip()]
        if not chunks:
            chunks = [normalized]

        fragment_type = self._fragment_type_for(resource.resource_type)
        fragments: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks[:100], start=1):
            fragments.append(
                {
                    "fragment_type": fragment_type,
                    "title_path": [resource.name],
                    "text": chunk[:8000],
                    "locator_json": {
                        "kind": resource.resource_type,
                        "resource_id": str(resource.id),
                        "snapshot_id": str(snapshot.id),
                        "chunk": index,
                        "source_url": resource.source_url,
                    },
                    "confidence": "source",
                }
            )
        return fragments

    def _fragment_type_for(self, resource_type: str) -> str:
        if resource_type == "pdf":
            return "page"
        if resource_type == "web":
            return "url_section"
        if resource_type in {"feishu_doc", "feishu_wiki"}:
            return "block"
        if resource_type == "feishu_sheet":
            return "sheet_range"
        if resource_type == "extracted_table":
            return "table_region"
        return "raw_text"


def get_knowledge_provider(name: str | None = None) -> KnowledgeProvider:
    # Single native provider for this slice; external OpenViking/Feishu/PDF/Web
    # providers can register behind this factory later without changing API.
    return NativeKnowledgeProvider()
