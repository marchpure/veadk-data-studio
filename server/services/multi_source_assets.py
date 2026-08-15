from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from server.auth.tenant_context import get_tenant_id
from server.models.datasets import Dataset
from server.models.knowledge_resources import EvidenceFragment, KnowledgeResource
from server.models.notebooks import Notebook, NotebookAsset
from server.models.source_resources import SourceResource
from server.models.source_snapshots import SourceSnapshot


@dataclass(frozen=True)
class KnowledgeResourceBundle:
    source_resource: SourceResource
    snapshot: SourceSnapshot
    knowledge_resource: KnowledgeResource
    evidence_fragments: list[EvidenceFragment]


class MultiSourceAssetService:
    async def create_knowledge_resource_from_snapshot(
        self,
        *,
        session: AsyncSession,
        resource_type: str,
        name: str,
        raw_storage_uri: str,
        content_hash: str,
        provider: str,
        external_id: str | None = None,
        source_url: str | None = None,
        external_revision: str | None = None,
        provider_resource_id: str | None = None,
        evidence_fragments: list[dict[str, Any]] | None = None,
        tenant_id: UUID | None = None,
        owner_id: UUID | None = None,
        parser_version: str | None = None,
        metadata_json: dict[str, Any] | None = None,
        completeness_score: float | None = None,
    ) -> KnowledgeResourceBundle:
        effective_tenant_id = tenant_id or get_tenant_id()
        if effective_tenant_id is None:
            raise ValueError("tenant_id is required to create a source resource")

        source_resource = SourceResource(
            tenant_id=effective_tenant_id,
            resource_type=resource_type,
            name=name,
            external_id=external_id,
            source_url=source_url,
            owner_id=owner_id,
            status="understanding",
        )
        session.add(source_resource)
        await session.flush()

        snapshot = SourceSnapshot(
            tenant_id=effective_tenant_id,
            resource_id=source_resource.id,
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
            tenant_id=effective_tenant_id,
            resource_id=source_resource.id,
            snapshot_id=snapshot.id,
            provider=provider,
            provider_resource_id=provider_resource_id,
            parse_status="parsed",
            index_status="indexed",
            completeness_score=completeness_score,
        )
        session.add(knowledge_resource)
        await session.flush()

        fragments: list[EvidenceFragment] = []
        for fragment in evidence_fragments or []:
            evidence = EvidenceFragment(
                tenant_id=effective_tenant_id,
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

        source_resource.latest_snapshot_id = snapshot.id
        source_resource.status = "ready"
        await session.commit()

        await session.refresh(source_resource)
        await session.refresh(snapshot)
        await session.refresh(knowledge_resource)
        for fragment in fragments:
            await session.refresh(fragment)

        return KnowledgeResourceBundle(
            source_resource=source_resource,
            snapshot=snapshot,
            knowledge_resource=knowledge_resource,
            evidence_fragments=fragments,
        )

    async def associate_asset_with_notebook(
        self,
        *,
        session: AsyncSession,
        notebook_id: str | UUID,
        asset_type: str,
        asset_id: str | UUID,
        usage_policy_json: dict[str, Any] | None = None,
        added_by: UUID | None = None,
    ) -> NotebookAsset:
        notebook = await session.get(Notebook, notebook_id)
        if notebook is None:
            raise ValueError(f"Notebook {notebook_id} not found")

        await self._assert_asset_belongs_to_notebook_tenant(
            session=session,
            asset_type=asset_type,
            asset_id=asset_id,
            notebook=notebook,
        )

        existing = await session.scalar(
            select(NotebookAsset).where(
                NotebookAsset.notebook_id == notebook_id,
                NotebookAsset.asset_type == asset_type,
                NotebookAsset.asset_id == asset_id,
            )
        )
        if existing is not None:
            raise ValueError(f"{asset_type} {asset_id} already associated with notebook {notebook_id}")

        asset = NotebookAsset(
            notebook_id=notebook_id,
            asset_type=asset_type,
            asset_id=asset_id,
            added_by=added_by,
            usage_policy_json=usage_policy_json,
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        return asset

    async def search_assets(self, *, session: AsyncSession, notebook_id: str | UUID) -> list[dict[str, Any]]:
        query = (
            select(NotebookAsset)
            .where(NotebookAsset.notebook_id == notebook_id)
            .options(joinedload(NotebookAsset.notebook))
            .order_by(NotebookAsset.added_at.asc())
        )
        result = await session.execute(query)
        assets = result.scalars().all()

        response: list[dict[str, Any]] = []
        for asset in assets:
            if asset.asset_type == "knowledge_resource":
                response.append(await self._describe_knowledge_asset(session=session, asset=asset))
            elif asset.asset_type == "dataset":
                response.append(await self._describe_dataset_asset(session=session, asset=asset))
            else:
                response.append(
                    {
                        "asset_type": asset.asset_type,
                        "asset_id": str(asset.asset_id),
                        "capabilities": ["semantic_query"],
                        "status": "ready",
                    }
                )
        return response

    async def _assert_asset_belongs_to_notebook_tenant(
        self,
        *,
        session: AsyncSession,
        asset_type: str,
        asset_id: str | UUID,
        notebook: Notebook,
    ) -> None:
        if asset_type == "knowledge_resource":
            knowledge_resource = await session.get(KnowledgeResource, asset_id)
            if knowledge_resource is None:
                raise ValueError(f"Knowledge resource {asset_id} not found")
            if knowledge_resource.tenant_id != notebook.tenant_id:
                raise ValueError(f"Knowledge resource {asset_id} does not belong to notebook tenant")
            return
        if asset_type == "dataset":
            dataset = await session.get(Dataset, asset_id)
            if dataset is None:
                raise ValueError(f"Dataset {asset_id} not found")
            if dataset.tenant_id != notebook.tenant_id:
                raise ValueError(f"Dataset {asset_id} does not belong to notebook tenant")
            return
        if asset_type == "semantic_model":
            return
        raise ValueError(f"Unsupported notebook asset type: {asset_type}")

    async def _describe_knowledge_asset(self, *, session: AsyncSession, asset: NotebookAsset) -> dict[str, Any]:
        query = (
            select(KnowledgeResource)
            .where(KnowledgeResource.id == asset.asset_id)
            .options(joinedload(KnowledgeResource.resource), joinedload(KnowledgeResource.snapshot))
        )
        result = await session.execute(query)
        knowledge_resource = result.scalars().unique().one()
        source_resource = knowledge_resource.resource
        snapshot = knowledge_resource.snapshot
        return {
            "asset_type": "knowledge_resource",
            "asset_id": str(knowledge_resource.id),
            "name": source_resource.name,
            "resource_type": source_resource.resource_type,
            "capabilities": ["knowledge_search", "evidence_read"],
            "status": source_resource.status,
            "freshness": {
                "snapshot_id": str(snapshot.id),
                "external_revision": snapshot.external_revision,
                "content_hash": snapshot.content_hash,
            },
        }

    async def _describe_dataset_asset(self, *, session: AsyncSession, asset: NotebookAsset) -> dict[str, Any]:
        dataset = await session.get(Dataset, asset.asset_id)
        if dataset is None:
            raise ValueError(f"Dataset {asset.asset_id} not found")
        return {
            "asset_type": "dataset",
            "asset_id": str(dataset.id),
            "name": dataset.name,
            "resource_type": dataset.type,
            "capabilities": ["dataset_query"],
            "status": "ready",
            "freshness": None,
        }
