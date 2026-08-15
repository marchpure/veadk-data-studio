from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.knowledge_resources import EvidenceFragment, KnowledgeResource
from server.models.source_resources import SourceResource
from server.models.source_snapshots import SourceSnapshot


NATIVE_PROVIDER_NAMES = {"byaan-native", "native", "local"}
OPENVIKING_PROVIDER_NAMES = {"openviking", "open-viking"}
COMMERCIAL_PROVIDER_MODES = {"commercial", "production", "prod", "enterprise"}


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _native_provider_required_external_reason() -> str | None:
    if _env_truthy("KNOWLEDGE_PROVIDER_ALLOW_NATIVE"):
        return None

    if _env_truthy("KNOWLEDGE_PROVIDER_REQUIRE_EXTERNAL"):
        return "KNOWLEDGE_PROVIDER_REQUIRE_EXTERNAL is enabled"

    provider_mode = os.getenv("KNOWLEDGE_PROVIDER_MODE", "").strip().lower()
    if provider_mode in COMMERCIAL_PROVIDER_MODES:
        return f"KNOWLEDGE_PROVIDER_MODE={provider_mode}"

    app_mode = os.getenv("APP_MODE", "desktop").strip().lower()
    if app_mode == "self-hosted":
        return "APP_MODE=self-hosted"

    return None


def _raise_native_provider_not_allowed(reason: str) -> None:
    raise RuntimeError(
        "NativeKnowledgeProvider is a local/dev fallback that stores evidence text in the control database. "
        f"It is disabled because {reason}. "
        "Configure KNOWLEDGE_PROVIDER=openviking or another external provider for commercial ingestion. "
        "Set KNOWLEDGE_PROVIDER_ALLOW_NATIVE=true only for explicit local diagnostics or migration drills."
    )


def default_knowledge_provider_name() -> str:
    return (os.getenv("KNOWLEDGE_PROVIDER") or "byaan-native").strip().lower()


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


@dataclass(frozen=True)
class KnowledgeEvidence:
    """Provider-neutral evidence payload returned by KnowledgeProvider reads.

    Native local/dev storage still materializes rows in the control database, but
    callers should consume this shape so external providers such as OpenViking can
    return equivalent evidence without exposing ORM rows as their API contract.
    """

    id: UUID
    knowledge_resource_id: UUID
    snapshot_id: UUID
    fragment_type: str
    title_path: list[Any] | None
    text: str
    locator_json: dict[str, Any]
    confidence: str | None
    content_hash: str | None
    created_at: datetime


