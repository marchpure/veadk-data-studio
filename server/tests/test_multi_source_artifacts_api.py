from __future__ import annotations

import io
import json
import zipfile
from uuid import uuid4

import pytest
from sqlalchemy import select

from server.models.analysis_artifacts import AnalysisArtifact
from server.models.dashboard import Dashboard
from server.models.datasets import Dataset
from server.models.files import File
from server.models.knowledge_resources import EvidenceFragment, KnowledgeResource
from server.models.notebook_assets import NotebookAsset
from server.models.notebooks import Notebook
from server.models.semantic_models import SemanticModel
from server.models.source_resources import SourceResource
from server.models.source_snapshots import SourceSnapshot
from server.models.tenant import Tenant
from server.services.knowledge_provider import (
    KnowledgeEvidence,
    KnowledgeSearchInput,
    NativeKnowledgeProvider,
    OpenVikingKnowledgeProvider,
    get_knowledge_provider,
)
from server.services.source_resources import SourceResourceService

pytestmark = __import__("pytest").mark.asyncio


def _assert_product_processing_copy(payload):
    text = " ".join([payload.get("message") or "", *payload.get("next_actions", [])]).lower()
    assert "connector-supplied" not in text
    assert "post content" not in text
    assert "api will not fake" not in text


async def _tenant(test_session):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    return tenant


async def _create_notebook(test_client):
    response = await test_client.post(
        "/api/notebooks",
        json={"notebook_name": "Multi-source analysis", "description": "VKS spec test notebook"},
    )
    assert response.status_code == 201
    return response.json()["data"]


async def test_source_resource_with_supplied_content_creates_snapshot_knowledge_and_search(test_client, test_session):
    tenant = await _tenant(test_session)

    response = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "feishu_doc",
            "name": "经营规则说明",
            "external_id": "docx_123",
            "source_url": "https://example.feishu.cn/docx/docx_123",
            "content": "收入定义：已支付订单的净额。\n\n复购风险：30 天未复购客户需要关注。",
            "external_revision": "rev-8",
            "metadata": {
                "title_path": ["经营", "规则"],
                "locator": {
                    "document_token": "docx_123",
                    "block_id": "blk_revenue_definition",
                    "heading_path": ["经营", "规则", "收入定义"],
                },
            },
        },
    )

    assert response.status_code == 201
    resource = response.json()["data"]
    assert resource["resource_type"] == "feishu_doc"
    assert resource["status"] == "ready"
    assert resource["latest_snapshot"]["status"] == "indexed"
    assert resource["knowledge_resource"]["index_status"] == "indexed"
    assert resource["knowledge_resource"]["evidence_count"] == 2
    assert resource["knowledge_resource"]["context_uri"].startswith("byaan-native://resources/")
    assert resource["knowledge_resource"]["provider_status"] == "indexed"
    assert resource["knowledge_resource"]["retrieval_debug_uri"].startswith("byaan-native://debug/resources/")
    assert resource["knowledge_resource"]["provider_metadata_json"]["storage_role"] == "local_dev_fallback"
    assert resource["knowledge_resource"]["provider_metadata_json"]["control_plane_text_storage"] is True

    search = await test_client.post("/api/knowledge/search", json={"query": "收入", "limit": 5})
    assert search.status_code == 200
    items = search.json()["data"]["items"]
    assert len(items) == 1
    assert "收入定义" in items[0]["text"]
    assert items[0]["locator_json"]["snapshot_id"] == str(resource["latest_snapshot_id"])
    assert items[0]["locator_json"]["document_token"] == "docx_123"
    assert items[0]["locator_json"]["block_id"] == "blk_revenue_definition"
    assert items[0]["locator_json"]["heading_path"] == ["经营", "规则", "收入定义"]
    assert items[0]["locator_json"]["revision"] == "rev-8"
    assert items[0]["locator_json"]["original_url"] == "https://example.feishu.cn/docx/docx_123"

    rows = (await test_session.execute(select(SourceResource))).scalars().all()
    snapshots = (await test_session.execute(select(SourceSnapshot))).scalars().all()
    knowledge = (await test_session.execute(select(KnowledgeResource))).scalars().all()
    evidence = (await test_session.execute(select(EvidenceFragment))).scalars().all()
    assert len(rows) == 1
    assert rows[0].tenant_id == tenant.id
    assert len(snapshots) == 1
    assert len(knowledge) == 1
    assert knowledge[0].context_uri == resource["knowledge_resource"]["context_uri"]
    assert knowledge[0].provider_status == "indexed"
    assert knowledge[0].last_indexed_at is not None
    assert len(evidence) == 2


async def test_openviking_provider_factory_is_explicit_boundary(test_session):
    provider = get_knowledge_provider("openviking")

    assert provider.provider == "openviking"
    with pytest.raises(RuntimeError, match="OpenVikingKnowledgeProvider is selected but not configured"):
        await provider.search(
            session=test_session,
            input=KnowledgeSearchInput(tenant_id=uuid4(), query="收入", limit=1),
        )


async def test_native_provider_factory_remains_default_local_dev(monkeypatch):
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.delenv("KNOWLEDGE_PROVIDER", raising=False)
    monkeypatch.delenv("KNOWLEDGE_PROVIDER_MODE", raising=False)
    monkeypatch.delenv("KNOWLEDGE_PROVIDER_REQUIRE_EXTERNAL", raising=False)
    monkeypatch.delenv("KNOWLEDGE_PROVIDER_ALLOW_NATIVE", raising=False)

    provider = get_knowledge_provider()

    assert isinstance(provider, NativeKnowledgeProvider)
    assert provider.provider == "byaan-native"


async def test_external_provider_required_rejects_native_fallback(monkeypatch):
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.setenv("KNOWLEDGE_PROVIDER_REQUIRE_EXTERNAL", "true")
    monkeypatch.delenv("KNOWLEDGE_PROVIDER", raising=False)
    monkeypatch.delenv("KNOWLEDGE_PROVIDER_ALLOW_NATIVE", raising=False)

    with pytest.raises(RuntimeError, match="stores evidence text in the control database"):
        get_knowledge_provider()


