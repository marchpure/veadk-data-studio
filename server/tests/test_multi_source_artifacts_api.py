from __future__ import annotations

from sqlalchemy import select

from server.models.analysis_artifacts import AnalysisArtifact
from server.models.knowledge_resources import EvidenceFragment, KnowledgeResource
from server.models.notebook_assets import NotebookAsset
from server.models.notebooks import Notebook
from server.models.source_resources import SourceResource
from server.models.source_snapshots import SourceSnapshot
from server.models.tenant import Tenant

pytestmark = __import__("pytest").mark.asyncio


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
            "metadata": {"title_path": ["经营", "规则"]},
        },
    )

    assert response.status_code == 201
    resource = response.json()["data"]
    assert resource["resource_type"] == "feishu_doc"
    assert resource["status"] == "ready"
    assert resource["latest_snapshot"]["status"] == "indexed"
    assert resource["knowledge_resource"]["index_status"] == "indexed"
    assert resource["knowledge_resource"]["evidence_count"] == 2

    search = await test_client.post("/api/knowledge/search", json={"query": "收入", "limit": 5})
    assert search.status_code == 200
    items = search.json()["data"]["items"]
    assert len(items) == 1
    assert "收入定义" in items[0]["text"]
    assert items[0]["locator_json"]["snapshot_id"] == str(resource["latest_snapshot_id"])

    rows = (await test_session.execute(select(SourceResource))).scalars().all()
    snapshots = (await test_session.execute(select(SourceSnapshot))).scalars().all()
    knowledge = (await test_session.execute(select(KnowledgeResource))).scalars().all()
    evidence = (await test_session.execute(select(EvidenceFragment))).scalars().all()
    assert len(rows) == 1
    assert rows[0].tenant_id == tenant.id
    assert len(snapshots) == 1
    assert len(knowledge) == 1
    assert len(evidence) == 2


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
    assert resource["latest_snapshot"]["metadata_json"]["final_url"] == "https://example.com/report"
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
