from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from server.models.knowledge_resources import EvidenceFragment
from server.models.source_snapshots import SourceSnapshot


@dataclass(frozen=True)
class KnowledgeIngestResult:
    provider: str
    provider_resource_id: str | None
    parse_status: str = "parsed"
    index_status: str = "indexed"
    completeness_score: float | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class KnowledgeSearchInput:
    query: str
    resource_ids: list[str] | None = None
    filters: dict[str, Any] | None = None
    limit: int = 10


@dataclass(frozen=True)
class EvidenceHit:
    evidence_id: str
    score: float
    text: str
    locator: dict[str, Any]


class KnowledgeProvider(Protocol):
    async def ingest(self, snapshot: SourceSnapshot) -> KnowledgeIngestResult: ...

    async def search(self, input: KnowledgeSearchInput) -> list[EvidenceHit]: ...

    async def read(self, evidence_id: str) -> EvidenceFragment: ...

    async def refresh(self, resource_id: str) -> KnowledgeIngestResult: ...

    async def delete(self, resource_id: str) -> None: ...