async def test_self_hosted_rejects_native_fallback_by_default(monkeypatch):
    monkeypatch.setenv("APP_MODE", "self-hosted")
    monkeypatch.delenv("KNOWLEDGE_PROVIDER", raising=False)
    monkeypatch.delenv("KNOWLEDGE_PROVIDER_REQUIRE_EXTERNAL", raising=False)
    monkeypatch.delenv("KNOWLEDGE_PROVIDER_ALLOW_NATIVE", raising=False)

    with pytest.raises(RuntimeError, match="APP_MODE=self-hosted"):
        get_knowledge_provider("byaan-native")


async def test_native_provider_can_be_explicitly_allowed_for_migration_drill(monkeypatch):
    monkeypatch.setenv("APP_MODE", "self-hosted")
    monkeypatch.setenv("KNOWLEDGE_PROVIDER_ALLOW_NATIVE", "true")

    provider = get_knowledge_provider("byaan-native")

    assert isinstance(provider, NativeKnowledgeProvider)


async def test_commercial_mode_allows_explicit_openviking_provider(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_PROVIDER_MODE", "commercial")
    monkeypatch.delenv("KNOWLEDGE_PROVIDER_ALLOW_NATIVE", raising=False)

    provider = get_knowledge_provider("open-viking")

    assert isinstance(provider, OpenVikingKnowledgeProvider)


async def test_unknown_knowledge_provider_does_not_silently_fallback_to_native(monkeypatch):
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.delenv("KNOWLEDGE_PROVIDER_REQUIRE_EXTERNAL", raising=False)
    monkeypatch.delenv("KNOWLEDGE_PROVIDER_ALLOW_NATIVE", raising=False)

    with pytest.raises(ValueError, match="Unsupported KNOWLEDGE_PROVIDER"):
        get_knowledge_provider("typo-provider")


async def test_native_provider_search_returns_provider_neutral_evidence(test_client, test_session):
    tenant = await _tenant(test_session)
    created = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "feishu_doc",
            "name": "经营规则说明",
            "external_id": "docx_provider_payload",
            "content": "收入定义：已支付订单的净额。",
            "external_revision": "rev-provider-payload",
        },
    )
    assert created.status_code == 201

    provider = get_knowledge_provider("byaan-native")
    results = await provider.search(
        session=test_session,
        input=KnowledgeSearchInput(tenant_id=tenant.id, query="收入", limit=5),
    )

    assert results
    assert isinstance(results[0], KnowledgeEvidence)
    assert not isinstance(results[0], EvidenceFragment)
    assert results[0].text == "收入定义：已支付订单的净额。"


async def test_read_evidence_returns_source_snapshot_and_resource_context(test_client):
    created = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "feishu_doc",
            "name": "经营规则说明",
            "external_id": "docx_456",
            "source_url": "https://example.feishu.cn/docx/docx_456",
            "content": "收入定义：已支付订单的净额。\n\n复购风险：30 天未复购客户需要关注。",
            "external_revision": "rev-9",
            "metadata": {
                "title_path": ["经营", "规则"],
                "locator": {
                    "document_token": "docx_456",
                    "block_id": "blk_retention_risk",
                    "heading_path": ["经营", "规则", "复购风险"],
                },
            },
        },
    )
    assert created.status_code == 201

    search = await test_client.post("/api/knowledge/search", json={"query": "复购风险", "limit": 5})
    assert search.status_code == 200
    evidence_id = search.json()["data"]["items"][0]["id"]

    response = await test_client.get(f"/api/evidence/{evidence_id}")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["evidence"]["id"] == evidence_id
    assert payload["evidence"]["text"] == "复购风险：30 天未复购客户需要关注。"
    assert payload["evidence"]["locator_json"]["block_id"] == "blk_retention_risk"
    assert payload["source_snapshot"]["id"] == payload["evidence"]["snapshot_id"]
    assert payload["source_snapshot"]["external_revision"] == "rev-9"
    assert payload["source_resource"]["id"] == created.json()["data"]["id"]
    assert payload["source_resource"]["resource_type"] == "feishu_doc"
    assert payload["source_resource"]["status"] == "ready"
    assert payload["knowledge_resource"]["id"] == payload["evidence"]["knowledge_resource_id"]


async def test_source_resource_sync_reuses_existing_snapshot_for_identical_content(test_client, test_session):
    created = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "pdf",
            "name": "渠道复盘",
            "content": "第 1 页：华东渠道收入增长。\n\n第 2 页：复购率低于目标。",
            "external_revision": "rev-1",
        },
    )
    assert created.status_code == 201
    resource = created.json()["data"]
    original_snapshot_id = resource["latest_snapshot_id"]

    synced = await test_client.post(
        f"/api/source-resources/{resource['id']}/sync",
        json={
            "content": "第 1 页：华东渠道收入增长。\n\n第 2 页：复购率低于目标。",
            "external_revision": "rev-1",
        },
    )
    assert synced.status_code == 200
    synced_resource = synced.json()["data"]
    assert synced_resource["status"] == "ready"
    assert synced_resource["latest_snapshot_id"] == original_snapshot_id

    snapshots = (await test_session.execute(select(SourceSnapshot))).scalars().all()
    evidence = (await test_session.execute(select(EvidenceFragment))).scalars().all()
    assert len(snapshots) == 1
    assert len(evidence) == 2


