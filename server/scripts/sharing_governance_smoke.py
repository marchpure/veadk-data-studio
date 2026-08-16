from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

os.environ.setdefault("BYAAN_LOCAL_AUTH_IMPERSONATION_ENABLED", "true")

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.db.base import Base
from server.db.session import get_async_session
from server.main import app
from server.models.dashboard import Dashboard
from server.models.folder import Folder
from server.models.folder_member import FolderMember
from server.models.notebooks import Notebook
from server.models.settings import Setting
from server.models.tenant import Tenant
from server.models.tenant_member import TenantMember, TenantRole
from server.models.user import User
from server.routers import exports as exports_router
from server.schemas.notebook_export import NotebookExport
from server.services import folder_service as folder_service_module

FORBIDDEN = (
    "html-password",
    "json-password",
    "rotated-json-password",
    "raw-share-token",
    "raw-verifier",
    "raw-salt",
    "restricted_table",
)


class _FakeWorkerResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeWorkerClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url: str, *, json: dict[str, Any], **_kwargs) -> _FakeWorkerResponse:
        if url.endswith("/api/html"):
            return _FakeWorkerResponse(
                200,
                {
                    "id": json["id"],
                    "is_new": True,
                    "has_password": bool(json.get("password")),
                    "token": "raw-share-token",
                    "verifier": "raw-verifier",
                },
            )
        if url.endswith("/api/notebook"):
            return _FakeWorkerResponse(
                200,
                {
                    "id": "sharing-smoke-json-share",
                    "has_password": bool(json.get("password")),
                    "raw_token": "raw-share-token",
                    "verifier": "raw-verifier",
                },
            )
        return _FakeWorkerResponse(404, {"error": "unknown fake worker route"})

    async def get(self, url: str, **_kwargs) -> _FakeWorkerResponse:
        if "/api/html/" in url:
            return _FakeWorkerResponse(
                200,
                {
                    "created_at": "2026-08-16T00:00:00Z",
                    "updated_at": "2026-08-16T00:00:00Z",
                    "has_password": True,
                    "password": "html-password",
                    "token": "raw-share-token",
                },
            )
        if "/api/notebook/list/" in url:
            return _FakeWorkerResponse(
                200,
                {
                    "shares": [
                        {
                            "id": "sharing-smoke-json-share",
                            "created_at": "2026-08-16T00:00:00Z",
                            "has_password": True,
                            "password": "json-password",
                            "raw_token": "raw-share-token",
                        }
                    ]
                },
            )
        return _FakeWorkerResponse(404, {"error": "unknown fake worker route"})

    async def put(self, url: str, *, json: dict[str, Any], **_kwargs) -> _FakeWorkerResponse:
        if "/api/notebook/" in url:
            return _FakeWorkerResponse(
                200,
                {"success": True, "has_password": bool(json.get("password")), "token": "raw-share-token"},
            )
        return _FakeWorkerResponse(404, {"error": "unknown fake worker route"})

    async def delete(self, url: str, **_kwargs) -> _FakeWorkerResponse:
        if "/api/html/" in url or "/api/notebook/" in url:
            return _FakeWorkerResponse(200, {"success": True})
        return _FakeWorkerResponse(404, {"error": "unknown fake worker route"})


def _assert_redacted(payload: object, operation: str) -> None:
    serialized = json.dumps(payload, default=str)
    leaked = [value for value in FORBIDDEN if value in serialized]
    if leaked:
        raise AssertionError(f"{operation} leaked sensitive values: {leaked}")


