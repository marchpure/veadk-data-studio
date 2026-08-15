from __future__ import annotations

import pytest
from sqlalchemy import select

from server.auth.tenant_context import set_tenant_id
from server.models.notebooks import Notebook, NotebookAsset
from server.models.source_resources import SourceResource
from server.services.multi_source_assets import MultiSourceAssetService


@pytest.mark.asyncio
async def test_knowledge_resource_can_be_created_and_bound_to_notebook(test_session):
    tenant_id = None
    from uuid import uuid4

    from server.models.tenant import Tenant
    from server.models.user import User

    user_id = uuid4()
    tenant_id = uuid4()
    test_session.add(User(id=user_id, email="asset@test.com", hashed_password="x", is_active=True, is_verified=True))
    await test_session.flush()
    test_session.add(Tenant(id=tenant_id, name="Asset Tenant", slug="asset-tenant", owner_id=user_id, is_personal=True))
    await test_session.flush()
    notebook = Notebook(tenant_id=tenant_id, created_by=user_id, notebook_name="Multi-source workspace")
    test_session.add(notebook)
    await test_session.commit()
    await test_session.refresh(notebook)
    set_tenant_id(tenant_id)

    service = MultiSourceAssetService()

    bundle = await service.create_knowledge_resource_from_snapshot(
        session=test_session,
        resource_type="feishu_doc",
        name="Operating Rules",
        external_id="docx_123",
        source_url="https://example.feishu.cn/docx/docx_123",
        raw_storage_uri="s3://snapshots/docx_123.json",
        external_revision="rev-7",
        content_hash="sha256:abc",
        provider="openviking",
        provider_resource_id="ov://resources/docx_123",
        evidence_fragments=[
            {
                "fragment_type": "block",
                "title_path": ["Revenue Rules", "Active Customer"],
                "text": "Active customers exclude pilots.",
                "locator_json": {"block_id": "blk_1", "url": "https://example.feishu.cn/docx/docx_123#blk_1"},
                "confidence": "high",
                "content_hash": "sha256:frag1",
            }
        ],
        tenant_id=tenant_id,
        owner_id=user_id,
    )
    asset = await service.associate_asset_with_notebook(
        session=test_session,
        notebook_id=notebook.id,
        asset_type="knowledge_resource",
        asset_id=bundle.knowledge_resource.id,
        usage_policy_json={"mode": "retrieve"},
    )
    assets = await service.search_assets(session=test_session, notebook_id=notebook.id)

    resource = await test_session.scalar(select(SourceResource).where(SourceResource.id == bundle.source_resource.id))
    notebook_asset = await test_session.scalar(select(NotebookAsset).where(NotebookAsset.id == asset.id))

    assert resource is not None
    assert resource.resource_type == "feishu_doc"
    assert bundle.snapshot.external_revision == "rev-7"
    assert bundle.knowledge_resource.provider == "openviking"
    assert bundle.evidence_fragments[0].locator_json["block_id"] == "blk_1"
    assert notebook_asset is not None
    assert notebook_asset.asset_type == "knowledge_resource"
    assert assets == [
        {
            "asset_type": "knowledge_resource",
            "asset_id": str(bundle.knowledge_resource.id),
            "name": "Operating Rules",
            "resource_type": "feishu_doc",
            "capabilities": ["knowledge_search", "evidence_read"],
            "status": "ready",
            "freshness": {
                "snapshot_id": str(bundle.snapshot.id),
                "external_revision": "rev-7",
                "content_hash": "sha256:abc",
            },
        }
    ]


