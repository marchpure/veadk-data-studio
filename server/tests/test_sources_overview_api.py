from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select

from server.models.connections import Connection
from server.models.datasets import Dataset
from server.models.notebook_assets import NotebookAsset
from server.models.notebooks import Notebook
from server.models.semantic_models import SemanticModel
from server.models.source_connections import SourceConnection
from server.models.source_resources import SourceResource
from server.models.tenant import Tenant

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
    assert item["next_actions"] == ["Search evidence", "Attach to notebook"]

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
    assert pending_item["next_actions"] == ["Confirm resource selection"]


async def test_sources_overview_promotes_feishu_reauthorization_to_next_action(test_client, test_session):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None

    connection = SourceConnection(
        tenant_id=tenant.id,
        provider="feishu",
        auth_mode="oauth",
        encrypted_credentials="{}",
        external_account_id="ou_stale",
        display_name="Feishu workspace",
        status="reauthorization_required",
        capabilities_json={},
        created_by=tenant.owner_id,
    )
    test_session.add(connection)
    await test_session.flush()
    resource = SourceResource(
        tenant_id=tenant.id,
        source_connection_id=connection.id,
        resource_type="feishu_doc",
        name="Stale Feishu doc",
        external_id="docx_stale",
        source_url="https://example.feishu.cn/docx/docx_stale",
        owner_id=tenant.owner_id,
        visibility="workspace",
        status="ready",
    )
    test_session.add(resource)
    await test_session.commit()

    overview = await test_client.get("/api/sources/overview")
    assert overview.status_code == 200
    item = next(item for item in overview.json()["data"]["items"] if item["id"] == str(resource.id))

    assert item["provider"] == "feishu"
    assert item["connection_id"] == str(connection.id)
    assert item["status"] == "Reauthorization required"
    assert item["attention_state"] == "auth"
    assert item["freshness_status"] == "unknown"
    assert item["next_actions"] == ["Reauthorize source"]


async def test_sources_overview_marks_resources_after_connection_disconnect(test_client, test_session):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None

    connection = SourceConnection(
        tenant_id=tenant.id,
        provider="feishu",
        auth_mode="oauth",
        encrypted_credentials="{}",
        external_account_id="ou_disconnect",
        display_name="Feishu workspace",
        status="connected",
        capabilities_json={},
        created_by=tenant.owner_id,
    )
    test_session.add(connection)
    await test_session.flush()
    resource = SourceResource(
        tenant_id=tenant.id,
        source_connection_id=connection.id,
        resource_type="feishu_doc",
        name="Disconnected Feishu doc",
        external_id="docx_disconnect",
        source_url="https://example.feishu.cn/docx/docx_disconnect",
        owner_id=tenant.owner_id,
        visibility="workspace",
        status="ready",
    )
    test_session.add(resource)
    await test_session.commit()

    disconnected = await test_client.delete(f"/api/source-connections/{connection.id}")
    assert disconnected.status_code == 200
    assert disconnected.json()["data"]["affected_resource_count"] == 1

    overview = await test_client.get("/api/sources/overview")
    assert overview.status_code == 200
    item = next(item for item in overview.json()["data"]["items"] if item["id"] == str(resource.id))

    assert item["provider"] == "feishu"
    assert item["connection_id"] == str(connection.id)
    assert item["status"] == "Authorization required"
    assert item["attention_state"] == "auth"
    assert item["freshness_status"] == "unknown"
    assert item["next_actions"] == ["Reauthorize source"]