async def test_source_resource_snapshots_api_lists_immutable_versions(test_client):
    created = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "pdf",
            "name": "渠道复盘",
            "content": "第 1 页：华东渠道收入增长。",
            "external_revision": "rev-1",
        },
    )
    assert created.status_code == 201
    resource = created.json()["data"]
    first_snapshot_id = resource["latest_snapshot_id"]

    synced = await test_client.post(
        f"/api/source-resources/{resource['id']}/sync",
        json={
            "content": "第 1 页：华东渠道收入增长。\n\n第 2 页：复购率低于目标。",
            "external_revision": "rev-2",
        },
    )
    assert synced.status_code == 200
    second_snapshot_id = synced.json()["data"]["latest_snapshot_id"]
    assert second_snapshot_id != first_snapshot_id

    response = await test_client.get(f"/api/source-resources/{resource['id']}/snapshots")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total"] == 2
    assert [item["external_revision"] for item in payload["items"]] == ["rev-2", "rev-1"]
    assert payload["items"][0]["id"] == second_snapshot_id
    assert payload["items"][0]["is_latest"] is True
    assert payload["items"][1]["id"] == first_snapshot_id
    assert payload["items"][1]["is_latest"] is False


async def test_web_source_refresh_reuses_identical_snapshot_and_failure_preserves_last_success(test_client, test_session, monkeypatch):
    from server.services.source_connectors import ConnectorError
    from server.services.web_source_adapter import WebCapturedPage

    calls = 0

    async def fake_capture(self, url):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise ConnectorError("Web page returned HTTP 500", code="source_unavailable", permanent=True)
        return WebCapturedPage(
            raw_bytes=b"<html><body><p>Stable public report.</p></body></html>",
            content_text="Stable public report.",
            external_revision=f"etag-web-{calls}",
            metadata={"provider": "web", "final_url": url, "redirect_chain": [], "status_code": 200},
            parser_version="web-html-parser-v1",
            raw_storage_uri="web://sha256/stable",
        )

    monkeypatch.setattr("server.services.web_source_adapter.WebSourceAdapter.capture", fake_capture)

    created = await test_client.post(
        "/api/source-resources",
        json={"resource_type": "web", "name": "公开行业页面", "source_url": "https://example.com/report"},
    )
    assert created.status_code == 201
    resource = created.json()["data"]
    original_snapshot_id = resource["latest_snapshot_id"]

    refreshed = await test_client.post(f"/api/source-resources/{resource['id']}/sync", json={})
    assert refreshed.status_code == 200
    refreshed_resource = refreshed.json()["data"]
    assert refreshed_resource["status"] == "ready"
    assert refreshed_resource["latest_snapshot_id"] == original_snapshot_id
    success_run = refreshed_resource["sync_config_json"]["latest_sync_run"]
    assert success_run["status"] == "succeeded"
    assert success_run["trigger"] == "manual"
    assert success_run["checkpoint"]["snapshot_id"] == original_snapshot_id
    assert success_run["checkpoint"]["external_revision"] == "etag-web-1"

    failed = await test_client.post(f"/api/source-resources/{resource['id']}/sync", json={})
    assert failed.status_code == 200
    failed_resource = failed.json()["data"]
    assert failed_resource["status"] == "source_unavailable"
    assert failed_resource["latest_snapshot_id"] == original_snapshot_id
    assert failed_resource["sync_config_json"]["last_error"]["code"] == "source_unavailable"
    failed_run = failed_resource["sync_config_json"]["latest_sync_run"]
    assert failed_run["status"] == "failed"
    assert failed_run["trigger"] == "manual"
    assert failed_run["checkpoint"] is None
    assert failed_run["error"]["code"] == "source_unavailable"

    snapshots = (await test_session.execute(select(SourceSnapshot))).scalars().all()
    evidence = (await test_session.execute(select(EvidenceFragment))).scalars().all()
    assert len(snapshots) == 1
    assert len(evidence) == 1


async def test_pdf_upload_creates_snapshot_knowledge_and_preserves_raw_pdf(test_client):
    raw_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nstream\n(Channel revenue grew 12%) Tj\nendstream\nendobj\n%%EOF"

    response = await test_client.post(
        "/api/source-resources/files",
        data={"name": "渠道复盘 PDF"},
        files={"file": ("channel-review.pdf", raw_pdf, "application/pdf")},
    )

    assert response.status_code == 201
    resource = response.json()["data"]
    assert resource["resource_type"] == "pdf"
    assert resource["status"] == "ready"
    assert resource["latest_snapshot"]["status"] == "indexed"
    assert resource["latest_snapshot"]["raw_storage_uri"].startswith("file://source-resources/")
    assert resource["latest_snapshot"]["metadata_json"]["raw_size"] == len(raw_pdf)
    assert resource["knowledge_resource"]["evidence_count"] == 1

    search = await test_client.post("/api/knowledge/search", json={"query": "revenue", "limit": 5})
    assert search.status_code == 200
    assert "Channel revenue" in search.json()["data"]["items"][0]["text"]


async def test_legacy_pdf_upload_endpoint_still_creates_source_resource(test_client):
    raw_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nstream\n(Legacy PDF endpoint still works) Tj\nendstream\nendobj\n%%EOF"

    response = await test_client.post(
        "/api/source-resources/pdf",
        data={"name": "兼容 PDF"},
        files={"file": ("legacy.pdf", raw_pdf, "application/pdf")},
    )

    assert response.status_code == 201
    resource = response.json()["data"]
    assert resource["resource_type"] == "pdf"
    assert resource["status"] == "ready"


async def test_csv_file_upload_creates_source_snapshot_context_and_projection(test_client):
    raw_csv = b"region,revenue\nEast,120\nWest,80\n"

    response = await test_client.post(
        "/api/source-resources/files",
        data={"name": "渠道收入 CSV"},
        files={"file": ("channel-revenue.csv", raw_csv, "text/csv")},
    )

    assert response.status_code == 201
    resource = response.json()["data"]
    assert resource["resource_type"] == "file"
    assert resource["status"] == "ready"
    assert resource["latest_snapshot"]["metadata_json"]["provider"] == "local_file_upload"
    assert resource["latest_snapshot"]["metadata_json"]["file_type"] == "csv"
    assert resource["latest_snapshot"]["metadata_json"]["projected_dataset_id"]
    assert resource["projected_dataset_id"] == resource["latest_snapshot"]["metadata_json"]["projected_dataset_id"]
    assert resource["knowledge_resource"]["evidence_count"] == 1

    search = await test_client.post("/api/knowledge/search", json={"query": "East", "limit": 5})
    assert search.status_code == 200
    assert "East" in search.json()["data"]["items"][0]["text"]