@pytest.mark.asyncio
async def test_search_assets_can_return_dataset_and_knowledge_resource_without_notebook_dataset_regression(test_session):
    from uuid import uuid4

    from server.models.datasets import Dataset
    from server.models.notebooks import NotebookDataset
    from server.models.tenant import Tenant
    from server.models.user import User

    user_id = uuid4()
    tenant_id = uuid4()
    test_session.add(
        User(id=user_id, email="mixed-assets@test.com", hashed_password="x", is_active=True, is_verified=True)
    )
    await test_session.flush()
    test_session.add(Tenant(id=tenant_id, name="Mixed Asset Tenant", slug="mixed-assets", owner_id=user_id))
    await test_session.flush()
    notebook = Notebook(tenant_id=tenant_id, created_by=user_id, notebook_name="Mixed asset workspace")
    dataset = Dataset(tenant_id=tenant_id, created_by=user_id, type="file", name="Sales Targets")
    test_session.add_all([notebook, dataset])
    await test_session.commit()
    await test_session.refresh(notebook)
    await test_session.refresh(dataset)
    set_tenant_id(tenant_id)

    service = MultiSourceAssetService()
    bundle = await service.create_knowledge_resource_from_snapshot(
        session=test_session,
        resource_type="pdf",
        name="Industry Report",
        raw_storage_uri="file://snapshots/report.pdf",
        content_hash="sha256:report",
        provider="native",
        tenant_id=tenant_id,
        owner_id=user_id,
    )

    dataset_asset = await service.associate_asset_with_notebook(
        session=test_session,
        notebook_id=notebook.id,
        asset_type="dataset",
        asset_id=dataset.id,
        usage_policy_json={"mode": "query"},
    )
    knowledge_asset = await service.associate_asset_with_notebook(
        session=test_session,
        notebook_id=notebook.id,
        asset_type="knowledge_resource",
        asset_id=bundle.knowledge_resource.id,
        usage_policy_json={"mode": "retrieve"},
    )
    old_style = NotebookDataset(notebook_id=notebook.id, dataset_id=dataset.id)
    test_session.add(old_style)
    await test_session.commit()

    assets = await service.search_assets(session=test_session, notebook_id=notebook.id)

    assert [asset["asset_type"] for asset in assets] == ["dataset", "knowledge_resource"]
    assert assets[0]["asset_id"] == str(dataset.id)
    assert assets[0]["capabilities"] == ["dataset_query"]
    assert assets[1]["asset_id"] == str(bundle.knowledge_resource.id)
    assert await test_session.get(NotebookAsset, dataset_asset.id) is not None
    assert await test_session.get(NotebookAsset, knowledge_asset.id) is not None
    assert await test_session.get(NotebookDataset, old_style.id) is not None


@pytest.mark.asyncio
async def test_notebook_asset_association_rejects_assets_from_another_tenant(test_session):
    from uuid import uuid4

    from server.models.datasets import Dataset
    from server.models.tenant import Tenant
    from server.models.user import User

    user_a_id = uuid4()
    user_b_id = uuid4()
    tenant_a_id = uuid4()
    tenant_b_id = uuid4()
    test_session.add_all(
        [
            User(id=user_a_id, email="tenant-a-assets@test.com", hashed_password="x", is_active=True, is_verified=True),
            User(id=user_b_id, email="tenant-b-assets@test.com", hashed_password="x", is_active=True, is_verified=True),
        ]
    )
    await test_session.flush()
    test_session.add_all(
        [
            Tenant(id=tenant_a_id, name="Tenant A", slug="tenant-a-assets", owner_id=user_a_id),
            Tenant(id=tenant_b_id, name="Tenant B", slug="tenant-b-assets", owner_id=user_b_id),
        ]
    )
    await test_session.flush()
    notebook = Notebook(tenant_id=tenant_a_id, created_by=user_a_id, notebook_name="Tenant A Notebook")
    dataset = Dataset(tenant_id=tenant_b_id, created_by=user_b_id, type="file", name="Tenant B Dataset")
    test_session.add_all([notebook, dataset])
    await test_session.commit()
    await test_session.refresh(notebook)
    await test_session.refresh(dataset)
    set_tenant_id(tenant_a_id)

    service = MultiSourceAssetService()
    bundle = await service.create_knowledge_resource_from_snapshot(
        session=test_session,
        resource_type="pdf",
        name="Tenant B Report",
        raw_storage_uri="file://snapshots/tenant-b-report.pdf",
        content_hash="sha256:tenant-b",
        provider="native",
        tenant_id=tenant_b_id,
        owner_id=user_b_id,
    )

    with pytest.raises(ValueError, match="does not belong to notebook tenant"):
        await service.associate_asset_with_notebook(
            session=test_session,
            notebook_id=notebook.id,
            asset_type="dataset",
            asset_id=dataset.id,
        )

    with pytest.raises(ValueError, match="does not belong to notebook tenant"):
        await service.associate_asset_with_notebook(
            session=test_session,
            notebook_id=notebook.id,
            asset_type="knowledge_resource",
            asset_id=bundle.knowledge_resource.id,
        )