async def test_sources_overview_next_actions_cover_warehouse_and_object_storage_contracts(test_client, test_session):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None

    connection = Connection(
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        type="databricks",
        name="Databricks Revenue Lakehouse",
        connection_obj_encrypted=json.dumps(
            {
                "server_hostname": "adb.example.databricks.com",
                "http_path": "/sql/1.0/warehouses/wh_1",
            }
        ),
        schema_cache=json.dumps({"schema": {"gold.orders": {"columns": [{"name": "order_id", "type": "STRING"}]}}}),
        schema_updated_at=datetime.utcnow(),
        is_public=True,
    )
    test_session.add(connection)
    await test_session.flush()
    test_session.add(
        Dataset(
            tenant_id=tenant.id,
            created_by=tenant.owner_id,
            type="connection",
            name="Databricks Revenue Lakehouse",
            connection_id=connection.id,
            is_public=True,
        )
    )
    await test_session.commit()

    tos = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "tos_object",
            "name": "monthly-targets.csv",
            "external_id": "sales/monthly-targets.csv",
            "metadata": {
                "projected_dataset": {
                    "files": [{"filename": "monthly-targets.csv", "status": "available"}],
                    "schema_tables": [{"name": "monthly_targets", "row_count": 2, "column_count": 3}],
                },
                "parser_warnings": ["header row inferred"],
            },
            "content": "channel,target\nEast,120\n",
            "external_revision": "etag-tos-1",
        },
    )
    assert tos.status_code == 201

    overview = await test_client.get("/api/sources/overview")
    assert overview.status_code == 200
    items = overview.json()["data"]["items"]

    databricks_item = next(item for item in items if item["provider"] == "databricks")
    assert databricks_item["source_kind"] == "connection"
    assert databricks_item["connection_id"] == str(connection.id)
    assert databricks_item["family"] == "warehouses"
    assert databricks_item["parsed_asset_counts"]["tables"] == 1
    assert databricks_item["next_actions"] == ["Generate semantic model", "Open warehouse catalog"]

    tos_item = next(item for item in items if item["id"] == tos.json()["data"]["id"])
    assert tos_item["source_kind"] == "source_resource"
    assert tos_item["family"] == "object_storage"
    assert tos_item["provider"] == "volcengine_tos"
    assert tos_item["next_actions"] == ["Search evidence", "Review projection"]


async def test_sources_overview_object_storage_confirmation_uses_large_object_action(test_client, test_session):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None

    resource = SourceResource(
        tenant_id=tenant.id,
        resource_type="tos_object",
        name="huge-export.parquet",
        external_id="sales-bucket/raw/huge-export.parquet",
        owner_id=tenant.owner_id,
        visibility="workspace",
        sync_mode="manual",
        status="needs_confirmation",
        sync_config_json={
            "last_error": {
                "code": "large_file_confirmation_required",
                "message": "TOS object is too large; confirmation required",
                "permanent": True,
            }
        },
    )
    test_session.add(resource)
    await test_session.commit()

    overview = await test_client.get("/api/sources/overview")
    assert overview.status_code == 200
    item = next(item for item in overview.json()["data"]["items"] if item["id"] == str(resource.id))
    assert item["family"] == "object_storage"
    assert item["provider"] == "volcengine_tos"
    assert item["status"] == "Needs confirmation"
    assert item["attention_state"] == "parse"
    assert item["context_index_status"] == "unavailable"
    assert item["next_actions"] == ["Review object size", "Confirm large object sync"]


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


async def test_sources_overview_counts_semantic_and_notebook_consumers(test_client, test_session):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None

    created = await test_client.post(
        "/api/source-resources",
        json={
            "resource_type": "feishu_doc",
            "name": "Operating rules",
            "external_id": "docx_rules",
            "source_url": "https://example.feishu.cn/docx/docx_rules",
            "content": "Revenue = paid order net amount.\n\nRetention risk if no repeat purchase in 30 days.",
            "external_revision": "rev-1",
        },
    )
    assert created.status_code == 201
    resource = created.json()["data"]
    knowledge_id = resource["knowledge_resource"]["id"]

    notebook = Notebook(
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        notebook_name="Consumer notebook",
        description="Checks source consumer counts",
    )
    test_session.add(notebook)
    await test_session.flush()
    test_session.add(
        NotebookAsset(
            tenant_id=tenant.id,
            notebook_id=notebook.id,
            asset_type="knowledge_resource",
            asset_id=knowledge_id,
            added_by=tenant.owner_id,
            usage_policy_json={"purpose": "evidence"},
        )
    )
    test_session.add(
        SemanticModel(
            tenant_id=tenant.id,
            created_by=tenant.owner_id,
            slug="rules-semantic",
            name="Rules Semantic",
            domain="Operations",
            owner="Ops",
            datasource_id=resource["id"],
            datasource_name="Operating rules",
            datasource_kind="feishu_doc",
            status="Draft",
        )
    )
    await test_session.commit()

    overview = await test_client.get("/api/sources/overview")
    assert overview.status_code == 200
    item = next(item for item in overview.json()["data"]["items"] if item["id"] == resource["id"])

    assert item["consumer_counts"]["semantic_models"] == 1
    assert item["consumer_counts"]["notebooks"] == 1
    assert item["consumer_counts"]["dashboards"] == 0
    assert item["counts_partial"] is True