async def test_csv_file_upload_can_reindex_from_raw_artifact(test_client, test_session):
    raw_csv = b"region,revenue\nEast,120\nWest,80\n"

    created = await test_client.post(
        "/api/source-resources/files",
        data={"name": "渠道收入 CSV"},
        files={"file": ("channel-revenue.csv", raw_csv, "text/csv")},
    )
    assert created.status_code == 201
    original = created.json()["data"]
    original_snapshot_id = original["latest_snapshot_id"]
    original_projected_dataset_id = original["projected_dataset_id"]

    synced = await test_client.post(
        f"/api/source-resources/{original['id']}/sync",
        json={"metadata": {"trigger": "test_reindex"}},
    )

    assert synced.status_code == 200
    resource = synced.json()["data"]
    assert resource["status"] == "ready"
    assert resource["latest_snapshot_id"] == original_snapshot_id
    assert resource["projected_dataset_id"] == original_projected_dataset_id
    assert resource["sync_config_json"]["latest_sync_run"]["status"] == "succeeded"
    assert resource["sync_config_json"]["latest_sync_run"]["checkpoint"]["snapshot_id"] == original_snapshot_id
    assert "last_error" not in resource["sync_config_json"]

    snapshots = (await test_session.execute(select(SourceSnapshot))).scalars().all()
    evidence = (await test_session.execute(select(EvidenceFragment))).scalars().all()
    assert len(snapshots) == 1
    assert len(evidence) == 1


async def test_docx_and_pptx_file_uploads_become_context_sources(test_client):
    docx_bytes = _docx_bytes("Docx revenue policy")
    pptx_bytes = _pptx_bytes("Slide retention risk")

    docx_response = await test_client.post(
        "/api/source-resources/files",
        data={"name": "经营规则 Docx"},
        files={"file": ("rules.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    pptx_response = await test_client.post(
        "/api/source-resources/files",
        data={"name": "复购风险 PPTX"},
        files={"file": ("retention.pptx", pptx_bytes, "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
    )

    assert docx_response.status_code == 201
    assert pptx_response.status_code == 201
    docx_resource = docx_response.json()["data"]
    pptx_resource = pptx_response.json()["data"]
    assert docx_resource["resource_type"] == "file"
    assert docx_resource["latest_snapshot"]["metadata_json"]["file_type"] == "docx"
    assert docx_resource["projected_dataset_id"] is None
    assert docx_resource["knowledge_resource"]["evidence_count"] == 1
    assert pptx_resource["resource_type"] == "file"
    assert pptx_resource["latest_snapshot"]["metadata_json"]["file_type"] == "pptx"
    assert pptx_resource["projected_dataset_id"] is None
    assert pptx_resource["knowledge_resource"]["evidence_count"] >= 1

    search = await test_client.post("/api/knowledge/search", json={"query": "retention", "limit": 5})
    assert search.status_code == 200
    assert "retention risk" in search.json()["data"]["items"][0]["text"]


async def test_pdf_upload_parse_failure_keeps_failed_snapshot(test_client):
    response = await test_client.post(
        "/api/source-resources/pdf",
        data={"name": "扫描件 PDF"},
        files={"file": ("scan.pdf", b"%PDF-1.7\n", "application/pdf")},
    )

    assert response.status_code == 201
    resource = response.json()["data"]
    assert resource["resource_type"] == "pdf"
    assert resource["status"] == "failed"
    assert resource["latest_snapshot"]["status"] == "failed"
    assert resource["latest_snapshot"]["error_json"]["code"] == "parser_no_text"
    assert resource["sync_config_json"]["last_error"]["code"] == "parser_no_text"
    assert resource["knowledge_resource"] is None


async def test_failed_pdf_upload_retry_reparses_raw_artifact_and_preserves_failed_snapshot(test_client, test_session):
    created = await test_client.post(
        "/api/source-resources/pdf",
        data={"name": "扫描件 PDF"},
        files={"file": ("scan.pdf", b"%PDF-1.7\n", "application/pdf")},
    )
    assert created.status_code == 201
    original = created.json()["data"]

    synced = await test_client.post(f"/api/source-resources/{original['id']}/sync", json={})

    assert synced.status_code == 200
    resource = synced.json()["data"]
    assert resource["status"] == "failed"
    assert resource["latest_snapshot_id"] == original["latest_snapshot_id"]
    assert resource["latest_snapshot"]["status"] == "failed"
    assert resource["sync_config_json"]["last_error"]["code"] == "parser_no_text"
    sync_run = resource["sync_config_json"]["latest_sync_run"]
    assert sync_run["status"] == "failed"
    assert sync_run["error"]["code"] == "parser_no_text"
    assert sync_run["checkpoint"] is None

    snapshots = (await test_session.execute(select(SourceSnapshot))).scalars().all()
    knowledge = (await test_session.execute(select(KnowledgeResource))).scalars().all()
    assert len(snapshots) == 1
    assert knowledge == []

    processing = await test_client.get(f"/api/source-resources/{original['id']}/processing")
    assert processing.status_code == 200
    payload = processing.json()["data"]
    assert payload["stage"] == "failed"
    assert payload["message"] == "PDF text extraction produced no text; configure a PDF parser worker"
    assert payload["next_actions"] == ["Upload a readable file", "Retry parse from raw artifact"]


def _docx_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            f"<w:document><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>",
        )
    return buffer.getvalue()


def _pptx_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            f"<p:sld><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>",
        )
    return buffer.getvalue()


async def test_source_resource_without_connector_content_is_not_marked_ready(test_client):
    response = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "web",
            "name": "公开行业页面",
        },
    )

    assert response.status_code == 201
    resource = response.json()["data"]
    assert resource["status"] == "needs_confirmation"
    assert resource["latest_snapshot"] is None
    assert resource["knowledge_resource"] is None

    processing = await test_client.get(f"/api/source-resources/{resource['id']}/processing")
    assert processing.status_code == 200
    payload = processing.json()["data"]
    assert payload["connector_required"] is True
    assert payload["stage"] == "waiting_for_connector"
    assert payload["message"] == "No source snapshot has been captured yet. Complete setup or add source content before indexing."
    assert payload["next_actions"] == ["Add source URL", "Review crawl policy"]
    assert payload["last_error"] is None
    _assert_product_processing_copy(payload)