def evidence_to_provider_payload(evidence: EvidenceFragment) -> KnowledgeEvidence:
    return KnowledgeEvidence(
        id=evidence.id,
        knowledge_resource_id=evidence.knowledge_resource_id,
        snapshot_id=evidence.snapshot_id,
        fragment_type=evidence.fragment_type,
        title_path=evidence.title_path,
        text=evidence.text,
        locator_json=evidence.locator_json,
        confidence=evidence.confidence,
        content_hash=evidence.content_hash,
        created_at=evidence.created_at,
    )


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
    ) -> list[KnowledgeEvidence]:
        ...

    async def read(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        evidence_id: UUID,
    ) -> KnowledgeEvidence | None:
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
                context_uri=f"byaan-native://resources/{resource.id}/snapshots/{snapshot.id}",
                provider_status="indexed",
                last_indexed_at=datetime.utcnow(),
                retrieval_debug_uri=f"byaan-native://debug/resources/{resource.id}/snapshots/{snapshot.id}",
                provider_metadata_json={
                    "storage_role": "local_dev_fallback",
                    "control_plane_text_storage": True,
                },
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
            knowledge_resource.context_uri = f"byaan-native://resources/{resource.id}/snapshots/{snapshot.id}"
            knowledge_resource.provider_status = "indexed"
            knowledge_resource.last_indexed_at = datetime.utcnow()
            knowledge_resource.provider_error = None
            knowledge_resource.retrieval_debug_uri = f"byaan-native://debug/resources/{resource.id}/snapshots/{snapshot.id}"
            knowledge_resource.provider_metadata_json = {
                **(knowledge_resource.provider_metadata_json or {}),
                "storage_role": "local_dev_fallback",
                "control_plane_text_storage": True,
            }

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
    ) -> list[KnowledgeEvidence]:
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
        return [evidence_to_provider_payload(item) for item in result.scalars().all()]

    async def read(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        evidence_id: UUID,
    ) -> KnowledgeEvidence | None:
        evidence = await session.scalar(
            select(EvidenceFragment).where(EvidenceFragment.tenant_id == tenant_id, EvidenceFragment.id == evidence_id)
        )
        return evidence_to_provider_payload(evidence) if evidence is not None else None

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
                        "source_connection_id": str(resource.source_connection_id) if resource.source_connection_id else None,
                        "source_resource_id": str(resource.id),
                        "source_snapshot_id": str(snapshot.id),
                        "resource_id": str(resource.id),
                        "snapshot_id": str(snapshot.id),
                        "external_id": resource.external_id,
                        "source_url": resource.source_url,
                        "external_revision": snapshot.external_revision,
                        "content_hash": snapshot.content_hash,
                        "parser_version": snapshot.parser_version,
                        "captured_at": snapshot.captured_at.isoformat() if snapshot.captured_at else None,
                        "chunk": index,
                        **self._source_locator(resource=resource, snapshot=snapshot, chunk=index),
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

    def _source_locator(
        self,
        *,
        resource: SourceResource,
        snapshot: SourceSnapshot,
        chunk: int,
    ) -> dict[str, Any]:
        metadata = snapshot.metadata_json or {}
        selection = resource.selection_config_json or {}
        selection_metadata = selection.get("metadata") or {}
        locator = metadata.get("locator") if isinstance(metadata.get("locator"), dict) else {}

        if resource.resource_type in {"feishu_doc", "feishu_wiki"}:
            return {
                "document_token": locator.get("document_token") or selection_metadata.get("token") or resource.external_id,
                "wiki_token": locator.get("wiki_token") or selection_metadata.get("node_token"),
                "block_id": locator.get("block_id"),
                "revision": snapshot.external_revision,
                "heading_path": locator.get("heading_path") or metadata.get("title_path") or [resource.name],
                "original_url": resource.source_url,
            }

        if resource.resource_type == "feishu_sheet":
            sheet = self._first((metadata.get("sheets") or []), (selection_metadata.get("sheets") or []))
            spreadsheet = metadata.get("spreadsheet_token") or locator.get("spreadsheet_token") or resource.external_id
            return {
                "spreadsheet_token": spreadsheet,
                "sheet_id": sheet.get("sheet_id") or sheet.get("id"),
                "range": sheet.get("range") or metadata.get("range") or selection.get("range"),
                "cell_range": sheet.get("range") or metadata.get("range") or selection.get("range"),
            }

        if resource.resource_type == "feishu_base":
            table = self._first((metadata.get("tables") or []), (selection_metadata.get("tables") or []))
            return {
                "app_token": metadata.get("app_token") or locator.get("app_token") or resource.external_id,
                "table_id": table.get("table_id"),
                "view_id": table.get("view_id") or selection.get("view_id"),
                "record_id": locator.get("record_id"),
                "field_id": locator.get("field_id"),
            }

        if resource.resource_type.startswith("tos_"):
            return {
                "bucket": metadata.get("bucket"),
                "key": metadata.get("key") or metadata.get("prefix"),
                "version_id": metadata.get("version_id"),
                "etag": metadata.get("etag"),
                "last_modified": metadata.get("last_modified"),
            }

        if resource.resource_type == "pdf":
            return {
                "page": metadata.get("page") or chunk,
                "bbox": metadata.get("bbox"),
                "pdf_parser_deferred": metadata.get("parse_error", {}).get("code") == "parser_no_text",
            }

        if resource.resource_type == "web":
            return {
                "final_url": metadata.get("final_url") or resource.source_url,
                "selector": metadata.get("selector"),
                "text_range": {"chunk": chunk},
            }

        return {}

    def _first(self, *collections: Any) -> dict[str, Any]:
        for collection in collections:
            if not isinstance(collection, list) or not collection:
                continue
            item = collection[0]
            if isinstance(item, dict):
                if "sheet" in item and isinstance(item["sheet"], dict):
                    return {**item["sheet"], "range": item.get("range")}
                if "table" in item and isinstance(item["table"], dict):
                    return item["table"]
                return item
        return {}


class OpenVikingKnowledgeProvider:
    """Provider boundary for commercial context storage.

    Core Byaan connectors should hand this provider normalized SourceSnapshots.
    This skeleton intentionally does not expose OpenViking connectors as Add
    Source entries and fails fast until a real OpenViking client is configured.
    """

    provider = "openviking"

    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = endpoint or os.getenv("OPENVIKING_ENDPOINT")

    def _not_configured(self) -> RuntimeError:
        return RuntimeError(
            "OpenVikingKnowledgeProvider is selected but not configured. "
            "Configure OPENVIKING_ENDPOINT and implement the provider client before using it for ingestion."
        )

    async def ingest(
        self,
        *,
        session: AsyncSession,
        resource: SourceResource,
        snapshot: SourceSnapshot,
        content: str,
    ) -> KnowledgeIngestResult:
        raise self._not_configured()

    async def search(
        self,
        *,
        session: AsyncSession,
        input: KnowledgeSearchInput,
    ) -> list[KnowledgeEvidence]:
        raise self._not_configured()

    async def read(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        evidence_id: UUID,
    ) -> KnowledgeEvidence | None:
        raise self._not_configured()

    async def refresh(
        self,
        *,
        session: AsyncSession,
        resource_id: UUID,
    ) -> KnowledgeIngestResult:
        raise self._not_configured()

    async def delete(
        self,
        *,
        session: AsyncSession,
        resource_id: UUID,
    ) -> None:
        raise self._not_configured()


def get_knowledge_provider(name: str | None = None) -> KnowledgeProvider:
    selected = (name or default_knowledge_provider_name()).strip().lower()
    if selected in OPENVIKING_PROVIDER_NAMES:
        return OpenVikingKnowledgeProvider()

    if selected in NATIVE_PROVIDER_NAMES:
        required_external_reason = _native_provider_required_external_reason()
        if required_external_reason is not None:
            _raise_native_provider_not_allowed(required_external_reason)
        # Native is the local/dev fallback. Commercial deployments should select an
        # external provider through KNOWLEDGE_PROVIDER rather than expanding PG-backed evidence storage.
        return NativeKnowledgeProvider()

    raise ValueError(
        f"Unsupported KNOWLEDGE_PROVIDER '{selected}'. "
        "Supported providers are: byaan-native, openviking."
    )
