from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.dashboard import Dashboard
from server.models.notebooks import Notebook
from server.models.queries import Query
from server.models.tenant import Tenant
from server.models.user import User
from server.routers import folders
from server.schemas.query import BatchExecuteSavedQueriesRequest, QueryWithFilters


async def _seed_dashboard_query_binding_fixture(test_session: AsyncSession) -> dict[str, UUID]:
    owner_id = uuid4()
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    dashboard_notebook_id = uuid4()
    other_notebook_id = uuid4()
    cross_tenant_notebook_id = uuid4()
    dashboard_id = uuid4()
    bound_query_id = uuid4()
    unbound_query_id = uuid4()
    cross_tenant_query_id = uuid4()

    owner = User(
        id=owner_id,
        email="dashboard-security@example.test",
        hashed_password="hash",
        is_active=True,
        is_verified=True,
    )
    test_session.add(owner)
    await test_session.flush()

    test_session.add_all(
        [
            Tenant(id=tenant_id, name="Dashboard Tenant", slug=f"dashboard-{tenant_id}", owner_id=owner_id),
            Tenant(id=other_tenant_id, name="Other Tenant", slug=f"other-{other_tenant_id}", owner_id=owner_id),
        ]
    )
    await test_session.flush()

    test_session.add_all(
        [
            Notebook(
                id=dashboard_notebook_id,
                tenant_id=tenant_id,
                created_by=owner_id,
                notebook_name="Dashboard notebook",
            ),
            Notebook(
                id=other_notebook_id,
                tenant_id=tenant_id,
                created_by=owner_id,
                notebook_name="Same-tenant other notebook",
            ),
            Notebook(
                id=cross_tenant_notebook_id,
                tenant_id=other_tenant_id,
                created_by=owner_id,
                notebook_name="Cross-tenant notebook",
            ),
        ]
    )
    await test_session.flush()

    test_session.add(
        Dashboard(
            id=dashboard_id,
            tenant_id=tenant_id,
            notebook_id=dashboard_notebook_id,
            version_num=1,
            html_content="<html></html>",
        )
    )
    await test_session.flush()

    test_session.add_all(
        [
            Query(
                id=bound_query_id,
                tenant_id=tenant_id,
                created_by=owner_id,
                name="Bound query",
                query="select 1",
                output_schema="[]",
                notebook_id=dashboard_notebook_id,
            ),
            Query(
                id=unbound_query_id,
                tenant_id=tenant_id,
                created_by=owner_id,
                name="Unbound query",
                query="select 2",
                output_schema="[]",
                notebook_id=other_notebook_id,
            ),
            Query(
                id=cross_tenant_query_id,
                tenant_id=other_tenant_id,
                created_by=owner_id,
                name="Cross-tenant query",
                query="select 3",
                output_schema="[]",
                notebook_id=cross_tenant_notebook_id,
            ),
        ]
    )
    await test_session.commit()

    return {
        "dashboard_id": dashboard_id,
        "bound_query_id": bound_query_id,
        "unbound_query_id": unbound_query_id,
        "cross_tenant_query_id": cross_tenant_query_id,
    }


@pytest.mark.asyncio
async def test_viewer_dashboard_binding_accepts_query_from_dashboard_notebook(test_session: AsyncSession) -> None:
    ids = await _seed_dashboard_query_binding_fixture(test_session)

    await folders._require_viewer_dashboard_query_bindings(
        dashboard_id=ids["dashboard_id"],
        request=BatchExecuteSavedQueriesRequest(query_ids=[ids["bound_query_id"]]),
        session=test_session,
    )


@pytest.mark.asyncio
async def test_viewer_dashboard_binding_rejects_query_from_other_notebook(test_session: AsyncSession) -> None:
    ids = await _seed_dashboard_query_binding_fixture(test_session)

    with pytest.raises(HTTPException) as exc:
        await folders._require_viewer_dashboard_query_bindings(
            dashboard_id=ids["dashboard_id"],
            request=BatchExecuteSavedQueriesRequest(query_ids=[ids["unbound_query_id"]]),
            session=test_session,
        )

    assert exc.value.status_code == 403
    assert "not available for this dashboard" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_viewer_dashboard_binding_rejects_cross_tenant_query(test_session: AsyncSession) -> None:
    ids = await _seed_dashboard_query_binding_fixture(test_session)

    with pytest.raises(HTTPException) as exc:
        await folders._require_viewer_dashboard_query_bindings(
            dashboard_id=ids["dashboard_id"],
            request=BatchExecuteSavedQueriesRequest(query_ids=[ids["cross_tenant_query_id"]]),
            session=test_session,
        )

    assert exc.value.status_code == 403
    assert "not available for this dashboard" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_viewer_dashboard_binding_rejects_filtered_query_from_other_notebook(test_session: AsyncSession) -> None:
    ids = await _seed_dashboard_query_binding_fixture(test_session)

    with pytest.raises(HTTPException) as exc:
        await folders._require_viewer_dashboard_query_bindings(
            dashboard_id=ids["dashboard_id"],
            request=BatchExecuteSavedQueriesRequest(
                queries_with_filters=[QueryWithFilters(query_id=ids["unbound_query_id"], filters=[])]
            ),
            session=test_session,
        )

    assert exc.value.status_code == 403
    assert "not available for this dashboard" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_viewer_dashboard_batch_rejects_unbound_query_before_execution(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = await _seed_dashboard_query_binding_fixture(test_session)
    viewer_user_id = uuid4()
    executed = False

    async def fake_require_viewer_session(_dashboard_id, _viewer_session):
        return viewer_user_id

    async def fake_can_access_dashboard_via_folder(**_kwargs):
        return True

    async def fake_execute_batch_saved_queries(**_kwargs):
        nonlocal executed
        executed = True
        return {
            "success": True,
            "message": "All queries executed successfully",
            "data": [],
            "partial_success": False,
            "total_queries": 1,
            "successful_queries": 1,
            "failed_queries": 0,
            "total_execution_time_ms": 0.0,
        }

    monkeypatch.setattr(folders, "_require_viewer_session", fake_require_viewer_session)
    monkeypatch.setattr(folders.FolderService, "can_access_dashboard_via_folder", fake_can_access_dashboard_via_folder)
    monkeypatch.setattr(folders.QueryService, "execute_batch_saved_queries", fake_execute_batch_saved_queries)

    with pytest.raises(HTTPException) as exc:
        await folders.execute_viewer_dashboard_queries(
            dashboard_id=ids["dashboard_id"],
            request=BatchExecuteSavedQueriesRequest(query_ids=[ids["unbound_query_id"]]),
            session=test_session,
            viewer_session="viewer-session",
            origin="https://app.example.test",
        )

    assert exc.value.status_code == 403
    assert executed is False
