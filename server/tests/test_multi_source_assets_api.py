from __future__ import annotations

import socket

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.datasets import Dataset
from server.models.knowledge_resources import EvidenceFragment, KnowledgeResource
from server.models.notebooks import Notebook
from server.models.tenant import Tenant
from server.services.multi_source_assets import MultiSourceAssetService
from server.services.source_processing import WebFetchGuard

PDF_BYTES = (
    b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length 86 >>
stream
BT
/F1 24 Tf
72 720 Td
(Byaan PDF source resource test revenue rules) Tj
ET
endstream
endobj
xref
0 6
"""
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000058 00000 n \n"
    b"0000000115 00000 n \n"
    b"0000000241 00000 n \n"
    b"0000000311 00000 n \n"
    b"""
trailer
<< /Size 6 /Root 1 0 R >>
startxref
447
%%EOF
"""
)


@pytest.mark.asyncio
async def test_source_resource_api_exposes_phase_zero_resource_contract(test_client: AsyncClient):
    create_response = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "feishu_doc",
            "name": "Operating Rules",
            "external_id": "docx_123",
            "source_url": "https://example.feishu.cn/docx/docx_123",
            "sync_mode": "manual",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()["data"]
    assert created["resource_type"] == "feishu_doc"
    assert created["name"] == "Operating Rules"
    assert created["status"] == "needs_confirmation"
    assert created["latest_snapshot_id"] is None

    get_response = await test_client.get(f"/api/source-resources/{created['id']}")
    snapshots_response = await test_client.get(f"/api/source-resources/{created['id']}/snapshots")
    processing_response = await test_client.get(f"/api/source-resources/{created['id']}/processing")

    assert get_response.status_code == 200
    assert get_response.json()["data"]["id"] == created["id"]
    assert snapshots_response.status_code == 200
    assert snapshots_response.json()["data"] == {"items": [], "total": 0}
    assert processing_response.status_code == 200
    assert processing_response.json()["data"]["status"] == "needs_confirmation"
    assert processing_response.json()["data"]["latest_snapshot"] is None
    assert processing_response.json()["data"]["knowledge_resource"] is None

    sync_response = await test_client.post(f"/api/source-resources/{created['id']}/sync")

    assert sync_response.status_code == 200
    assert sync_response.json()["data"]["status"] == "needs_confirmation"
    assert "requires production OAuth" in sync_response.json()["data"]["message"]


@pytest.mark.asyncio
async def test_pdf_upload_persists_snapshot_knowledge_and_datasource_projection(
    test_client: AsyncClient,
    test_session: AsyncSession,
):
    response = await test_client.post(
        "/api/source-resources/pdf",
        files={"file": ("rules.pdf", PDF_BYTES, "application/pdf")},
        data={"name": "Revenue Rules PDF"},
    )

    assert response.status_code == 201
    resource = response.json()["data"]
    assert resource["resource_type"] == "pdf"
    assert resource["status"] == "ready"
    assert resource["latest_snapshot_id"]

    snapshots_response = await test_client.get(f"/api/source-resources/{resource['id']}/snapshots")
    processing_response = await test_client.get(f"/api/source-resources/{resource['id']}/processing")
    datasources_response = await test_client.get("/api/datasources")

    snapshots = snapshots_response.json()["data"]["items"]
    assert snapshots_response.status_code == 200
    assert len(snapshots) == 1
    assert snapshots[0]["status"] == "indexed"
    assert snapshots[0]["raw_storage_uri"].startswith("file://")
    assert snapshots[0]["metadata_json"]["page_count"] == 1
    assert "Byaan PDF source resource test" in snapshots[0]["metadata_json"]["summary"]

    processing = processing_response.json()["data"]
    assert processing["status"] == "ready"
    assert processing["latest_snapshot"]["id"] == resource["latest_snapshot_id"]
    assert processing["knowledge_resource"]["provider"] == "native"
    assert processing["knowledge_resource"]["index_status"] == "indexed"

    datasource = next(item for item in datasources_response.json()["data"]["items"] if item["id"] == resource["id"])
    assert datasource["source_type"] == "source_resource"
    assert datasource["type"] == "pdf"
    assert datasource["status"] == "ready"
    assert datasource["latest_snapshot_id"] == resource["latest_snapshot_id"]

    knowledge = await test_session.scalar(
        select(KnowledgeResource).where(KnowledgeResource.resource_id == resource["id"])
    )
    assert knowledge is not None
    evidence = await test_session.scalar(
        select(EvidenceFragment).where(EvidenceFragment.knowledge_resource_id == knowledge.id)
    )
    assert evidence is not None
    assert "Byaan PDF source resource test" in evidence.text


@pytest.mark.asyncio
async def test_web_resource_fetches_public_url_and_can_refresh(
    test_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_public_hostname(hostname: str) -> None:
        assert hostname == "example.com"

    calls: list[str] = []
    original_get = httpx.AsyncClient.get

    async def fake_get(self, url: str):  # noqa: ANN001
        if not url.startswith("http"):
            return await original_get(self, url)
        calls.append(url)
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<html><head><title>Data Agent Note</title></head><body><main><h1>Data Agent</h1><p>Web source resource evidence.</p></main></body></html>",
        )

    monkeypatch.setattr(WebFetchGuard, "_assert_public_hostname", fake_public_hostname)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    response = await test_client.post(
        "/api/source-resources/web",
        json={"name": "Data Agent Web", "source_url": "https://example.com/data-agent"},
    )

    assert response.status_code == 201
    resource = response.json()["data"]
    assert resource["status"] == "ready"
    assert resource["latest_snapshot_id"]

    sync_response = await test_client.post(f"/api/source-resources/{resource['id']}/sync")
    snapshots_response = await test_client.get(f"/api/source-resources/{resource['id']}/snapshots")

    assert sync_response.status_code == 200
    assert sync_response.json()["data"]["status"] == "ready"
    assert sync_response.json()["data"]["snapshot_id"]
    assert calls == ["https://example.com/data-agent", "https://example.com/data-agent"]
    snapshots = snapshots_response.json()["data"]["items"]
    assert len(snapshots) == 2
    assert all(snapshot["status"] == "indexed" for snapshot in snapshots)
    assert snapshots[0]["metadata_json"]["final_url"] == "https://example.com/data-agent"


@pytest.mark.asyncio
async def test_web_fetch_guard_blocks_local_and_private_addresses(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(Exception, match="private or local network"):
        await WebFetchGuard.fetch("http://127.0.0.1/private")

    def fake_private_lookup(hostname: str, port):  # noqa: ANN001
        assert hostname == "internal.example"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 80))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_private_lookup)
    with pytest.raises(Exception, match="private or local network"):
        await WebFetchGuard.fetch("https://internal.example/page")


@pytest.mark.asyncio
async def test_failed_pdf_upload_keeps_failed_snapshot_with_error_reason(test_client: AsyncClient):
    response = await test_client.post(
        "/api/source-resources/pdf",
        files={"file": ("scan.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        data={"name": "Broken PDF"},
    )

    assert response.status_code == 400

    datasources_response = await test_client.get("/api/datasources")
    failed_resource = next(
        item for item in datasources_response.json()["data"]["items"] if item["name"] == "Broken PDF"
    )
    assert failed_resource["status"] == "failed"
    assert failed_resource["latest_snapshot_id"]

    processing_response = await test_client.get(f"/api/source-resources/{failed_resource['id']}/processing")
    latest_snapshot = processing_response.json()["data"]["latest_snapshot"]
    assert latest_snapshot["status"] == "failed"
    assert latest_snapshot["raw_storage_uri"].startswith("file://")
    assert latest_snapshot["error_json"]["message"]


@pytest.mark.asyncio
async def test_source_resource_delete_removes_resource_from_unified_list(test_client: AsyncClient):
    create_response = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "feishu_sheet",
            "name": "Planning Sheet",
            "source_url": "https://example.feishu.cn/sheets/sht_123",
        },
    )
    resource_id = create_response.json()["data"]["id"]

    delete_response = await test_client.delete(f"/api/source-resources/{resource_id}")
    get_response = await test_client.get(f"/api/source-resources/{resource_id}")
    datasources_response = await test_client.get("/api/datasources")

    assert delete_response.status_code == 204
    assert get_response.status_code == 404
    assert all(item["id"] != resource_id for item in datasources_response.json()["data"]["items"])


@pytest.mark.asyncio
async def test_notebook_assets_api_binds_dataset_and_knowledge_resource(
    test_client: AsyncClient,
    test_session: AsyncSession,
):
    notebook_response = await test_client.post(
        "/api/notebooks",
        json={"notebook_name": "Multi-source workspace"},
    )
    assert notebook_response.status_code == 201
    notebook_id = notebook_response.json()["data"]["id"]

    notebook = await test_session.scalar(select(Notebook).where(Notebook.id == notebook_id))
    tenant = await test_session.scalar(select(Tenant).where(Tenant.id == notebook.tenant_id))
    assert notebook is not None
    assert tenant is not None

    dataset = Dataset(
        tenant_id=notebook.tenant_id,
        created_by=tenant.owner_id,
        type="file",
        name="Sales Targets",
    )
    test_session.add(dataset)
    await test_session.commit()
    await test_session.refresh(dataset)

    bundle = await MultiSourceAssetService().create_knowledge_resource_from_snapshot(
        session=test_session,
        resource_type="pdf",
        name="Industry Report",
        raw_storage_uri="file://snapshots/industry-report.pdf",
        content_hash="sha256:industry",
        provider="native",
        tenant_id=notebook.tenant_id,
        owner_id=tenant.owner_id,
    )

    dataset_bind_response = await test_client.post(
        f"/api/notebooks/{notebook_id}/assets",
        json={
            "asset_type": "dataset",
            "asset_id": str(dataset.id),
            "usage_policy_json": {"mode": "query"},
        },
    )
    knowledge_bind_response = await test_client.post(
        f"/api/notebooks/{notebook_id}/assets",
        json={
            "asset_type": "knowledge_resource",
            "asset_id": str(bundle.knowledge_resource.id),
            "usage_policy_json": {"mode": "retrieve"},
        },
    )
    list_response = await test_client.get(f"/api/notebooks/{notebook_id}/assets")

    assert dataset_bind_response.status_code == 201
    assert knowledge_bind_response.status_code == 201
    assert list_response.status_code == 200

    assets = list_response.json()["data"]["items"]
    assert [asset["asset_type"] for asset in assets] == ["dataset", "knowledge_resource"]
    assert assets[0]["asset_id"] == str(dataset.id)
    assert assets[0]["capabilities"] == ["dataset_query"]
    assert assets[1]["asset_id"] == str(bundle.knowledge_resource.id)
    assert assets[1]["capabilities"] == ["knowledge_search", "evidence_read"]
    assert assets[1]["freshness"]["content_hash"] == "sha256:industry"

    delete_response = await test_client.delete(
        f"/api/notebooks/{notebook_id}/assets/knowledge_resource/{bundle.knowledge_resource.id}"
    )
    after_delete_response = await test_client.get(f"/api/notebooks/{notebook_id}/assets")

    assert delete_response.status_code == 204
    assert [asset["asset_type"] for asset in after_delete_response.json()["data"]["items"]] == ["dataset"]
