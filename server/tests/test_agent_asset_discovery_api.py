from __future__ import annotations

import pytest

from server.tests.asset_helpers import current_tenant, seed_dashboard_asset

pytestmark = pytest.mark.asyncio


async def test_asset_search_and_describe_support_dashboard(test_client, test_session) -> None:
    tenant = await current_tenant(test_session)
    dashboard = await seed_dashboard_asset(test_session, tenant, slug="published-sales-dashboard", publish=True)

    search = await test_client.post(
        "/api/assets/search",
        json={"asset_types": ["dashboard"], "query": "paid revenue", "limit": 10},
    )

    assert search.status_code == 200
    items = search.json()["data"]["items"]
    assert len(items) == 1
    item = items[0]
    assert item["asset_type"] == "dashboard"
    assert item["asset_id"] == str(dashboard.id)
    assert item["publish_state"] == "published"
    assert item["gate"]["score"] == 100
    assert item["capabilities"]["execution_modes"] == ["query_dashboard"]
    assert item["capabilities"]["metrics"][0]["id"] == "paid_revenue"

    describe = await test_client.post(
        "/api/assets/describe",
        json={"asset_type": "dashboard", "asset_id": str(dashboard.id)},
    )

    assert describe.status_code == 200
    payload = describe.json()["data"]
    assert payload["asset_type"] == "dashboard"
    assert payload["publish_state"] == "published"
    assert payload["capabilities"]["default_time_field"] == "paid_at"
    assert payload["capabilities"]["access_policy"]["required_scopes"] == ["dashboard:read", "dashboard:query"]
    assert payload["provenance"]["dashboard_slug"] == "published-sales-dashboard"
    assert {evidence["kind"] for evidence in payload["sample_evidence"]} >= {
        "sql",
        "document_section",
        "permission_policy",
    }