async def test_processing_payload_for_captured_unindexed_source_uses_product_actions(test_client, test_session):
    tenant = await _tenant(test_session)
    service = SourceResourceService()
    resource = SourceResource(
        tenant_id=tenant.id,
        resource_type="file",
        name="Captured CSV",
        visibility="workspace",
        sync_mode="manual",
        sync_config_json={"original_filename": "captured.csv", "file_type": "csv"},
        status="pending",
    )
    test_session.add(resource)
    await test_session.flush()
    snapshot = SourceSnapshot(
        tenant_id=tenant.id,
        resource_id=resource.id,
        external_revision="rev-captured",
        content_hash="sha256:captured",
        raw_storage_uri=f"file://source-resources/{resource.id}/raw/captured.csv",
        parser_version="test-parser-v1",
        metadata_json={"original_filename": "captured.csv", "file_type": "csv"},
        status="captured",
    )
    test_session.add(snapshot)
    await test_session.flush()
    resource.latest_snapshot_id = snapshot.id
    await test_session.commit()

    payload = await service.processing_payload(session=test_session, tenant_id=tenant.id, resource_id=str(resource.id))

    assert payload["stage"] == "captured"
    assert payload["connector_required"] is False
    assert payload["message"] == "Snapshot is captured, but parsing, projection, or context indexing is incomplete."
    assert payload["next_actions"] == ["Retry parse from raw artifact", "Review parsed content"]
    _assert_product_processing_copy(payload)


async def test_web_source_url_fetch_creates_snapshot_knowledge_and_search(test_client, monkeypatch):
    from server.services.web_source_adapter import WebCapturedPage

    async def fake_capture(self, url):
        assert url == "https://example.com/report"
        return WebCapturedPage(
            raw_bytes=b"<html><title>Industry Report</title><body><h1>Channel report</h1><p>East revenue grew 12%.</p></body></html>",
            content_text="Channel report\n\nEast revenue grew 12%.",
            external_revision="etag-web-1",
            metadata={
                "provider": "web",
                "initial_url": "https://example.com/report",
                "canonical_url": "https://example.com/report",
                "final_url": "https://example.com/report",
                "redirect_chain": [],
                "status_code": 200,
                "content_type": "text/html",
                "title": "Industry Report",
                "raw_size": 106,
            },
            parser_version="web-html-parser-v1",
            raw_storage_uri="web://sha256/webhash",
        )

    monkeypatch.setattr("server.services.web_source_adapter.WebSourceAdapter.capture", fake_capture)

    response = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "web",
            "name": "公开行业页面",
            "source_url": "https://example.com/report",
        },
    )

    assert response.status_code == 201
    resource = response.json()["data"]
    assert resource["status"] == "ready"
    assert resource["latest_snapshot"]["external_revision"] == "etag-web-1"
    assert resource["latest_snapshot"]["raw_storage_uri"] == "web://sha256/webhash"
    assert resource["latest_snapshot"]["metadata_json"]["canonical_url"] == "https://example.com/report"
    assert resource["latest_snapshot"]["metadata_json"]["final_url"] == "https://example.com/report"
    assert resource["latest_snapshot"]["metadata_json"]["source_resource_id"] == resource["id"]
    assert resource["latest_snapshot"]["metadata_json"]["source_connection_id"] is None
    assert resource["latest_snapshot"]["metadata_json"]["provider"] == "web"
    assert resource["latest_snapshot"]["metadata_json"]["knowledge_provider"] == "byaan-native"
    assert resource["latest_snapshot"]["metadata_json"]["content_hash"] == resource["latest_snapshot"]["content_hash"]
    assert resource["knowledge_resource"]["evidence_count"] == 2

    search = await test_client.post("/api/knowledge/search", json={"query": "East", "limit": 5})
    assert search.status_code == 200
    items = search.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["fragment_type"] == "url_section"
    assert "East revenue" in items[0]["text"]
    assert items[0]["locator_json"]["source_url"] == "https://example.com/report"


async def test_web_source_blocks_private_urls(test_client):
    response = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "web",
            "name": "本机页面",
            "source_url": "http://127.0.0.1:8080/admin",
        },
    )

    assert response.status_code == 201
    resource = response.json()["data"]
    assert resource["status"] == "failed"
    assert resource["latest_snapshot"] is None
    assert resource["sync_config_json"]["last_error"]["code"] == "blocked_private_url"

    processing = await test_client.get(f"/api/source-resources/{resource['id']}/processing")
    assert processing.status_code == 200
    payload = processing.json()["data"]
    assert payload["stage"] == "failed"
    assert payload["connector_required"] is False
    assert payload["last_error"]["code"] == "blocked_private_url"
    assert payload["message"].startswith("Access to private or non-routable address is not allowed")
    assert payload["next_actions"] == ["Review source settings", "Retry sync"]
    _assert_product_processing_copy(payload)