def _success(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    if payload.get("success") is not True:
        raise AssertionError(f"{operation} failed: {payload}")
    _assert_redacted(payload, operation)
    return payload.get("data") or {}


async def _seed(session: AsyncSession) -> dict[str, str]:
    owner = User(
        id=uuid4(),
        email=f"sharing-smoke-{uuid4().hex[:8]}@example.test",
        hashed_password="fakehash",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    session.add(owner)
    await session.flush()
    tenant = Tenant(
        id=uuid4(),
        name="Sharing governance smoke",
        slug=f"sharing-smoke-{uuid4().hex[:8]}",
        owner_id=owner.id,
        is_personal=True,
    )
    session.add(tenant)
    await session.flush()
    notebook = Notebook(
        id=uuid4(),
        tenant_id=tenant.id,
        created_by=owner.id,
        notebook_name="Sharing governance smoke notebook",
        description="Covers canonical sharing compatibility",
    )
    folder = Folder(
        id=uuid4(),
        tenant_id=tenant.id,
        created_by=owner.id,
        name="Sharing governance smoke folder",
        is_public=False,
    )
    session.add_all(
        [
            TenantMember(user_id=owner.id, tenant_id=tenant.id, role=TenantRole.OWNER.value),
            notebook,
            folder,
            FolderMember(folder_id=folder.id, user_id=owner.id, added_by=owner.id),
            Setting(
                tenant_id=tenant.id,
                user_id=None,
                setting_key="api_key",
                setting_value="worker-api-key",
                is_encrypted=False,
            ),
        ]
    )
    await session.flush()
    dashboard = Dashboard(
        id=uuid4(),
        tenant_id=tenant.id,
        notebook_id=notebook.id,
        version_num=1,
        html_content="<html><body>sharing smoke</body></html>",
        content_hash="sha256:sharing-smoke-dashboard",
        status="published",
        created_by=owner.id,
        actor_type="human",
        is_published_immutable=True,
    )
    session.add(dashboard)
    await session.commit()
    return {
        "tenant_id": str(tenant.id),
        "user_id": str(owner.id),
        "notebook_id": str(notebook.id),
        "folder_id": str(folder.id),
        "dashboard_id": str(dashboard.id),
    }


def _patch_runtime() -> dict[str, Any]:
    originals = {
        "is_feature_enabled": exports_router.is_feature_enabled,
        "get_waitlist_config": exports_router.get_waitlist_config,
        "AsyncClient": exports_router.httpx.AsyncClient,
        "generate_compiled_html": exports_router.CompiledHtmlExportService.generate_compiled_html,
        "export_notebook": exports_router.NotebookExportService.export_notebook,
        "warm_dashboard_cache_background": folder_service_module._warm_dashboard_cache_background,
    }

    async def fake_generate_compiled_html(**_kwargs) -> str:
        return "<html><body>compiled sharing smoke</body></html>"

    async def fake_export_notebook(*_args, **_kwargs) -> NotebookExport:
        return NotebookExport(
            id="sharing-smoke-notebook",
            title="Sharing smoke notebook",
            description="Sharing governance smoke export",
            chat_history=[],
            dashboards=[],
            datasets=[],
            exported_at="2026-08-16T00:00:00Z",
        )

    async def fake_warm_dashboard_cache_background(*_args, **_kwargs) -> None:
        return None

    exports_router.is_feature_enabled = lambda feature: feature == "external_sharing_enabled"
    exports_router.get_waitlist_config = lambda: {"worker_url": "https://worker.test"}
    exports_router.httpx.AsyncClient = _FakeWorkerClient
    exports_router.CompiledHtmlExportService.generate_compiled_html = fake_generate_compiled_html
    exports_router.NotebookExportService.export_notebook = fake_export_notebook
    folder_service_module._warm_dashboard_cache_background = fake_warm_dashboard_cache_background
    return originals


def _restore_runtime(originals: dict[str, Any]) -> None:
    exports_router.is_feature_enabled = originals["is_feature_enabled"]
    exports_router.get_waitlist_config = originals["get_waitlist_config"]
    exports_router.httpx.AsyncClient = originals["AsyncClient"]
    exports_router.CompiledHtmlExportService.generate_compiled_html = originals["generate_compiled_html"]
    exports_router.NotebookExportService.export_notebook = originals["export_notebook"]
    folder_service_module._warm_dashboard_cache_background = originals["warm_dashboard_cache_background"]


@asynccontextmanager
async def _client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_async_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = override_get_async_session
    originals = _patch_runtime()
    try:
        async with session_factory() as session:
            fixture = await _seed(session)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://sharing-smoke",
            headers={"X-Tenant-ID": fixture["tenant_id"], "X-Local-User-ID": fixture["user_id"]},
        ) as client:
            yield client, fixture
    finally:
        _restore_runtime(originals)
        app.dependency_overrides.clear()
        await engine.dispose()


async def _api(client: AsyncClient, method: str, path: str, **kwargs) -> dict[str, Any]:
    response = await client.request(method, path, **kwargs)
    payload = response.json() if response.content else {"success": response.status_code < 400}
    if response.status_code >= 400:
        raise AssertionError(f"{method} {path} failed {response.status_code}: {payload}")
    _assert_redacted(payload, f"{method} {path}")
    return payload


async def main() -> None:
    async with _client() as (client, fixture):
        notebook_id = fixture["notebook_id"]
        folder_id = fixture["folder_id"]
        dashboard_id = fixture["dashboard_id"]

        folder_notebook = _success(
            await _api(
                client,
                "POST",
                f"/api/folders/{folder_id}/notebooks",
                json={"notebook_id": notebook_id, "is_snapshot": True},
            ),
            "folder notebook share",
        )
        folder_dashboard = _success(
            await _api(
                client,
                "POST",
                f"/api/folders/{folder_id}/dashboards",
                json={"dashboard_id": dashboard_id, "is_snapshot": False},
            ),
            "folder dashboard share",
        )
        html_share = _success(
            await _api(client, "POST", f"/api/notebooks/{notebook_id}/share?password=html-password"),
            "html notebook share",
        )
        json_share = _success(
            await _api(
                client,
                "POST",
                f"/api/notebooks/{notebook_id}/share/notebook",
                json={"password": "json-password"},
            ),
            "json notebook share",
        )
        rotated = _success(
            await _api(
                client,
                "PUT",
                f"/api/notebooks/{notebook_id}/shares/notebook/{json_share['share_id']}/password?password=rotated-json-password",
            ),
            "json notebook password rotation",
        )
        html_readback = _success(
            await _api(client, "GET", f"/api/notebooks/{notebook_id}/share"),
            "html share readback",
        )
        json_readback = _success(
            await _api(client, "GET", f"/api/notebooks/{notebook_id}/shares/notebook"),
            "json share readback",
        )

        grants = _success(await _api(client, "GET", "/api/sharing/grants?object_type=notebook"), "sharing grants")
        surfaces = {
            link["legacy_surface"]
            for grant in grants["items"]
            for link in _success(
                await _api(client, "GET", f"/api/sharing/grants/{grant['id']}"),
                f"sharing evidence {grant['id']}",
            )["compatibility_links"]
        }
        expected_surfaces = {"folder_notebook", "html_notebook_share", "json_notebook_share"}
        if not expected_surfaces.issubset(surfaces):
            raise AssertionError(f"missing canonical notebook surfaces: {expected_surfaces - surfaces}")

        dashboard_grants = _success(
            await _api(client, "GET", "/api/sharing/grants?object_type=dashboard"),
            "dashboard sharing grants",
        )
        if not any(item["channel"] == "folder" for item in dashboard_grants["items"]):
            raise AssertionError("folder dashboard canonical grant was not listed")

        await _api(client, "DELETE", f"/api/folders/{folder_id}/notebooks/{notebook_id}")
        await _api(client, "DELETE", f"/api/notebooks/{notebook_id}/share")
        await _api(client, "DELETE", f"/api/notebooks/{notebook_id}/shares/notebook/{json_share['share_id']}")
        revoked = _success(await _api(client, "GET", "/api/sharing/grants?object_type=notebook"), "revoked grants")
        revoked_by_surface = {
            evidence["compatibility_links"][0]["legacy_surface"]: evidence["grant"]["status"]
            for evidence in [
                _success(
                    await _api(client, "GET", f"/api/sharing/grants/{grant['id']}"),
                    f"revoked evidence {grant['id']}",
                )
                for grant in revoked["items"]
            ]
        }
        for surface in expected_surfaces:
            if revoked_by_surface.get(surface) != "revoked":
                raise AssertionError(f"{surface} grant was not revoked: {revoked_by_surface.get(surface)}")

        result = {
            "ok": True,
            "tenant_id": fixture["tenant_id"],
            "folder_notebook_share_id": folder_notebook["id"],
            "folder_dashboard_share_id": folder_dashboard["id"],
            "html_share_id": html_share["share_id"],
            "json_share_id": json_share["share_id"],
            "json_has_password_after_rotation": rotated["has_password"],
            "html_readback_has_password": html_readback["share"]["has_password"],
            "json_readback_count": len(json_readback["shares"]),
            "canonical_notebook_surfaces": sorted(surfaces),
            "canonical_dashboard_grant_count": dashboard_grants["total"],
            "revoked_notebook_surface_statuses": revoked_by_surface,
        }
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
