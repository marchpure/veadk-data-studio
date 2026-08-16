from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.dashboard import Dashboard, DashboardAsset
from server.models.folder import Folder
from server.models.folder_dashboard import FolderDashboard
from server.models.folder_member import FolderMember
from server.models.notebooks import Notebook
from server.models.queries import Query
from server.models.sharing import SharingCompatibilityLink, SharingGrant, SharingViewerSession
from server.models.tenant import Tenant
from server.models.user import User
from server.routers import folders
from server.schemas.query import BatchExecuteSavedQueriesRequest, QueryWithFilters
from server.services.sharing import SharingService
from server.services.viewer_session_service import ViewerSessionService


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

    async def fake_require_viewer_session(_dashboard_id, _viewer_session, _session):
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


@pytest.mark.asyncio
async def test_viewer_session_token_binds_to_grant_asset_version_and_registered_claims() -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    grant_id = uuid4()
    asset_id = uuid4()
    dashboard_id = uuid4()

    token = ViewerSessionService.generate_token(
        user_id=user_id,
        tenant_id=tenant_id,
        grant_id=grant_id,
        asset_id=asset_id,
        version_id=dashboard_id,
    )

    payload = ViewerSessionService.verify(token)
    assert payload is not None
    assert payload["iss"] == "byaan-api"
    assert payload["aud"] == "byaan-viewer"
    assert payload["uid"] == str(user_id)
    assert payload["tid"] == str(tenant_id)
    assert payload["grant_id"] == str(grant_id)
    assert payload["asset_id"] == str(asset_id)
    assert payload["version_id"] == str(dashboard_id)
    assert isinstance(payload["jti"], str) and payload["jti"]
    assert payload["iat"] <= payload["nbf"] <= payload["exp"]


@pytest.mark.asyncio
async def test_viewer_session_rejects_token_for_different_dashboard(test_session: AsyncSession) -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    dashboard_id = uuid4()
    other_dashboard_id = uuid4()
    asset_id = uuid4()
    folder_id = uuid4()
    grant_id = uuid4()

    user = User(
        id=user_id,
        email="viewer-session@example.test",
        hashed_password="hash",
        is_active=True,
        is_verified=True,
    )
    test_session.add(user)
    await test_session.flush()
    test_session.add(Tenant(id=tenant_id, name="Viewer Session Tenant", slug=f"viewer-{tenant_id}", owner_id=user_id))
    await test_session.flush()
    test_session.add(Folder(id=folder_id, tenant_id=tenant_id, created_by=user_id, name="Shared dashboards"))
    test_session.add(
        Notebook(
            id=uuid4(),
            tenant_id=tenant_id,
            created_by=user_id,
            notebook_name="Viewer notebook",
        )
    )
    await test_session.flush()
    notebook = (await test_session.execute(select(Notebook).where(Notebook.tenant_id == tenant_id))).scalars().first()
    assert notebook is not None
    test_session.add(
        DashboardAsset(
            id=asset_id,
            tenant_id=tenant_id,
            notebook_id=notebook.id,
            slug="viewer-session-dashboard",
            name="Viewer Session Dashboard",
            owner_id=user_id,
        )
    )
    test_session.add(FolderMember(folder_id=folder_id, user_id=user_id, added_by=user_id))
    await test_session.flush()
    test_session.add_all(
        [
            Dashboard(
                id=dashboard_id,
                tenant_id=tenant_id,
                notebook_id=notebook.id,
                asset_id=asset_id,
                version_num=1,
                html_content="<html></html>",
            ),
            Dashboard(
                id=other_dashboard_id,
                tenant_id=tenant_id,
                notebook_id=notebook.id,
                asset_id=asset_id,
                version_num=2,
                html_content="<html></html>",
            ),
            FolderDashboard(
                id=grant_id,
                folder_id=folder_id,
                dashboard_id=dashboard_id,
                shared_by=user_id,
            ),
        ]
    )
    await test_session.commit()

    token = ViewerSessionService.generate_token(
        user_id=user_id,
        tenant_id=tenant_id,
        grant_id=grant_id,
        asset_id=asset_id,
        version_id=dashboard_id,
    )

    assert await folders._require_viewer_session(dashboard_id, token, test_session) == user_id
    with pytest.raises(HTTPException) as exc:
        await folders._require_viewer_session(other_dashboard_id, token, test_session)

    assert exc.value.status_code == 403
    assert "viewer session is not valid for this dashboard" in str(exc.value.detail)

    grant = await test_session.get(FolderDashboard, grant_id)
    assert grant is not None
    await test_session.delete(grant)
    await test_session.commit()

    with pytest.raises(HTTPException) as revoked_exc:
        await folders._require_viewer_session(dashboard_id, token, test_session)

    assert revoked_exc.value.status_code == 403
    assert "viewer session grant has been revoked or rotated" in str(revoked_exc.value.detail)