async def test_real_public_web_url_capture_e2e(test_client):
    response = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "web",
            "name": "Example Domain",
            "source_url": "https://example.com/",
        },
    )
    if response.status_code != 201:
        pytest.skip(f"public web E2E unavailable: HTTP {response.status_code} {response.text[:200]}")
    resource = response.json()["data"]
    if resource["status"] != "ready":
        error = (resource.get("sync_config_json") or {}).get("last_error") or {}
        pytest.skip(f"public web E2E unavailable: {error}")
    assert resource["latest_snapshot"]["metadata_json"]["final_url"] == "https://example.com/"
    assert resource["latest_snapshot"]["parser_version"] == "web-html-parser-v1"
    assert resource["latest_snapshot"]["content_hash"].startswith("sha256:")
    assert resource["knowledge_resource"]["evidence_count"] >= 1

    search = await test_client.post("/api/knowledge/search", json={"query": "Example Domain", "limit": 5})
    assert search.status_code == 200
    items = search.json()["data"]["items"]
    assert any("Example Domain" in item["text"] for item in items)


async def test_datasources_list_includes_source_resource_and_delete_removes_it(test_client, monkeypatch):
    from server.services.web_source_adapter import WebCapturedPage

    async def fake_capture(self, url):
        return WebCapturedPage(
            raw_bytes=b"<html><body>Public report</body></html>",
            content_text="Public report",
            external_revision="etag-web-1",
            metadata={"provider": "web", "final_url": url, "redirect_chain": [], "status_code": 200},
            parser_version="web-html-parser-v1",
            raw_storage_uri="web://sha256/webhash",
        )

    monkeypatch.setattr("server.services.web_source_adapter.WebSourceAdapter.capture", fake_capture)

    created = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "web",
            "name": "公开行业页面",
            "source_url": "https://example.com/report",
        },
    )
    assert created.status_code == 201
    resource = created.json()["data"]

    listed = await test_client.get("/api/datasources")
    assert listed.status_code == 200
    source_item = next(item for item in listed.json()["data"]["items"] if item["id"] == resource["id"])
    assert source_item["source_type"] == "source_resource"
    assert source_item["type"] == "web"
    assert source_item["status"] == "ready"

    deleted = await test_client.delete(f"/api/source-resources/{resource['id']}")
    assert deleted.status_code == 204

    listed_after_delete = await test_client.get("/api/datasources")
    assert listed_after_delete.status_code == 200
    assert all(item["id"] != resource["id"] for item in listed_after_delete.json()["data"]["items"])


async def test_delete_source_resource_records_tombstone_before_removal(test_client, test_session, monkeypatch):
    from server.services.web_source_adapter import WebCapturedPage

    async def fake_capture(self, url):
        return WebCapturedPage(
            raw_bytes=b"<html><body>Public report</body></html>",
            content_text="Public report",
            external_revision="etag-web-1",
            metadata={"provider": "web", "final_url": url, "redirect_chain": [], "status_code": 200},
            parser_version="web-html-parser-v1",
            raw_storage_uri="web://sha256/webhash",
        )

    monkeypatch.setattr("server.services.web_source_adapter.WebSourceAdapter.capture", fake_capture)

    created = await test_client.post(
        "/api/source-resources",
        json={"resource_type": "web", "name": "公开行业页面", "source_url": "https://example.com/report"},
    )
    assert created.status_code == 201
    resource = created.json()["data"]

    deleted = await test_client.delete(f"/api/source-resources/{resource['id']}")
    assert deleted.status_code == 204

    tombstone_snapshot = await test_session.scalar(
        select(SourceSnapshot).where(SourceSnapshot.resource_id == resource["id"]).order_by(SourceSnapshot.captured_at.desc())
    )
    assert tombstone_snapshot is not None
    assert tombstone_snapshot.metadata_json["deletion_marker"]["status"] == "removed"
    assert tombstone_snapshot.metadata_json["deletion_marker"]["source_resource_id"] == resource["id"]
    assert tombstone_snapshot.metadata_json["deletion_marker"]["latest_snapshot_id"] == resource["latest_snapshot_id"]


async def test_notebook_assets_bind_knowledge_resource(test_client, test_session):
    notebook = await _create_notebook(test_client)
    created = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "pdf",
            "name": "行业报告",
            "content": "第 16 页：渠道复购率低于经营目标。",
        },
    )
    assert created.status_code == 201
    knowledge_id = created.json()["data"]["knowledge_resource"]["id"]

    bind = await test_client.post(
        f"/api/notebooks/{notebook['id']}/assets",
        json={
            "asset_type": "knowledge_resource",
            "asset_id": knowledge_id,
            "usage_policy": {"purpose": "evidence", "allow_snapshot_reuse": False},
        },
    )
    assert bind.status_code == 200
    asset = bind.json()["data"]
    assert asset["asset_type"] == "knowledge_resource"
    assert asset["asset_id"] == knowledge_id

    listed = await test_client.get(f"/api/notebooks/{notebook['id']}/assets")
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1

    rows = (await test_session.execute(select(NotebookAsset))).scalars().all()
    assert len(rows) == 1
    assert rows[0].usage_policy_json["purpose"] == "evidence"


