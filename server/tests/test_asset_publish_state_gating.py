from __future__ import annotations

import pytest

from server.tests.asset_helpers import current_tenant, seed_dashboard_asset

pytestmark = pytest.mark.asyncio


async def test_draft_dashboard_is_searchable_but_not_externally_consumable(test_client, test_session) -> None:
    tenant = await current_tenant(test_session)
    dashboard = await seed_dashboard_asset(test_session, tenant, slug="draft-sales-dashboard", publish=False)

    search = await test_client.post(
        "/api/assets/search",
        json={"asset_types": ["dashboard"], "query": "sales dashboard", "limit": 10},
    )

    assert search.status_code == 200
    item = next(asset for asset in search.json()["data"]["items"] if asset["asset_id"] == str(dashboard.id))
    assert item["publish_state"] == "draft"
    assert item["capabilities"] == {}
    assert item["usage_policy"]["external"] is False


async def test_published_dashboard_has_gate_and_capabilities(test_client, test_session) -> None:
    tenant = await current_tenant(test_session)
    dashboard = await seed_dashboard_asset(test_session, tenant, slug="published-gated-dashboard", publish=True)

    describe = await test_client.post(
        "/api/assets/describe",
        json={"asset_type": "dashboard", "asset_id": str(dashboard.id)},
    )

    assert describe.status_code == 200
    payload = describe.json()["data"]
    assert payload["publish_state"] == "published"
    assert payload["gate"]["score"] == 100
    assert payload["gate"]["blockers"] == []
    assert payload["version"] == "v1"
    assert payload["capabilities"]["metrics"]
    assert payload["usage_policy"]["external"] is True


async def test_asset_search_filters_publish_states(test_client, test_session) -> None:
    tenant = await current_tenant(test_session)
    published = await seed_dashboard_asset(test_session, tenant, slug="published-filter-dashboard", publish=True)
    draft = await seed_dashboard_asset(test_session, tenant, slug="draft-filter-dashboard", publish=False)

    published_search = await test_client.post(
        "/api/assets/search",
        json={"asset_types": ["dashboard"], "publish_states": ["published"], "limit": 10},
    )
    draft_search = await test_client.post(
        "/api/assets/search",
        json={"asset_types": ["dashboard"], "publish_states": ["draft"], "limit": 10},
    )

    assert published_search.status_code == 200
    assert {item["asset_id"] for item in published_search.json()["data"]["items"]} == {str(published.id)}
    assert draft_search.status_code == 200
    assert {item["asset_id"] for item in draft_search.json()["data"]["items"]} == {str(draft.id)}