@pytest.mark.asyncio
async def test_viewer_session_accepts_canonical_folder_dashboard_grant_and_rejects_revoked_legacy(
    test_session: AsyncSession,
) -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    dashboard_id = uuid4()
    asset_id = uuid4()
    folder_id = uuid4()
    legacy_grant_id = uuid4()

    user = User(
        id=user_id,
        email="canonical-viewer-session@example.test",
        hashed_password="hash",
        is_active=True,
        is_verified=True,
    )
    test_session.add(user)
    await test_session.flush()
    test_session.add(Tenant(id=tenant_id, name="Canonical Viewer Tenant", slug=f"canonical-{tenant_id}", owner_id=user_id))
    await test_session.flush()
    test_session.add(Folder(id=folder_id, tenant_id=tenant_id, created_by=user_id, name="Canonical shared dashboards"))
    notebook = Notebook(
        id=uuid4(),
        tenant_id=tenant_id,
        created_by=user_id,
        notebook_name="Canonical viewer notebook",
    )
    test_session.add(notebook)
    await test_session.flush()
    test_session.add(
        DashboardAsset(
            id=asset_id,
            tenant_id=tenant_id,
            notebook_id=notebook.id,
            slug="canonical-viewer-session-dashboard",
            name="Canonical Viewer Session Dashboard",
            owner_id=user_id,
        )
    )
    test_session.add(FolderMember(folder_id=folder_id, user_id=user_id, added_by=user_id))
    await test_session.flush()
    test_session.add_all(
        [
            Dashboard(
                id=dashboard_id,
                tenant_id=tenant_id,
                notebook_id=notebook.id,
                asset_id=asset_id,
                version_num=1,
                html_content="<html></html>",
            ),
            FolderDashboard(
                id=legacy_grant_id,
                folder_id=folder_id,
                dashboard_id=dashboard_id,
                shared_by=user_id,
            ),
        ]
    )
    await test_session.commit()

    canonical_grant = await SharingService(test_session).ensure_folder_dashboard_grant(
        tenant_id=tenant_id,
        actor_id=user_id,
        folder_dashboard_id=legacy_grant_id,
        dashboard_id=dashboard_id,
    )
    token, viewer_session = await SharingService(test_session).issue_viewer_session_for_grant(
        grant=canonical_grant,
        viewer_user_id=user_id,
    )

    assert await folders._require_viewer_session(dashboard_id, token, test_session) == user_id
    assert (
        await test_session.execute(
            select(SharingCompatibilityLink).where(SharingCompatibilityLink.legacy_id == str(legacy_grant_id))
        )
    ).scalar_one()
    assert await test_session.get(SharingGrant, canonical_grant.id) is not None
    assert await test_session.get(SharingViewerSession, viewer_session.id) is not None

    legacy_grant = await test_session.get(FolderDashboard, legacy_grant_id)
    assert legacy_grant is not None
    await test_session.delete(legacy_grant)
    await test_session.commit()

    with pytest.raises(HTTPException) as revoked_exc:
        await folders._require_viewer_session(dashboard_id, token, test_session)

    assert revoked_exc.value.status_code == 403
    assert "viewer session grant has been revoked or rotated" in str(revoked_exc.value.detail)
