from __future__ import annotations

from sqlalchemy import select

from server.models.source_resources import SourceResource

pytestmark = __import__("pytest").mark.asyncio


async def test_sources_overview_includes_ready_web_source_and_compatibility_alias(
    test_client, test_session, monkeypatch
):
    from server.services.web_source_adapter import WebCapturedPage

    async def fake_capture(self, url):
        return WebCapturedPage(
            raw_bytes=b"<html><body><h1>Industry Report</h1><p>East revenue grew 12%.</p></body></html>",
            content_text="Industry Report\n\nEast revenue grew 12%.",
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
            "name": "Public industry page",
            "source_url": "https://example.com/report",
        },
    )
    assert created.status_code == 201
    resource = created.json()["data"]

    overview = await test_client.get("/api/sources/overview")
    assert overview.status_code == 200
    payload = overview.json()["data"]
    assert payload["total"] == 1
    assert payload["counts_partial"] is True

    item = payload["items"][0]
    assert item["id"] == resource["id"]
    assert item["source_kind"] == "source_resource"
    assert item["family"] == "web"
    assert item["provider"] == "web"
    assert item["resource_type"] == "web"
    assert item["name"] == "Public industry page"
    assert item["status"] == "Ready"
    assert item["attention_state"] == "none"
    assert item["freshness_status"] == "fresh"
    assert item["latest_snapshot_id"] == resource["latest_snapshot_id"]
    assert item["context_index_status"] == "indexed"
    assert item["parse_status"] == "parsed"
    assert item["parsed_asset_counts"]["evidence"] == 2
    assert item["parsed_asset_counts"]["blocks"] == 2
    assert item["consumer_counts"] == {
        "semantic_models": 0,
        "dashboards": 0,
        "notebooks": 0,
        "mcp_tools": 0,
    }
    assert item["visibility"] == "workspace"
    assert item["owner"]["id"]
    assert item["created_at"]
    assert item["updated_at"]
    assert item["counts_partial"] is True

    compatibility = await test_client.get("/api/datasources/overview")
    assert compatibility.status_code == 200
    assert compatibility.json()["data"] == payload


async def test_sources_overview_maps_failed_and_needs_confirmation_to_product_states(test_client):
    failed = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "web",
            "name": "Blocked local page",
            "source_url": "http://127.0.0.1:8080/admin",
        },
    )
    assert failed.status_code == 201

    pending = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "web",
            "name": "Awaiting crawl policy",
        },
    )
    assert pending.status_code == 201

    overview = await test_client.get("/api/sources/overview")
    assert overview.status_code == 200
    items = {item["id"]: item for item in overview.json()["data"]["items"]}

    failed_item = items[failed.json()["data"]["id"]]
    assert failed_item["status"] == "Failed"
    assert failed_item["attention_state"] == "parse"
    assert failed_item["context_index_status"] == "unavailable"
    assert failed_item["parse_status"] == "pending"
    assert failed_item["freshness_status"] == "unknown"

    pending_item = items[pending.json()["data"]["id"]]
    assert pending_item["status"] == "Needs confirmation"
    assert pending_item["attention_state"] == "parse"
    assert pending_item["context_index_status"] == "unavailable"
    assert pending_item["parse_status"] == "pending"


async def test_sources_overview_excludes_deleted_source_resources(test_client, test_session, monkeypatch):
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
        json={"resource_type": "web", "name": "Deleted page", "source_url": "https://example.com/report"},
    )
    assert created.status_code == 201
    resource_id = created.json()["data"]["id"]

    deleted = await test_client.delete(f"/api/source-resources/{resource_id}")
    assert deleted.status_code == 204

    overview = await test_client.get("/api/sources/overview")
    assert overview.status_code == 200
    assert all(item["id"] != resource_id for item in overview.json()["data"]["items"])

    row = await test_session.scalar(select(SourceResource).where(SourceResource.id == resource_id))
    assert row is not None
    assert row.sync_config_json["deletion_marker"]["status"] == "removed"
