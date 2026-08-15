from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
from readability import Document
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.knowledge_resources import EvidenceFragment, KnowledgeResource
from server.models.source_resources import SourceResource
from server.models.source_snapshots import SourceSnapshot
from server.services.source_resource_storage import SourceResourceStorageService


class SourceProcessingError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        raw_storage_uri: str | None = None,
        parser_version: str | None = None,
        metadata_json: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_storage_uri = raw_storage_uri
        self.parser_version = parser_version
        self.metadata_json = metadata_json


@dataclass(slots=True, frozen=True)
class SourceProcessingResult:
    snapshot: SourceSnapshot
    knowledge_resource: KnowledgeResource
    evidence_fragments: list[EvidenceFragment]


class WebFetchGuard:
    MAX_BYTES = 5 * 1024 * 1024
    TIMEOUT_SECONDS = 12
    MAX_REDIRECTS = 3
    USER_AGENT = "ByaanSourceIngest/1.0"

    @classmethod
    def _validate_url(cls, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise SourceProcessingError("Only http and https URLs are supported")
        if not parsed.hostname:
            raise SourceProcessingError("URL must include a hostname")
        return parsed.hostname

    @staticmethod
    def _is_forbidden_ip(ip: str) -> bool:
        address = ipaddress.ip_address(ip)
        return (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        )

    @classmethod
    async def _assert_public_hostname(cls, hostname: str) -> None:
        def resolve() -> list[str]:
            return list({item[4][0] for item in socket.getaddrinfo(hostname, None)})

        try:
            addresses = await asyncio.to_thread(resolve)
        except socket.gaierror as exc:
            raise SourceProcessingError(f"Could not resolve URL hostname: {hostname}") from exc

        if not addresses:
            raise SourceProcessingError(f"Could not resolve URL hostname: {hostname}")
        for address in addresses:
            if cls._is_forbidden_ip(address):
                raise SourceProcessingError("URL resolves to a private or local network address")

    @classmethod
    async def fetch(cls, url: str) -> tuple[bytes, str, str | None]:
        current_url = url
        redirects = 0

        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=cls.TIMEOUT_SECONDS,
            headers={"User-Agent": cls.USER_AGENT},
        ) as client:
            while True:
                hostname = cls._validate_url(current_url)
                await cls._assert_public_hostname(hostname)

                try:
                    response = await client.get(current_url)
                except httpx.TimeoutException as exc:
                    raise SourceProcessingError("Timed out fetching URL") from exc
                except httpx.HTTPError as exc:
                    raise SourceProcessingError(f"Failed to fetch URL: {exc}") from exc

                if response.is_redirect:
                    if redirects >= cls.MAX_REDIRECTS:
                        raise SourceProcessingError("Too many redirects while fetching URL")
                    location = response.headers.get("location")
                    if not location:
                        raise SourceProcessingError("Redirect response did not include a Location header")
                    current_url = str(response.url.join(location))
                    redirects += 1
                    continue

                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise SourceProcessingError(f"URL returned HTTP {response.status_code}") from exc

                content = response.content
                if len(content) > cls.MAX_BYTES:
                    raise SourceProcessingError("Fetched page exceeds maximum supported size")

                content_type = response.headers.get("content-type")
                return content, str(response.url), content_type


