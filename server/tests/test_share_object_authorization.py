from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from server.models.dashboard import Dashboard
from server.models.folder import Folder
from server.models.folder_dashboard import FolderDashboard
from server.models.folder_member import FolderMember
from server.models.folder_notebook import FolderNotebook
from server.models.notebooks import Notebook
from server.models.settings import Setting
from server.models.sharing import SharingCompatibilityLink, SharingGrant
from server.models.tenant import Tenant
from server.models.tenant_member import TenantMember, TenantRole
from server.models.user import User

pytestmark = pytest.mark.asyncio


async def _seed_member_and_owner_notebook(test_session) -> tuple[str, str]:
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None

    member = User(
        id=uuid4(),
        email="share-member@example.test",
        hashed_password="fakehash",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    notebook = Notebook(
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        notebook_name="Owner notebook",
        description="A notebook the member must not share or export.",
    )
    test_session.add(member)
    await test_session.flush()
    test_session.add(TenantMember(user_id=member.id, tenant_id=tenant.id, role=TenantRole.MEMBER.value))
    test_session.add(notebook)
    test_session.add(
        Setting(
            tenant_id=tenant.id,
            user_id=None,
            setting_key="api_key",
            setting_value="worker-api-key",
            is_encrypted=False,
        )
    )
    await test_session.commit()
    return str(member.id), str(notebook.id)


async def _seed_member_owned_notebook_and_folder(test_session) -> tuple[str, str, str]:
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None

    member = User(
        id=uuid4(),
        email="folder-share-member@example.test",
        hashed_password="fakehash",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    notebook = Notebook(
        tenant_id=tenant.id,
        created_by=member.id,
        notebook_name="Member notebook",
        description="A notebook the member owns but cannot folder-share without dashboard.share.",
    )
    folder = Folder(
        tenant_id=tenant.id,
        created_by=member.id,
        name="Member folder",
        description="Folder share target",
        is_public=False,
    )
    test_session.add(member)
    await test_session.flush()
    test_session.add(TenantMember(user_id=member.id, tenant_id=tenant.id, role=TenantRole.MEMBER.value))
    test_session.add(notebook)
    test_session.add(folder)
    await test_session.flush()
    test_session.add(FolderMember(folder_id=folder.id, user_id=member.id, added_by=member.id))
    await test_session.commit()
    return str(member.id), str(notebook.id), str(folder.id)


async def _seed_member_snapshot_share_for_owner_notebook(test_session) -> tuple[str, str, str]:
    member_id, notebook_id = await _seed_member_and_owner_notebook(test_session)
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    folder = Folder(
        tenant_id=tenant.id,
        created_by=member_id,
        name="Legacy member snapshot folder",
        description="Contains a legacy snapshot row that must still be object-authorized.",
        is_public=False,
    )
    test_session.add(folder)
    await test_session.flush()
    test_session.add(FolderMember(folder_id=folder.id, user_id=member_id, added_by=member_id))
    folder_notebook = FolderNotebook(
        folder_id=folder.id,
        notebook_id=notebook_id,
        shared_by=member_id,
        is_snapshot=True,
        snapshot_data="{}",
    )
    test_session.add(folder_notebook)
    await test_session.commit()
    return member_id, notebook_id, str(folder.id)


async def _seed_member_dashboard_and_folder(test_session) -> tuple[str, str, str]:
    member_id, notebook_id, folder_id = await _seed_member_owned_notebook_and_folder(test_session)
    dashboard = Dashboard(
        tenant_id=(await test_session.execute(select(Tenant))).scalars().first().id,
        notebook_id=notebook_id,
        version_num=1,
        html_content="<html>dashboard</html>",
        created_by=member_id,
    )
    test_session.add(dashboard)
    await test_session.commit()
    return member_id, str(dashboard.id), folder_id


async def _seed_member_folder_dashboard(test_session) -> tuple[str, str, str, str]:
    member_id, dashboard_id, folder_id = await _seed_member_dashboard_and_folder(test_session)
    first_dashboard = await test_session.get(Dashboard, dashboard_id)
    assert first_dashboard is not None
    next_dashboard = Dashboard(
        tenant_id=first_dashboard.tenant_id,
        notebook_id=first_dashboard.notebook_id,
        version_num=2,
        html_content="<html>dashboard v2</html>",
        created_by=first_dashboard.created_by,
    )
    test_session.add(next_dashboard)
    await test_session.flush()
    test_session.add(
        FolderDashboard(
            folder_id=folder_id,
            dashboard_id=dashboard_id,
            shared_by=member_id,
            is_snapshot=False,
        )
    )
    await test_session.commit()
    return member_id, dashboard_id, str(next_dashboard.id), folder_id


async def _seed_owner_notebook_dashboard_and_folder(test_session) -> tuple[str, str, str]:
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    assert tenant is not None
    notebook = Notebook(
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        notebook_name="Owner folder-share notebook",
        description="Owner notebook that should still be shareable.",
    )
    folder = Folder(
        tenant_id=tenant.id,
        created_by=tenant.owner_id,
        name="Owner folder",
        description="Owner folder share target",
        is_public=False,
    )
    test_session.add(notebook)
    test_session.add(folder)
    await test_session.flush()
    dashboard = Dashboard(
        tenant_id=tenant.id,
        notebook_id=notebook.id,
        version_num=1,
        html_content="<html>owner dashboard</html>",
        created_by=tenant.owner_id,
    )
    test_session.add(FolderMember(folder_id=folder.id, user_id=tenant.owner_id, added_by=tenant.owner_id))
    test_session.add(dashboard)
    await test_session.commit()
    return str(notebook.id), str(dashboard.id), str(folder.id)


@pytest.fixture
def sharing_enabled(monkeypatch):
    monkeypatch.setenv("BYAAN_LOCAL_AUTH_IMPERSONATION_ENABLED", "true")
    monkeypatch.setattr("server.routers.exports.is_feature_enabled", lambda feature: feature == "external_sharing_enabled")
    monkeypatch.setattr("server.routers.exports.get_waitlist_config", lambda: {"worker_url": "https://worker.test"})


@pytest.mark.parametrize(
    ("method", "path_template"),
    [
        ("GET", "/api/notebooks/{notebook_id}/export/compiled-html"),
        ("GET", "/api/notebooks/{notebook_id}/export/json"),
        ("POST", "/api/notebooks/{notebook_id}/share"),
        ("GET", "/api/notebooks/{notebook_id}/share"),
        ("DELETE", "/api/notebooks/{notebook_id}/share"),
        ("POST", "/api/notebooks/{notebook_id}/share/notebook"),
        ("GET", "/api/notebooks/{notebook_id}/shares/notebook"),
        ("PUT", "/api/notebooks/{notebook_id}/shares/notebook/json-share-1/password?password=rotated"),
        ("DELETE", "/api/notebooks/{notebook_id}/shares/notebook/json-share-1"),
    ],
)
async def test_member_cannot_export_or_manage_owner_notebook_shares(
    test_client,
    test_session,
    sharing_enabled,
    monkeypatch,
    method,
    path_template,
):
    member_id, notebook_id = await _seed_member_and_owner_notebook(test_session)
    worker_called = False

    async def forbidden_worker_call(*args, **kwargs):
        nonlocal worker_called
        worker_called = True
        raise AssertionError("Object authorization must happen before export or worker calls")

    monkeypatch.setattr(
        "server.routers.exports.CompiledHtmlExportService.generate_compiled_html",
        forbidden_worker_call,
    )
    monkeypatch.setattr("server.routers.exports.NotebookExportService.export_notebook", forbidden_worker_call)

    response = await test_client.request(
        method,
        path_template.format(notebook_id=notebook_id),
        headers={"X-Local-User-ID": member_id},
        json={} if method == "POST" and path_template.endswith("/share/notebook") else None,
    )

    assert response.status_code == 403
    assert worker_called is False


async def test_folder_notebook_share_requires_dashboard_share_scope(
    test_client,
    test_session,
    sharing_enabled,
    monkeypatch,
):
    member_id, notebook_id, folder_id = await _seed_member_owned_notebook_and_folder(test_session)
    export_called = False

    async def forbidden_export(*args, **kwargs):
        nonlocal export_called
        export_called = True
        raise AssertionError("Dashboard share authorization must happen before snapshot export")

    monkeypatch.setattr("server.services.folder_service.NotebookExportService.export_notebook", forbidden_export)

    response = await test_client.post(
        f"/api/folders/{folder_id}/notebooks",
        headers={"X-Local-User-ID": member_id},
        json={"notebook_id": notebook_id, "is_snapshot": True},
    )

    assert response.status_code == 403
    assert export_called is False


async def test_folder_notebook_snapshot_refresh_requires_dashboard_export_scope(
    test_client,
    test_session,
    sharing_enabled,
    monkeypatch,
):
    member_id, notebook_id, folder_id = await _seed_member_snapshot_share_for_owner_notebook(test_session)
    export_called = False

    async def forbidden_export(*args, **kwargs):
        nonlocal export_called
        export_called = True
        raise AssertionError("Dashboard export authorization must happen before snapshot export")

    monkeypatch.setattr("server.services.folder_service.NotebookExportService.export_notebook", forbidden_export)

    response = await test_client.put(
        f"/api/folders/{folder_id}/notebooks/{notebook_id}/snapshot",
        headers={"X-Local-User-ID": member_id},
    )

    assert response.status_code == 403
    assert export_called is False


async def test_folder_dashboard_share_requires_dashboard_share_scope(
    test_client,
    test_session,
    sharing_enabled,
):
    member_id, dashboard_id, folder_id = await _seed_member_dashboard_and_folder(test_session)

    response = await test_client.post(
        f"/api/folders/{folder_id}/dashboards",
        headers={"X-Local-User-ID": member_id},
        json={"dashboard_id": dashboard_id},
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("method", "path_template", "json_body"),
    [
        ("PUT", "/api/folders/{folder_id}/dashboards/{dashboard_id}", {"new_dashboard_id": "{new_dashboard_id}"}),
        ("DELETE", "/api/folders/{folder_id}/dashboards/{dashboard_id}", None),
    ],
)
async def test_folder_dashboard_manage_requires_dashboard_share_scope(
    test_client,
    test_session,
    sharing_enabled,
    method,
    path_template,
    json_body,
):
    member_id, dashboard_id, new_dashboard_id, folder_id = await _seed_member_folder_dashboard(test_session)
    body = None
    if json_body is not None:
        body = {
            key: value.format(new_dashboard_id=new_dashboard_id)
            for key, value in json_body.items()
        }

    response = await test_client.request(
        method,
        path_template.format(folder_id=folder_id, dashboard_id=dashboard_id),
        headers={"X-Local-User-ID": member_id},
        json=body,
    )

    assert response.status_code == 403


async def test_owner_can_folder_share_notebook_and_dashboard_after_dashboard_share_authorization(
    test_client,
    test_session,
    sharing_enabled,
    monkeypatch,
):
    notebook_id, dashboard_id, folder_id = await _seed_owner_notebook_dashboard_and_folder(test_session)

    async def fake_refresh(*args, **kwargs):
        return None

    monkeypatch.setattr("server.services.folder_service._warm_dashboard_cache_background", fake_refresh)

    notebook_response = await test_client.post(
        f"/api/folders/{folder_id}/notebooks",
        json={"notebook_id": notebook_id, "is_snapshot": False},
    )
    dashboard_response = await test_client.post(
        f"/api/folders/{folder_id}/dashboards",
        json={"dashboard_id": dashboard_id},
    )

    assert notebook_response.status_code == 201
    assert dashboard_response.status_code == 201
    folder_dashboard_id = dashboard_response.json()["data"]["id"]
    compatibility = (
        await test_session.execute(
            select(SharingCompatibilityLink).where(
                SharingCompatibilityLink.legacy_surface == "folder_dashboard",
                SharingCompatibilityLink.legacy_id == folder_dashboard_id,
            )
        )
    ).scalar_one()
    grant = await test_session.get(SharingGrant, compatibility.grant_id)
    assert grant is not None
    assert grant.object_type == "dashboard"
    assert str(grant.object_version_id) == dashboard_id
    assert grant.channel == "folder"
    assert grant.audience == "folder_member"
    assert grant.status == "active"