async def test_source_detail_support_apis_return_parsed_assets_lineage_and_consumers(test_client, test_session):
    tenant = await _tenant(test_session)
    notebook = await _create_notebook(test_client)
    created = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "feishu_doc",
            "name": "经营规则说明",
            "external_id": "docx_rules",
            "source_url": "https://example.feishu.cn/docx/docx_rules",
            "content": "渠道收入达成率 = 实际收入 / 目标收入。",
            "external_revision": "rev-20",
            "metadata": {
                "tables": [{"name": "rules_table", "row_count": 1, "column_count": 2}],
                "parser_warnings": ["one formula was kept as text"],
                "locator": {"document_token": "docx_rules", "block_id": "blk_rule"},
            },
        },
    )
    assert created.status_code == 201
    resource = created.json()["data"]
    knowledge_id = resource["knowledge_resource"]["id"]

    bind = await test_client.post(
        f"/api/notebooks/{notebook['id']}/assets",
        json={"asset_type": "knowledge_resource", "asset_id": knowledge_id, "usage_policy": {"purpose": "evidence"}},
    )
    assert bind.status_code == 200

    semantic_model = SemanticModel(
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        slug="rules_model",
        name="Rules Model",
        domain="Operations",
        owner="Data Team",
        datasource_id=resource["id"],
        datasource_name=resource["name"],
        datasource_kind="feishu_doc",
        description="Rules semantic draft",
        status="Draft",
        readiness=45,
        readiness_level="review",
        published_version="v0",
    )
    test_session.add(semantic_model)
    test_session.add(
        Dashboard(
            tenant_id=tenant.id,
            notebook_id=notebook["id"],
            version_num=1,
            html_content="<html>dashboard</html>",
        )
    )
    test_session.add(
        AnalysisArtifact(
            tenant_id=tenant.id,
            notebook_id=notebook["id"],
            name="经营规则分析",
            objective="Explain rules",
            definition_json={"source_snapshot_refs": [resource["latest_snapshot_id"]]},
            status="published",
        )
    )
    await test_session.commit()

    parsed = await test_client.get(f"/api/source-resources/{resource['id']}/parsed-assets")
    assert parsed.status_code == 200
    parsed_payload = parsed.json()["data"]
    assert parsed_payload["latest_snapshot_id"] == resource["latest_snapshot_id"]
    assert parsed_payload["parser_warnings"] == ["one formula was kept as text"]
    assert parsed_payload["tables"][0]["name"] == "rules_table"
    assert parsed_payload["evidence_count"] == 1

    lineage = await test_client.get(f"/api/source-resources/{resource['id']}/lineage")
    assert lineage.status_code == 200
    lineage_payload = lineage.json()["data"]
    node_types = {node["node_type"] for node in lineage_payload["nodes"]}
    assert {"source_resource", "source_snapshot", "knowledge_resource"}.issubset(node_types)
    assert any(edge["relationship"] == "captured_as" for edge in lineage_payload["edges"])
    assert any(edge["relationship"] == "indexed_as" for edge in lineage_payload["edges"])

    consumers = await test_client.get(f"/api/source-resources/{resource['id']}/consumers")
    assert consumers.status_code == 200
    consumer_payload = consumers.json()["data"]
    consumer_types = {item["consumer_type"] for item in consumer_payload["items"]}
    assert {"semantic_model", "notebook", "dashboard", "analysis_artifact"}.issubset(consumer_types)
    assert consumer_payload["counts"]["semantic_model"] == 1
    assert consumer_payload["counts"]["notebook"] == 1


async def test_agent_asset_search_and_describe_spans_dataset_and_knowledge_resource(test_client, test_session):
    tenant = await _tenant(test_session)
    notebook = await _create_notebook(test_client)

    dataset = Dataset(
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        type="file",
        name="经营目标 Sheet",
        description="各渠道月度目标，可用于达成率计算。",
        schema_cache=json.dumps(
            {
                "tables": {
                    "targets": {
                        "columns": [
                            {"name": "channel", "type": "TEXT"},
                            {"name": "month", "type": "TEXT"},
                            {"name": "target_revenue", "type": "REAL"},
                        ]
                    }
                }
            }
        ),
        is_public=True,
    )
    test_session.add(dataset)
    await test_session.flush()
    test_session.add(
        File(
            tenant_id=tenant.id,
            dataset_id=dataset.id,
            name="targets.xlsx",
            type="xlsx",
            size=2048,
        )
    )
    await test_session.commit()
    await test_session.refresh(dataset)

    bind_dataset = await test_client.post(
        f"/api/notebooks/{notebook['id']}/assets",
        json={
            "asset_type": "dataset",
            "asset_id": str(dataset.id),
            "usage_policy": {"purpose": "calculation", "source": "feishu_sheet_projection"},
        },
    )
    assert bind_dataset.status_code == 200

    created_doc = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "feishu_doc",
            "name": "经营规则说明",
            "external_id": "docx_rules",
            "source_url": "https://example.feishu.cn/docx/docx_rules",
            "content": "渠道收入达成率 = 实际收入 / 目标收入。\n\n低于 80% 需要解释原因。",
            "external_revision": "rev-12",
            "metadata": {
                "locator": {
                    "document_token": "docx_rules",
                    "block_id": "blk_attainment_rule",
                    "heading_path": ["经营规则", "达成率"],
                }
            },
        },
    )
    assert created_doc.status_code == 201
    knowledge_resource_id = created_doc.json()["data"]["knowledge_resource"]["id"]

    bind_knowledge = await test_client.post(
        f"/api/notebooks/{notebook['id']}/assets",
        json={
            "asset_type": "knowledge_resource",
            "asset_id": knowledge_resource_id,
            "usage_policy": {"purpose": "policy_evidence"},
        },
    )
    assert bind_knowledge.status_code == 200

    search = await test_client.post(
        "/api/assets/search",
        json={"notebook_id": notebook["id"], "query": "渠道 收入", "limit": 10},
    )
    assert search.status_code == 200
    items = search.json()["data"]["items"]
    assert {item["asset_type"] for item in items} == {"dataset", "knowledge_resource"}
    dataset_item = next(item for item in items if item["asset_type"] == "dataset")
    knowledge_item = next(item for item in items if item["asset_type"] == "knowledge_resource")
    assert dataset_item["capabilities"]["execution_modes"] == ["execute_dataset_query"]
    assert dataset_item["freshness"]["status"] == "current"
    assert dataset_item["provenance"]["source_snapshot_id"] is None
    assert knowledge_item["capabilities"]["execution_modes"] == ["search_knowledge", "read_evidence"]
    assert knowledge_item["freshness"]["source_status"] == "ready"
    assert knowledge_item["provenance"]["source_resource_type"] == "feishu_doc"

    described = await test_client.post(
        "/api/assets/describe",
        json={"asset_type": "knowledge_resource", "asset_id": knowledge_resource_id},
    )
    assert described.status_code == 200
    payload = described.json()["data"]
    assert payload["asset_type"] == "knowledge_resource"
    assert payload["capabilities"]["locator_types"] == ["block"]
    assert payload["provenance"]["source_revision"] == "rev-12"
    assert payload["freshness"]["snapshot_id"] == created_doc.json()["data"]["latest_snapshot_id"]
    assert payload["sample_evidence"][0]["locator_json"]["block_id"] == "blk_attainment_rule"


