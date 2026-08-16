from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from server.models.notebooks import Notebook
from server.models.settings import Setting
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