class SourceProcessingService:
    PDF_PARSER_VERSION = "native-pypdf-1"
    WEB_PARSER_VERSION = "native-readability-1"

    @classmethod
    async def ingest_pdf(
        cls,
        *,
        session: AsyncSession,
        resource: SourceResource,
        filename: str,
        data: bytes,
    ) -> SourceProcessingResult:
        if not data:
            raise SourceProcessingError("PDF file is empty")

        stored = await SourceResourceStorageService.save_bytes(
            tenant_id=resource.tenant_id,
            resource_id=resource.id,
            filename=filename,
            data=data,
        )
        base_metadata = {
            "filename": filename,
            "stored_filename": stored.stored_filename,
            "size": stored.size,
        }
        try:
            text, page_count = await asyncio.to_thread(cls._extract_pdf_text, data)
        except Exception as exc:
            raise SourceProcessingError(
                f"Failed to parse PDF: {exc}",
                raw_storage_uri=stored.raw_storage_uri,
                parser_version=cls.PDF_PARSER_VERSION,
                metadata_json=base_metadata,
            ) from exc
        if not text.strip():
            raise SourceProcessingError(
                "No extractable text was found in the PDF",
                raw_storage_uri=stored.raw_storage_uri,
                parser_version=cls.PDF_PARSER_VERSION,
                metadata_json={**base_metadata, "page_count": page_count},
            )

        metadata = {
            **base_metadata,
            "page_count": page_count,
            "summary": cls._summary(text),
        }
        return await cls._persist_knowledge_result(
            session=session,
            resource=resource,
            raw_storage_uri=stored.raw_storage_uri,
            content_hash=stored.content_hash,
            parser_version=cls.PDF_PARSER_VERSION,
            metadata_json=metadata,
            evidence_fragments=[
                {
                    "fragment_type": "page",
                    "title_path": [resource.name],
                    "text": text[:6000],
                    "locator_json": {"filename": filename, "page_range": [1, page_count]},
                    "confidence": "medium",
                    "content_hash": stored.content_hash,
                }
            ],
        )

    @classmethod
    async def ingest_web(
        cls,
        *,
        session: AsyncSession,
        resource: SourceResource,
    ) -> SourceProcessingResult:
        if not resource.source_url:
            raise SourceProcessingError("Web source requires source_url")

        html_bytes, final_url, content_type = await WebFetchGuard.fetch(resource.source_url)
        stored = await SourceResourceStorageService.save_bytes(
            tenant_id=resource.tenant_id,
            resource_id=resource.id,
            filename="snapshot.html",
            data=html_bytes,
        )
        title, text = await asyncio.to_thread(cls._extract_web_text, html_bytes, final_url)
        if not text.strip():
            raise SourceProcessingError(
                "No extractable text was found in the web page",
                raw_storage_uri=stored.raw_storage_uri,
                parser_version=cls.WEB_PARSER_VERSION,
                metadata_json={
                    "source_url": resource.source_url,
                    "final_url": final_url,
                    "content_type": content_type,
                    "size": stored.size,
                },
            )

        metadata = {
            "title": title,
            "source_url": resource.source_url,
            "final_url": final_url,
            "content_type": content_type,
            "size": stored.size,
            "summary": cls._summary(text),
        }
        return await cls._persist_knowledge_result(
            session=session,
            resource=resource,
            raw_storage_uri=stored.raw_storage_uri,
            content_hash=stored.content_hash,
            parser_version=cls.WEB_PARSER_VERSION,
            metadata_json=metadata,
            external_revision=final_url,
            evidence_fragments=[
                {
                    "fragment_type": "url_section",
                    "title_path": [title or resource.name],
                    "text": text[:6000],
                    "locator_json": {"url": final_url},
                    "confidence": "medium",
                    "content_hash": stored.content_hash,
                }
            ],
        )

    @staticmethod
    def _extract_pdf_text(data: bytes) -> tuple[str, int]:
        reader = PdfReader(BytesIO(data))
        page_texts = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                page_texts.append(f"[Page {index}]\n{text.strip()}")
        return "\n\n".join(page_texts), len(reader.pages)

    @staticmethod
    def _extract_web_text(html_bytes: bytes, url: str) -> tuple[str, str]:
        html = html_bytes.decode("utf-8", errors="replace")
        try:
            document = Document(html)
            title = document.short_title()
            summary_html = document.summary(html_partial=True)
        except Exception:
            soup = BeautifulSoup(html, "lxml")
            title = soup.title.get_text(" ", strip=True) if soup.title else url
            summary_html = html

        soup = BeautifulSoup(summary_html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
        return title or url, text

    @staticmethod
    def _summary(text: str) -> str:
        compact = " ".join(text.split())
        return compact[:500]

    @staticmethod
    async def persist_failed_snapshot(
        *,
        session: AsyncSession,
        resource: SourceResource,
        message: str,
        raw_storage_uri: str = "error://source-processing",
        parser_version: str | None = None,
        metadata_json: dict | None = None,
    ) -> SourceSnapshot:
        digest = hashlib.sha256(f"{resource.id}:{message}".encode()).hexdigest()
        snapshot = SourceSnapshot(
            tenant_id=resource.tenant_id,
            resource_id=resource.id,
            content_hash=f"sha256:{digest}",
            raw_storage_uri=raw_storage_uri,
            parser_version=parser_version,
            metadata_json=metadata_json,
            status="failed",
            error_json={"message": message},
        )
        session.add(snapshot)
        await session.flush()
        resource.status = "failed"
        resource.latest_snapshot_id = snapshot.id
        await session.commit()
        await session.refresh(snapshot)
        await session.refresh(resource)
        return snapshot

    @staticmethod
    async def _persist_knowledge_result(
        *,
        session: AsyncSession,
        resource: SourceResource,
        raw_storage_uri: str,
        content_hash: str,
        parser_version: str,
        metadata_json: dict,
        evidence_fragments: list[dict],
        external_revision: str | None = None,
    ) -> SourceProcessingResult:
        snapshot = SourceSnapshot(
            tenant_id=resource.tenant_id,
            resource_id=resource.id,
            external_revision=external_revision,
            content_hash=content_hash,
            raw_storage_uri=raw_storage_uri,
            parser_version=parser_version,
            metadata_json=metadata_json,
            status="indexed",
        )
        session.add(snapshot)
        await session.flush()

        knowledge_resource = KnowledgeResource(
            tenant_id=resource.tenant_id,
            resource_id=resource.id,
            snapshot_id=snapshot.id,
            provider="native",
            provider_resource_id=str(resource.id),
            parse_status="parsed",
            index_status="indexed",
            completeness_score=1.0,
        )
        session.add(knowledge_resource)
        await session.flush()

        fragments = []
        for fragment in evidence_fragments:
            evidence = EvidenceFragment(
                tenant_id=resource.tenant_id,
                knowledge_resource_id=knowledge_resource.id,
                snapshot_id=snapshot.id,
                fragment_type=fragment["fragment_type"],
                title_path=fragment.get("title_path"),
                text=fragment["text"],
                locator_json=fragment["locator_json"],
                confidence=fragment.get("confidence"),
                content_hash=fragment.get("content_hash"),
            )
            session.add(evidence)
            fragments.append(evidence)

        resource.latest_snapshot_id = snapshot.id
        resource.status = "ready"
        await session.commit()
        await session.refresh(snapshot)
        await session.refresh(knowledge_resource)
        for fragment in fragments:
            await session.refresh(fragment)
        await session.refresh(resource)
        return SourceProcessingResult(
            snapshot=snapshot,
            knowledge_resource=knowledge_resource,
            evidence_fragments=fragments,
        )