async def test_analysis_artifact_canonical_definition_render_and_run_preflight(test_client, test_session):
    notebook = await _create_notebook(test_client)
    create = await test_client.post(
        "/api/analysis-artifacts",
        json={
            "notebook_id": notebook["id"],
            "name": "渠道经营分析",
            "objective": "分析渠道收入、目标达成和复购风险",
            "definition": {
                "sections": [
                    {"type": "metric", "title": "本月收入", "metric_ref": "sales.revenue"},
                    {
                        "type": "finding",
                        "title": "华东复购风险",
                        "text": "华东收入增长最快，但复购率低于经营目标。",
                        "evidence_refs": ["query_region_growth", "feishu_doc_block_183"],
                    },
                    {"type": "chart", "title": "未绑定图表"},
                ],
                "source_snapshot_refs": ["oracle_sales_20260814", "feishu_targets_rev_83"],
            },
        },
    )
    assert create.status_code == 201
    artifact = create.json()["data"]
    assert artifact["definition_json"]["objective"] == "分析渠道收入、目标达成和复购风险"
    assert artifact["definition_json"]["source_snapshot_refs"] == ["oracle_sales_20260814", "feishu_targets_rev_83"]

    rendered = await test_client.get(f"/api/analysis-artifacts/{artifact['id']}/render?format=markdown")
    assert rendered.status_code == 200
    markdown = rendered.json()["data"]["content"]
    assert "# 渠道经营分析" in markdown
    assert "Metric: `sales.revenue`" in markdown
    assert "`feishu_doc_block_183`" in markdown

    preflight = await test_client.post(f"/api/analysis-artifacts/{artifact['id']}/runs")
    assert preflight.status_code == 200
    assert preflight.json()["data"]["required_bindings"] == ["未绑定图表: query_ref or metric_ref"]

    row = await test_session.scalar(select(AnalysisArtifact).where(AnalysisArtifact.id == artifact["id"]))
    assert row is not None
    assert row.status == "draft"
    assert (await test_session.scalar(select(Notebook).where(Notebook.id == notebook["id"]))) is not None


async def test_analysis_artifact_preflight_resolves_dependencies_and_latest_successful_snapshot(test_client):
    notebook = await _create_notebook(test_client)
    created_doc = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "feishu_doc",
            "name": "经营规则说明",
            "external_id": "docx_rules",
            "source_url": "https://example.feishu.cn/docx/docx_rules",
            "content": "华东收入增长最快，但复购率低于经营目标。",
            "external_revision": "rev-21",
            "metadata": {
                "locator": {
                    "document_token": "docx_rules",
                    "block_id": "blk_region_growth",
                    "heading_path": ["经营规则", "复购风险"],
                }
            },
        },
    )
    assert created_doc.status_code == 201
    evidence_search = await test_client.post("/api/knowledge/search", json={"query": "复购率", "limit": 1})
    assert evidence_search.status_code == 200
    evidence_id = evidence_search.json()["data"]["items"][0]["id"]
    snapshot_id = created_doc.json()["data"]["latest_snapshot_id"]

    create = await test_client.post(
        "/api/analysis-artifacts",
        json={
            "notebook_id": notebook["id"],
            "name": "渠道经营分析",
            "objective": "验证指标、证据和快照依赖",
            "definition": {
                "sections": [
                    {
                        "type": "metric",
                        "title": "本月收入",
                        "metric_ref": "sales.revenue",
                        "result_snapshot_ref": "result_20260814_success",
                    },
                    {
                        "type": "finding",
                        "title": "华东复购风险",
                        "text": "华东收入增长最快，但复购率低于经营目标。",
                        "evidence_refs": [evidence_id],
                    },
                ],
                "source_snapshot_refs": [snapshot_id],
                "result_snapshots": {
                    "result_20260814_success": {
                        "status": "succeeded",
                        "captured_at": "2026-08-14T10:30:00+08:00",
                        "query_ref": "query_region_growth",
                        "row_count": 12,
                    },
                    "result_failed": {
                        "status": "failed",
                        "captured_at": "2026-08-14T11:30:00+08:00",
                        "error": {"code": "source_unavailable"},
                    },
                },
            },
        },
    )
    assert create.status_code == 201
    artifact = create.json()["data"]

    preflight = await test_client.post(f"/api/analysis-artifacts/{artifact['id']}/runs")
    assert preflight.status_code == 200
    payload = preflight.json()["data"]
    assert payload["status"] == "not_started"
    assert payload["required_bindings"] == []
    assert payload["dependency_summary"]["queries"] == ["query_region_growth"]
    assert payload["dependency_summary"]["evidence"] == [evidence_id]
    assert payload["dependency_summary"]["source_snapshots"] == [snapshot_id]
    assert payload["blocking_issues"] == []

    latest = await test_client.get(f"/api/analysis-artifacts/{artifact['id']}/snapshots/latest-successful")
    assert latest.status_code == 200
    latest_payload = latest.json()["data"]
    assert latest_payload["artifact_id"] == artifact["id"]
    assert latest_payload["snapshot_id"] == "result_20260814_success"
    assert latest_payload["snapshot"]["status"] == "succeeded"
    assert latest_payload["snapshot"]["query_ref"] == "query_region_growth"
