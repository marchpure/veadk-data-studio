from __future__ import annotations

import io
import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from sqlalchemy import select

from server.auth.tenant_context import set_tenant_id
from server.models.datasets import Dataset
from server.models.files import File
from server.models.knowledge_resources import EvidenceFragment, KnowledgeResource
from server.models.settings import Setting
from server.models.source_connections import FeishuOAuthFlow, SourceConnection
from server.models.source_resources import SourceResource
from server.models.source_snapshots import SourceSnapshot
from server.models.tenant import Tenant
from server.models.tenant_member import TenantMember, TenantRole
from server.models.user import User
from server.schemas.source_connections import SourceConnectionCreate
from server.schemas.source_resources import SourceResourceImportRequest
from server.services.crypto_service import CryptoService
from server.services.file_operations import DataFrameFileService
from server.services.source_connections import SourceConnectionService
from server.services.source_connectors import (
    CapturedSnapshot,
    ConnectorError,
    FeishuAdminConfigService,
    FeishuConnectorAdapter,
    FeishuOAuthStateStore,
    ResourceListInput,
    ResourceListResult,
    ResourcePickerItem,
    TosConnectorAdapter,
    parse_object_bytes,
)
from server.services.source_resources import SourceResourceService

pytestmark = pytest.mark.asyncio


@dataclass
class FakeConnectorAdapter:
    provider: str = "volcengine_tos"
    sync_calls: int = 0

    async def test_connection(self, credentials: dict[str, Any]) -> dict[str, Any]:
        assert credentials["secret_access_key"] == "tos-secret"
        return {
            "account_id": "tos-account-1",
            "bucket_count": 1,
            "endpoint": credentials["endpoint"],
        }

    async def list_resources(self, *, session, input: ResourceListInput) -> ResourceListResult:
        assert input.connection.provider == "volcengine_tos"
        items = [
            ResourcePickerItem(
                external_id="sales-bucket/reports/",
                resource_type="tos_prefix",
                name="reports",
                parent_external_id="sales-bucket",
                has_children=True,
                is_folder=True,
                already_added="sales-bucket/reports/" in input.already_added_external_ids,
                metadata={"bucket": "sales-bucket", "prefix": "reports/"},
            ),
            ResourcePickerItem(
                external_id="sales-bucket/reports/revenue.csv",
                resource_type="tos_object",
                name="revenue.csv",
                parent_external_id="sales-bucket",
                metadata={"bucket": "sales-bucket", "key": "reports/revenue.csv", "etag": "etag-1", "size": 22},
            ),
        ]
        return ResourceListResult(items=items, next_page_token="next-1")

    async def sync_resource(self, *, session, connection: SourceConnection, resource: SourceResource) -> CapturedSnapshot:
        self.sync_calls += 1
        assert connection.id == resource.source_connection_id
        raw = b"region,revenue\nEast,120\nWest,80\n"
        return CapturedSnapshot(
            raw_bytes=raw,
            content_text="| region | revenue |\n| --- | --- |\n| East | 120 |\n| West | 80 |",
            external_revision="etag-1",
            metadata={
                "provider": "volcengine_tos",
                "bucket": "sales-bucket",
                "key": "reports/revenue.csv",
                "version_id": "version-1",
                "etag": "etag-1",
                "region": "cn-beijing",
            },
            provider="byaan-native",
            parser_version="tos-csv-parser-v1",
            raw_storage_uri="tos://sales-bucket/reports/revenue.csv",
        )


@dataclass
class FakeFeishuConnectorAdapter:
    provider: str = "feishu"
    sync_calls: int = 0

    async def test_connection(self, credentials: dict[str, Any]) -> dict[str, Any]:
        return {"account_id": "ou_feishu_1"}

    async def list_resources(self, *, session, input: ResourceListInput) -> ResourceListResult:
        assert input.connection.provider == "feishu"
        items = [
            ResourcePickerItem(
                external_id="docx_token_1",
                resource_type="feishu_doc",
                name="经营规则说明",
                source_url="https://example.feishu.cn/docx/docx_token_1",
                already_added="docx_token_1" in input.already_added_external_ids,
                metadata={"token": "docx_token_1", "type": "docx"},
            ),
            ResourcePickerItem(
                external_id="wiki_node_1",
                resource_type="feishu_wiki",
                name="经营知识库节点",
                source_url="https://example.feishu.cn/wiki/wiki_node_1",
                already_added="wiki_node_1" in input.already_added_external_ids,
                metadata={"node_token": "wiki_node_1", "obj_token": "docx_token_2", "obj_type": "docx"},
            ),
            ResourcePickerItem(
                external_id="sheet_token_1",
                resource_type="feishu_sheet",
                name="经营目标表",
                source_url="https://example.feishu.cn/sheets/sheet_token_1",
                already_added="sheet_token_1" in input.already_added_external_ids,
                metadata={"spreadsheet_token": "sheet_token_1", "sheets": [{"sheet_id": "sh1", "title": "目标"}]},
            ),
            ResourcePickerItem(
                external_id="base_token_1",
                resource_type="feishu_base",
                name="客户线索 Base",
                source_url="https://example.feishu.cn/base/base_token_1",
                already_added="base_token_1" in input.already_added_external_ids,
                metadata={"app_token": "base_token_1", "tables": [{"table_id": "tbl1", "name": "线索"}]},
            ),
        ]
        return ResourceListResult(items=items, next_page_token=None)

    async def sync_resource(self, *, session, connection: SourceConnection, resource: SourceResource) -> CapturedSnapshot:
        self.sync_calls += 1
        assert connection.id == resource.source_connection_id
        raw_payload: dict[str, Any] | None = None
        if resource.resource_type == "feishu_sheet":
            raw_payload = {
                "metadata": {"spreadsheet": {"title": resource.name}},
                "sheets": [
                    {
                        "sheet": {"sheet_id": "sh1", "title": "目标"},
                        "range": "sh1!A1:B3",
                        "values": [["region", "target"], ["East", 120], ["West", 80]],
                    }
                ],
            }
        elif resource.resource_type == "feishu_base":
            raw_payload = {
                "tables": [
                    {
                        "table": {"table_id": "tbl1", "name": "线索", "view_id": "view1"},
                        "fields": {
                            "items": [
                                {"field_id": "fld_region", "field_name": "region"},
                                {"field_id": "fld_lead_count", "field_name": "lead_count"},
                            ]
                        },
                        "records": {
                            "items": [
                                {"record_id": "rec_east", "fields": {"region": "East", "lead_count": 3}},
                                {"record_id": "rec_west", "fields": {"region": "West", "lead_count": 2}},
                            ]
                        },
                    }
                ]
            }
        content = f"{resource.name}: Synced {resource.resource_type} from Feishu token {resource.external_id}."
        raw_bytes = json.dumps(raw_payload, ensure_ascii=False, sort_keys=True).encode("utf-8") if raw_payload else content.encode("utf-8")
        return CapturedSnapshot(
            raw_bytes=raw_bytes,
            content_text=content,
            external_revision=f"rev-{resource.external_id}",
            metadata={
                "provider": "feishu",
                "resource_type": resource.resource_type,
                "external_id": resource.external_id,
                "locator": {
                    "document_token": resource.external_id if resource.resource_type == "feishu_doc" else None,
                    "wiki_token": resource.external_id if resource.resource_type == "feishu_wiki" else None,
                    "spreadsheet_token": resource.external_id if resource.resource_type == "feishu_sheet" else None,
                    "app_token": resource.external_id if resource.resource_type == "feishu_base" else None,
                    "record_id": "rec_east" if resource.resource_type == "feishu_base" else None,
                    "field_id": "fld_lead_count" if resource.resource_type == "feishu_base" else None,
                },
            },
            provider="byaan-native",
            parser_version="feishu-contract-parser-v1",
            raw_storage_uri=f"feishu://{resource.resource_type}/{resource.external_id}",
        )


class _FakeTosHead:
    def __init__(
        self,
        *,
        size: int = 12,
        etag: str = '"etag-1"',
        last_modified: str = "2026-08-14T00:00:00Z",
        version_id: str = "version-1",
    ):
        self.content_length = size
        self.etag = etag
        self.last_modified = last_modified
        self.version_id = version_id


class _FakeTosObject:
    def __init__(self, raw: bytes):
        self.raw = raw
        self.etag = '"etag-1"'

    def read(self) -> bytes:
        return self.raw


class _FakeTosListedObject:
    def __init__(self, *, key: str, size: int = 24, etag: str = '"etag-1"', last_modified: str = "2026-08-14T00:00:00Z"):
        self.key = key
        self.size = size
        self.etag = etag
        self.last_modified = last_modified


class _FakeTosListOutput:
    def __init__(self):
        self.contents = [
            _FakeTosListedObject(key="reports/revenue.csv", size=24, etag='"etag-1"'),
            _FakeTosListedObject(key="reports/cost.csv", size=20, etag='"etag-2"'),
        ]


class _FakeTosClient:
    def __init__(self, *, mode: str = "ok"):
        self.mode = mode

    def head_object(self, *, bucket: str, key: str):
        if self.mode == "missing":
            raise RuntimeError("NoSuchKey: object not found")
        if self.mode == "forbidden":
            raise RuntimeError("AccessDenied: permission denied")
        if self.mode == "large":
            return _FakeTosHead(size=TosConnectorAdapter.max_inline_bytes + 1)
        return _FakeTosHead()

    def get_object(self, *, bucket: str, key: str):
        return _FakeTosObject(b"region,revenue\nEast,120\n")

    def list_objects_type2(self, *, bucket: str, prefix: str, max_keys: int, **kwargs):
        assert bucket == "sales-bucket"
        assert prefix in {"reports/", ""}
        assert max_keys == 1000
        return _FakeTosListOutput()


async def _tenant(test_session):
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    if tenant is not None:
        set_tenant_id(tenant.id)
        return tenant
    from uuid import uuid4

    user = User(
        id=uuid4(),
        email="source-connectors@test.com",
        hashed_password="fakehash",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    test_session.add(user)
    await test_session.flush()
    tenant = Tenant(
        id=uuid4(),
        name="Source Connector Tenant",
        slug=f"source-connector-{uuid4().hex[:8]}",
        owner_id=user.id,
        is_personal=True,
    )
    test_session.add(tenant)
    await test_session.flush()
    test_session.add(TenantMember(user_id=user.id, tenant_id=tenant.id, role=TenantRole.OWNER.value))
    await test_session.commit()
    set_tenant_id(tenant.id)
    return tenant


async def _another_tenant(test_session):
    from uuid import uuid4

    user = User(
        id=uuid4(),
        email=f"source-connectors-{uuid4().hex[:8]}@test.com",
        hashed_password="fakehash",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    test_session.add(user)
    await test_session.flush()
    tenant = Tenant(
        id=uuid4(),
        name="Other Source Connector Tenant",
        slug=f"source-connector-other-{uuid4().hex[:8]}",
        owner_id=user.id,
        is_personal=True,
    )
    test_session.add(tenant)
    await test_session.flush()
    test_session.add(TenantMember(user_id=user.id, tenant_id=tenant.id, role=TenantRole.OWNER.value))
    await test_session.commit()
    return tenant


async def test_connector_catalog_marks_only_real_connectors_available(test_client):
    response = await test_client.get("/api/connector-definitions")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    by_id = {item["id"]: item for item in items}
    assert {
        "local_files",
        "feishu",
        "web",
        "sql_databases",
        "volcengine_tos",
        "databricks",
    }.issubset(by_id)
    assert by_id["local_files"]["availability"] == "available"
    assert by_id["local_files"]["entry_kind"] == "embedded_flow"
    assert by_id["local_files"]["family"] == "files"
    assert by_id["local_files"]["resource_picker_type"] == "file_import"
    assert by_id["local_files"]["modeling_modes"] == ["context_assisted", "projection"]
    assert by_id["local_files"]["supported_resource_types"] == ["pdf", "file"]
    assert {gate["status"] for gate in by_id["local_files"]["readiness_gates"]} == {"passed"}
    assert by_id["web"]["availability"] == "available"
    assert by_id["web"]["entry_kind"] == "embedded_flow"
    assert by_id["web"]["family"] == "web"
    assert by_id["web"]["resource_picker_type"] == "url_import"
    assert by_id["web"]["modeling_modes"] == ["context_assisted"]
    assert by_id["feishu"]["availability"] == "available"
    assert by_id["feishu"]["entry_kind"] == "connector_backed"
    assert by_id["feishu"]["provider"] == "feishu"
    assert by_id["feishu"]["family"] == "business_docs"
    assert by_id["feishu"]["resource_picker_type"] == "oauth_drive_picker"
    assert by_id["feishu"]["modeling_modes"] == ["context_assisted", "projection"]
    assert "docx:document:readonly" in by_id["feishu"]["required_scopes"]
    assert by_id["feishu"]["limitations"]
    assert len(by_id["feishu"]["readiness_gates"]) == 10
    assert {gate["status"] for gate in by_id["feishu"]["readiness_gates"]} == {"passed"}
    assert {gate["key"] for gate in by_id["feishu"]["readiness_gates"]} >= {
        "tenant_isolated_auth",
        "immutable_snapshot",
        "context_index_status",
        "lifecycle_actions",
    }
    assert by_id["sql_databases"]["availability"] == "available"
    assert by_id["sql_databases"]["entry_kind"] == "embedded_flow"
    assert by_id["sql_databases"]["family"] == "databases"
    assert by_id["sql_databases"]["resource_picker_type"] == "database_schema_picker"
    assert by_id["sql_databases"]["modeling_modes"] == ["relational"]
    assert by_id["volcengine_tos"]["availability"] == "available"
    assert by_id["volcengine_tos"]["entry_kind"] == "connector_backed"
    assert by_id["volcengine_tos"]["status"] == "available"
    assert by_id["volcengine_tos"]["family"] == "object_storage"
    assert by_id["volcengine_tos"]["resource_picker_type"] == "object_storage_browser"
    assert by_id["volcengine_tos"]["modeling_modes"] == ["projection", "context_assisted"]
    assert "tos:GetObject" in by_id["volcengine_tos"]["required_scopes"]
    assert {gate["status"] for gate in by_id["volcengine_tos"]["readiness_gates"]} == {"passed"}
    assert by_id["databricks"]["availability"] == "available"
    assert by_id["databricks"]["entry_kind"] == "embedded_flow"
    assert by_id["databricks"]["family"] == "warehouses"
    assert by_id["databricks"]["resource_picker_type"] == "warehouse_catalog_picker"
    assert by_id["databricks"]["modeling_modes"] == ["warehouse"]
    assert by_id["aliyun_oss"]["availability"] == "planned"
    assert by_id["aliyun_oss"]["entry_kind"] == "roadmap"
    assert by_id["aliyun_oss"]["status"] == "planned"
    assert by_id["aliyun_oss"]["resource_picker_type"] == "roadmap_only"
    assert by_id["aliyun_oss"]["supported_resource_types"] == []
    assert by_id["aliyun_oss"]["modeling_modes"] == []
    assert len(by_id["aliyun_oss"]["readiness_gates"]) == 10
    assert {gate["status"] for gate in by_id["aliyun_oss"]["readiness_gates"]} == {"missing"}
    assert "Roadmap entry only" in by_id["aliyun_oss"]["limitations"][0]
    assert "snapshot_sync" in by_id["volcengine_tos"]["capabilities"]


async def test_source_connection_encrypts_credentials_and_redacts_secret(test_session):
    tenant = await _tenant(test_session)
    service = SourceConnectionService()
    adapter = FakeConnectorAdapter()
    connection = await service.create_connection(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceConnectionCreate(
            provider="volcengine_tos",
            auth_mode="access_key",
            display_name="经营分析 TOS",
            credentials={
                "endpoint": "https://tos-cn-beijing.volces.com",
                "region": "cn-beijing",
                "access_key_id": "tos-ak",
                "secret_access_key": "tos-secret",
                "verify_ssl": True,
            },
        ),
        adapter=adapter,
    )

    assert connection.status == "connected"
    assert "tos-secret" not in connection.encrypted_credentials
    decrypted = await CryptoService.decrypt_config(connection.encrypted_credentials, test_session)
    assert decrypted["secret_access_key"] == "tos-secret"
    redacted = await service.decrypted_redacted_credentials(session=test_session, connection=connection)
    assert redacted["secret_access_key"] == "tos-…cret"


async def test_children_route_accepts_tos_external_ids_with_slashes(test_client, monkeypatch):
    captured: dict[str, Any] = {}

    async def fake_list_resources(**kwargs):
        captured.update(kwargs)
        return {
            "items": [
                {
                    "external_id": "sales-bucket/reports/revenue.csv",
                    "resource_type": "tos_object",
                    "name": "revenue.csv",
                    "parent_external_id": "sales-bucket",
                    "source_url": None,
                    "has_children": False,
                    "is_folder": False,
                    "already_added": False,
                    "metadata": {"bucket": "sales-bucket", "key": "reports/revenue.csv"},
                }
            ],
            "next_page_token": None,
            "scope": "children",
            "connection_status": "connected",
        }

    monkeypatch.setattr("server.routers.source_connections.source_connection_service.list_resources", fake_list_resources)
    response = await test_client.get("/api/source-connections/conn_1/resources/sales-bucket/reports/children")

    assert response.status_code == 200
    assert captured["connection_id"] == "conn_1"
    assert captured["scope"] == "children"
    assert captured["parent_token"] == "sales-bucket/reports"
    assert response.json()["data"]["items"][0]["resource_type"] == "tos_object"


async def test_feishu_admin_config_and_oauth_callback_encrypt_tokens_and_isolate_users(test_session, monkeypatch):
    tenant = await _tenant(test_session)
    other_tenant = await _another_tenant(test_session)
    set_tenant_id(tenant.id)
    adapter = FeishuConnectorAdapter()

    await FeishuAdminConfigService.save_config(
        session=test_session,
        app_id="cli_a",
        app_secret="feishu-secret",
        redirect_uri="http://127.0.0.1:8080/api/source-connections/feishu/oauth/callback",
        scopes=["space:document:retrieve", "docx:document:readonly", "wiki:wiki:readonly"],
    )
    await test_session.commit()

    setting = await test_session.scalar(select(Setting).where(Setting.setting_key == "source_connector_feishu_config"))
    assert setting is not None
    assert "feishu-secret" not in setting.setting_value

    authorization_url, state = await adapter.create_authorization_url(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
    )
    parsed_authorization_url = urlparse(authorization_url)
    authorization_params = parse_qs(parsed_authorization_url.query)
    assert parsed_authorization_url.netloc == "accounts.feishu.cn"
    assert parsed_authorization_url.path == "/open-apis/authen/v1/authorize"
    assert authorization_params["client_id"] == ["cli_a"]
    assert authorization_params["response_type"] == ["code"]
    assert authorization_params["prompt"] == ["consent"]
    assert set(authorization_params["scope"][0].split()) == {
        "space:document:retrieve",
        "docx:document:readonly",
        "wiki:wiki:readonly",
    }
    assert "feishu-secret" not in authorization_url

    async def fake_exchange_code(*, config, code):
        assert code == "oauth-code"
        assert config["app_secret"] == "feishu-secret"
        return {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "scope": ["space:document:retrieve", "docx:document:readonly", "wiki:wiki:readonly"],
        }

    async def fake_get_user_info(access_token):
        assert access_token == "access-token"
        return {"open_id": "ou_1", "name": "郝行军"}

    monkeypatch.setattr(adapter, "_exchange_code", fake_exchange_code)
    monkeypatch.setattr(adapter, "_get_user_info", fake_get_user_info)

    connection = await adapter.complete_oauth_callback(session=test_session, code="oauth-code", state=state)
    assert connection.provider == "feishu"
    assert connection.status == "connected"
    assert connection.tenant_id == tenant.id
    assert connection.created_by == tenant.owner_id
    assert connection.external_account_id == "ou_1"
    assert "access-token" not in connection.encrypted_credentials

    decrypted = await CryptoService.decrypt_config(connection.encrypted_credentials, test_session)
    assert decrypted["access_token"] == "access-token"
    assert decrypted["refresh_token"] == "refresh-token"

    same_tenant_connections = await SourceConnectionService().list_connections(
        session=test_session,
        tenant_id=tenant.id,
        provider="feishu",
    )
    other_tenant_connections = await SourceConnectionService().list_connections(
        session=test_session,
        tenant_id=other_tenant.id,
        provider="feishu",
    )
    assert [item.id for item in same_tenant_connections] == [connection.id]
    assert other_tenant_connections == []

    flow = await test_session.scalar(select(FeishuOAuthFlow).where(FeishuOAuthFlow.state_hash == FeishuOAuthStateStore.state_hash(state)))
    assert flow is not None
    assert flow.status == "connected"
    assert flow.connection_id == connection.id
    assert flow.consumed_at is not None
    assert flow.result_json["connection_id"] == str(connection.id)


async def test_feishu_admin_config_status_is_admin_only_and_never_returns_secret(test_client, test_session, monkeypatch):
    tenant = await _tenant(test_session)
    set_tenant_id(tenant.id)
    monkeypatch.setenv("BYAAN_FEISHU_APP_ID", "cli_hosted")
    monkeypatch.setenv("BYAAN_FEISHU_APP_SECRET", "hosted-secret")
    monkeypatch.setenv("BYAAN_FEISHU_REDIRECT_URI", "http://127.0.0.1:8080/api/source-connections/feishu/oauth/callback")

    status_response = await test_client.get("/api/source-connections/feishu/status")
    assert status_response.status_code == 200
    status_data = status_response.json()["data"]
    assert status_data["admin_config"]["mode"] == "hosted"
    assert "cli_hosted" not in str(status_data)
    assert "hosted-secret" not in str(status_data)

    admin_response = await test_client.get("/api/source-connections/feishu/admin-config")
    assert admin_response.status_code == 200
    admin_data = admin_response.json()["data"]
    assert admin_data["app_id"] == "cli_hosted"
    assert admin_data["secret_configured"] is True
    assert "hosted-secret" not in str(admin_data)

    validation = await test_client.post("/api/source-connections/feishu/admin-config/validate")
    assert validation.status_code == 200
    checks = validation.json()["data"]["checks"]
    assert checks["credentials_valid"]["ok"] is True
    assert checks["scopes_complete"]["ok"] is True

    member = User(
        id=uuid4(),
        email="feishu-member@test.com",
        hashed_password="fakehash",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    test_session.add(member)
    await test_session.flush()
    test_session.add(TenantMember(user_id=member.id, tenant_id=tenant.id, role=TenantRole.MEMBER.value))
    await test_session.commit()
    monkeypatch.setenv("BYAAN_LOCAL_AUTH_IMPERSONATION_ENABLED", "true")

    member_response = await test_client.get(
        "/api/source-connections/feishu/admin-config",
        headers={"X-Local-User-ID": str(member.id)},
    )
    assert member_response.status_code == 403


async def test_feishu_self_built_config_takes_precedence_over_hosted_env(test_session, monkeypatch):
    tenant = await _tenant(test_session)
    set_tenant_id(tenant.id)
    monkeypatch.setenv("BYAAN_FEISHU_APP_ID", "cli_hosted")
    monkeypatch.setenv("BYAAN_FEISHU_APP_SECRET", "hosted-secret")
    monkeypatch.setenv("BYAAN_FEISHU_REDIRECT_URI", "http://127.0.0.1:8080/hosted-callback")

    await FeishuAdminConfigService.save_config(
        session=test_session,
        app_id="cli_self",
        app_secret="self-secret",
        redirect_uri="http://127.0.0.1:8080/self-callback",
        scopes=["space:document:retrieve", "docx:document:readonly", "wiki:wiki:readonly"],
    )
    await test_session.commit()

    config = await FeishuAdminConfigService.load_config(session=test_session)
    assert config is not None
    assert config["mode"] == "self_built"
    assert config["app_id"] == "cli_self"
    assert config["app_secret"] == "self-secret"


async def test_feishu_legacy_doc_scope_is_migrated_before_oauth(test_session):
    tenant = await _tenant(test_session)
    await FeishuAdminConfigService.save_config(
        session=test_session,
        app_id="cli_legacy",
        app_secret="legacy-secret",
        redirect_uri="http://127.0.0.1:8080/api/source-connections/feishu/oauth/callback",
        scopes=["space:document:retrieve", "docs:doc:readonly", "wiki:wiki:readonly"],
    )
    await test_session.commit()

    config = await FeishuAdminConfigService.load_config(session=test_session)
    assert config is not None
    assert "docs:doc:readonly" not in config["scopes"]
    assert "docx:document:readonly" in config["scopes"]

    authorization_url, _ = await FeishuConnectorAdapter().create_authorization_url(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
    )
    requested_scopes = set(parse_qs(urlparse(authorization_url).query)["scope"][0].split())
    assert "docs:doc:readonly" not in requested_scopes
    assert "docx:document:readonly" in requested_scopes


async def test_feishu_oauth_token_exchange_uses_v3_contract(monkeypatch):
    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "code": 0,
                "access_token": "user-access-token",
                "refresh_token": "refresh-token",
                "expires_in": 7200,
                "scope": "space:document:retrieve docx:document:readonly wiki:wiki:readonly",
                "token_type": "Bearer",
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, json):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("server.services.source_connectors.httpx.AsyncClient", lambda **kwargs: FakeClient())
    adapter = FeishuConnectorAdapter()
    token = await adapter._exchange_code(
        config={
            "app_id": "cli_v3",
            "app_secret": "secret-v3",
            "redirect_uri": "http://127.0.0.1:8080/api/source-connections/feishu/oauth/callback",
        },
        code="authorization-code",
    )

    assert captured["url"] == "https://accounts.feishu.cn/oauth/v3/token"
    assert captured["json"] == {
        "client_id": "cli_v3",
        "client_secret": "secret-v3",
        "grant_type": "authorization_code",
        "code": "authorization-code",
        "redirect_uri": "http://127.0.0.1:8080/api/source-connections/feishu/oauth/callback",
    }
    assert token["scope"] == "space:document:retrieve docx:document:readonly wiki:wiki:readonly"


async def test_feishu_oauth_refresh_uses_v3_contract(monkeypatch):
    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "code": 0,
                "access_token": "refreshed-user-access-token",
                "refresh_token": "rotated-refresh-token",
                "expires_in": 7200,
                "scope": "space:document:retrieve docx:document:readonly wiki:wiki:readonly",
                "token_type": "Bearer",
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, json):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("server.services.source_connectors.httpx.AsyncClient", lambda **kwargs: FakeClient())
    adapter = FeishuConnectorAdapter()
    token = await adapter._refresh_token(
        config={
            "app_id": "cli_v3",
            "app_secret": "secret-v3",
            "redirect_uri": "http://127.0.0.1:8080/api/source-connections/feishu/oauth/callback",
        },
        refresh_token="old-refresh-token",
    )

    assert captured["url"] == "https://accounts.feishu.cn/oauth/v3/token"
    assert captured["json"] == {
        "client_id": "cli_v3",
        "client_secret": "secret-v3",
        "grant_type": "refresh_token",
        "refresh_token": "old-refresh-token",
    }
    assert token["refresh_token"] == "rotated-refresh-token"


async def test_feishu_oauth_state_is_single_use_and_expired_state_is_rejected(test_session):
    tenant = await _tenant(test_session)
    state = await FeishuOAuthStateStore.create(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        redirect_uri="http://127.0.0.1/callback",
    )
    await test_session.commit()
    first = await FeishuOAuthStateStore.consume(session=test_session, state=state)
    second = await FeishuOAuthStateStore.consume(session=test_session, state=state)
    assert first is not None
    assert first.tenant_id == tenant.id
    assert second is None

    expired_state = await FeishuOAuthStateStore.create(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        redirect_uri="http://127.0.0.1/callback",
    )
    expired_flow = await test_session.scalar(
        select(FeishuOAuthFlow).where(FeishuOAuthFlow.state_hash == FeishuOAuthStateStore.state_hash(expired_state))
    )
    assert expired_flow is not None
    expired_flow.expires_at = datetime.utcnow() - timedelta(seconds=1)
    await test_session.commit()
    assert await FeishuOAuthStateStore.consume(session=test_session, state=expired_state) is None
    await test_session.refresh(expired_flow)
    assert expired_flow.status == "state_expired"


async def test_feishu_oauth_callback_route_returns_html_and_result_is_pollable(test_client, test_session, monkeypatch):
    tenant = await _tenant(test_session)
    set_tenant_id(tenant.id)
    await FeishuAdminConfigService.save_config(
        session=test_session,
        app_id="cli_a",
        app_secret="feishu-secret",
        redirect_uri="http://test/api/source-connections/feishu/oauth/callback",
        scopes=["space:document:retrieve", "docx:document:readonly", "wiki:wiki:readonly"],
    )
    await test_session.commit()

    async def fake_exchange_code(self, *, config, code):
        return {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "scope": ["space:document:retrieve", "docx:document:readonly", "wiki:wiki:readonly"],
        }

    async def fake_get_user_info(self, access_token):
        return {"open_id": "ou_1", "name": "郝行军"}

    monkeypatch.setattr(FeishuConnectorAdapter, "_exchange_code", fake_exchange_code)
    monkeypatch.setattr(FeishuConnectorAdapter, "_get_user_info", fake_get_user_info)

    start = await test_client.post("/api/source-connections/feishu/oauth/start")
    assert start.status_code == 200
    state = start.json()["data"]["state"]
    assert start.json()["data"]["result_url"].endswith(f"state={state}")

    callback = await test_client.get(f"/api/source-connections/feishu/oauth/callback?code=oauth-code&state={state}")
    assert callback.status_code == 200
    assert "text/html" in callback.headers["content-type"]
    assert "byaan:feishu-oauth" in callback.text
    assert "access-token" not in callback.text

    result = await test_client.get(f"/api/source-connections/feishu/oauth/result?state={state}")
    assert result.status_code == 200
    body = result.json()["data"]
    assert body["status"] == "connected"
    assert body["connection_id"]

    repeat = await test_client.get(f"/api/source-connections/feishu/oauth/callback?code=oauth-code&state={state}")
    assert repeat.status_code == 400
    assert "Invalid or expired" in repeat.text


async def test_picker_import_sync_and_idempotency_use_source_connection_not_placeholder(test_session):
    tenant = await _tenant(test_session)
    connection_service = SourceConnectionService()
    resource_service = SourceResourceService()
    adapter = FakeConnectorAdapter()
    connection = await connection_service.create_connection(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceConnectionCreate(
            provider="volcengine_tos",
            auth_mode="access_key",
            display_name="经营分析 TOS",
            credentials={
                "endpoint": "https://tos-cn-beijing.volces.com",
                "region": "cn-beijing",
                "access_key_id": "tos-ak",
                "secret_access_key": "tos-secret",
            },
        ),
        adapter=adapter,
    )

    listed = await connection_service.list_resources(
        session=test_session,
        tenant_id=tenant.id,
        connection_id=connection.id,
        scope="children",
        parent_token="sales-bucket/reports/",
        resource_type=None,
        query=None,
        page_token=None,
        page_size=50,
        adapter=adapter,
    )
    assert listed["next_page_token"] == "next-1"
    assert any(item["resource_type"] == "tos_object" for item in listed["items"])

    imported = await resource_service.import_resources(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceResourceImportRequest(
            connection_id=connection.id,
            selections=[
                {
                    "external_id": "sales-bucket/reports/revenue.csv",
                    "resource_type": "tos_object",
                    "name": "revenue.csv",
                    "selection_config": {"format": "csv"},
                }
            ],
        ),
        adapter=adapter,
    )

    assert imported["succeeded"] == 1
    resource = imported["results"][0]["resource"]
    assert resource["status"] == "ready"
    assert str(resource["source_connection_id"]) == str(connection.id)
    assert resource["latest_snapshot"]["external_revision"] == "etag-1"
    assert resource["latest_snapshot"]["metadata_json"]["version_id"] == "version-1"
    assert resource["knowledge_resource"]["evidence_count"] == 1
    assert resource["projected_dataset_id"]
    query_result = await DataFrameFileService.execute_duckdb_query_on_dataset(
        session=test_session,
        dataset_id=resource["projected_dataset_id"],
        query="SELECT SUM(revenue) AS total_revenue FROM revenue",
        limit=10,
    )
    assert query_result["success"] is True
    assert query_result["result"][0]["total_revenue"] == 200

    imported_again = await resource_service.import_resources(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceResourceImportRequest(
            connection_id=connection.id,
            selections=[
                {
                    "external_id": "sales-bucket/reports/revenue.csv",
                    "resource_type": "tos_object",
                    "name": "revenue.csv",
                    "selection_config": {"format": "csv"},
                }
            ],
        ),
        adapter=adapter,
    )
    assert imported_again["succeeded"] == 1

    resources = (await test_session.execute(select(SourceResource))).scalars().all()
    snapshots = (await test_session.execute(select(SourceSnapshot))).scalars().all()
    knowledge = (await test_session.execute(select(KnowledgeResource))).scalars().all()
    evidence = (await test_session.execute(select(EvidenceFragment))).scalars().all()
    datasets = (await test_session.execute(select(Dataset))).scalars().all()
    files = (await test_session.execute(select(File))).scalars().all()
    assert len(resources) == 1
    assert len(snapshots) == 1
    assert len(knowledge) == 1
    assert len(evidence) == 1
    assert len(datasets) == 1
    assert len(files) == 1
    projection = (snapshots[0].metadata_json or {})["projected_dataset"]
    projected_file = projection["files"][0]
    assert projected_file["source_locator"]["bucket"] == "sales-bucket"
    assert projected_file["source_locator"]["key"] == "reports/revenue.csv"
    assert projected_file["source_locator"]["version_id"] == "version-1"
    await test_session.refresh(resources[0])
    assert resources[0].status == "ready"


async def test_feishu_picker_import_syncs_real_resource_types_without_placeholder_state(test_session):
    tenant = await _tenant(test_session)
    connection_service = SourceConnectionService()
    resource_service = SourceResourceService()
    adapter = FakeFeishuConnectorAdapter()
    encrypted = await CryptoService.encrypt_config(
        {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "open_id": "ou_feishu_1",
        },
        test_session,
    )
    connection = SourceConnection(
        tenant_id=tenant.id,
        provider="feishu",
        auth_mode="oauth",
        encrypted_credentials=encrypted,
        external_account_id="ou_feishu_1",
        display_name="郝行军的飞书",
        status="connected",
        capabilities_json={"scopes": ["drive:drive:readonly", "wiki:wiki:readonly"]},
        token_expires_at=datetime.utcnow() + timedelta(hours=1),
        created_by=tenant.owner_id,
    )
    test_session.add(connection)
    await test_session.commit()
    await test_session.refresh(connection)

    listed = await connection_service.list_resources(
        session=test_session,
        tenant_id=tenant.id,
        connection_id=connection.id,
        scope="recent",
        parent_token=None,
        resource_type=None,
        query=None,
        page_token=None,
        page_size=50,
        adapter=adapter,
    )
    listed_types = {item["resource_type"] for item in listed["items"]}
    assert {"feishu_doc", "feishu_wiki", "feishu_sheet", "feishu_base"}.issubset(listed_types)

    imported = await resource_service.import_resources(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceResourceImportRequest(
            connection_id=connection.id,
            selections=[
                {
                    "external_id": item["external_id"],
                    "resource_type": item["resource_type"],
                    "name": item["name"],
                    "source_url": item["source_url"],
                    "metadata": item["metadata"],
                }
                for item in listed["items"]
            ],
        ),
        adapter=adapter,
    )

    assert imported["succeeded"] == 4
    assert imported["failed"] == 0
    for result in imported["results"]:
        resource = result["resource"]
        assert result["status"] == "ready"
        assert result["already_added"] is False
        assert result["resource_action"] == "created"
        assert resource["status"] == "ready"
        assert resource["status"] != "needs_confirmation"
        assert str(resource["source_connection_id"]) == str(connection.id)
        assert resource["latest_snapshot"]["external_revision"] == f"rev-{resource['external_id']}"
        assert resource["knowledge_resource"]["evidence_count"] == 1
        if resource["resource_type"] in {"feishu_sheet", "feishu_base"}:
            assert resource["projected_dataset_id"]

    resources = (await test_session.execute(select(SourceResource))).scalars().all()
    snapshots = (await test_session.execute(select(SourceSnapshot))).scalars().all()
    knowledge = (await test_session.execute(select(KnowledgeResource))).scalars().all()
    evidence = (await test_session.execute(select(EvidenceFragment))).scalars().all()
    datasets = (await test_session.execute(select(Dataset))).scalars().all()
    files = (await test_session.execute(select(File))).scalars().all()
    assert len(resources) == 4
    assert len(snapshots) == 4
    assert len(knowledge) == 4
    assert len(evidence) == 4
    assert len(datasets) == 2
    assert len(files) == 2

    wiki_item = next(item for item in listed["items"] if item["resource_type"] == "feishu_wiki")
    reimported_wiki = await resource_service.import_resources(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceResourceImportRequest(
            connection_id=connection.id,
            selections=[
                {
                    "external_id": wiki_item["external_id"],
                    "resource_type": wiki_item["resource_type"],
                    "name": wiki_item["name"],
                    "source_url": wiki_item["source_url"],
                    "selection_config": {"imported_from": "datasources_connector_picker"},
                    "metadata": wiki_item["metadata"],
                }
            ],
        ),
        adapter=adapter,
    )

    assert reimported_wiki["succeeded"] == 1
    assert reimported_wiki["failed"] == 0
    assert reimported_wiki["results"][0]["already_added"] is True
    assert reimported_wiki["results"][0]["resource_action"] == "reused"
    wiki_resource = reimported_wiki["results"][0]["resource"]
    assert wiki_resource["selection_config_json"]["imported_from"] == "datasources_connector_picker"
    assert wiki_resource["selection_config_json"]["metadata"]["node_token"] == "wiki_node_1"
    resources_after_reimport = (await test_session.execute(select(SourceResource))).scalars().all()
    snapshots_after_reimport = (await test_session.execute(select(SourceSnapshot))).scalars().all()
    assert len(resources_after_reimport) == 4
    assert len(snapshots_after_reimport) == 4

    sheet = next(result["resource"] for result in imported["results"] if result["resource"]["resource_type"] == "feishu_sheet")
    sheet_dataset = await test_session.get(Dataset, sheet["projected_dataset_id"])
    assert sheet_dataset is not None
    sheet_schema = json.loads(sheet_dataset.schema_cache)
    sheet_table = next(iter(sheet_schema["schema"].keys()))
    sheet_query = await DataFrameFileService.execute_duckdb_query_on_dataset(
        session=test_session,
        dataset_id=sheet["projected_dataset_id"],
        query=f'SELECT SUM(target) AS total_target FROM "{sheet_table}"',
        limit=10,
    )
    assert sheet_query["success"] is True
    assert sheet_query["result"][0]["total_target"] == 200

    sheet_resource_row = await test_session.get(SourceResource, sheet["id"])
    assert sheet_resource_row is not None
    sheet_snapshot = await test_session.get(SourceSnapshot, sheet["latest_snapshot_id"])
    assert sheet_snapshot is not None
    sheet_evidence = await test_session.scalar(
        select(EvidenceFragment).where(EvidenceFragment.snapshot_id == sheet_snapshot.id)
    )
    assert sheet_evidence is not None
    assert sheet_evidence.fragment_type == "sheet_range"
    assert sheet_evidence.locator_json["source_connection_id"] == str(connection.id)
    assert sheet_evidence.locator_json["source_resource_id"] == str(sheet_resource_row.id)
    assert sheet_evidence.locator_json["source_snapshot_id"] == str(sheet_snapshot.id)
    assert sheet_evidence.locator_json["content_hash"] == sheet_snapshot.content_hash
    assert sheet_evidence.locator_json["parser_version"] == sheet_snapshot.parser_version
    assert sheet_evidence.locator_json["spreadsheet_token"] == "sheet_token_1"
    assert sheet_evidence.locator_json["sheet_id"] == "sh1"
    assert sheet_evidence.locator_json["range"] == "sh1!A1:B3"
    assert sheet_evidence.locator_json["cell_range"] == "sh1!A1:B3"

    projection = (sheet_snapshot.metadata_json or {})["projected_dataset"]
    projected_file = projection["files"][0]
    assert projected_file["source_locator"]["spreadsheet_token"] == "sheet_token_1"
    assert projected_file["source_locator"]["sheet_id"] == "sh1"
    assert projected_file["source_locator"]["range"] == "sh1!A1:B3"
    assert projected_file["row_mappings"][0] == {"dataset_row": 1, "source_row": 2}
    assert projected_file["coordinate_system"] == {
        "kind": "sheet_grid",
        "range": "sh1!A1:B3",
        "header_row": 1,
        "first_data_row": 2,
        "first_column": "A",
    }
    assert projected_file["column_mappings"] == [
        {"dataset_column": "region", "source_column": "A", "header_cell": "A1"},
        {"dataset_column": "target", "source_column": "B", "header_cell": "B1"},
    ]
    assert projected_file["cell_mappings"] == [
        {"dataset_row": 1, "dataset_column": "region", "source_cell": "A2"},
        {"dataset_row": 1, "dataset_column": "target", "source_cell": "B2"},
        {"dataset_row": 2, "dataset_column": "region", "source_cell": "A3"},
        {"dataset_row": 2, "dataset_column": "target", "source_cell": "B3"},
    ]

    base = next(result["resource"] for result in imported["results"] if result["resource"]["resource_type"] == "feishu_base")
    base_snapshot = await test_session.get(SourceSnapshot, base["latest_snapshot_id"])
    assert base_snapshot is not None
    base_evidence = await test_session.scalar(
        select(EvidenceFragment).where(EvidenceFragment.snapshot_id == base_snapshot.id)
    )
    assert base_evidence is not None
    assert base_evidence.locator_json["app_token"] == "base_token_1"
    assert base_evidence.locator_json["table_id"] == "tbl1"
    assert base_evidence.locator_json["view_id"] == "view1"
    assert base_evidence.locator_json["record_id"] == "rec_east"
    assert base_evidence.locator_json["field_id"] == "fld_lead_count"

    base_projection = (base_snapshot.metadata_json or {})["projected_dataset"]
    base_projected_file = base_projection["files"][0]
    assert base_projected_file["source_locator"]["app_token"] == "base_token_1"
    assert base_projected_file["source_locator"]["table_id"] == "tbl1"
    assert base_projected_file["source_locator"]["view_id"] == "view1"
    assert base_projected_file["source_locator"]["field_mappings"] == [
        {"dataset_column": "region", "field_id": "fld_region", "field_name": "region"},
        {"dataset_column": "lead_count", "field_id": "fld_lead_count", "field_name": "lead_count"},
    ]
    assert base_projected_file["row_mappings"] == [
        {"dataset_row": 1, "record_id": "rec_east"},
        {"dataset_row": 2, "record_id": "rec_west"},
    ]


async def test_failed_source_resource_does_not_mark_picker_item_already_added(test_session):
    tenant = await _tenant(test_session)
    connection_service = SourceConnectionService()
    adapter = FakeFeishuConnectorAdapter()
    encrypted = await CryptoService.encrypt_config(
        {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "open_id": "ou_feishu_1",
        },
        test_session,
    )
    connection = SourceConnection(
        tenant_id=tenant.id,
        provider="feishu",
        auth_mode="oauth",
        encrypted_credentials=encrypted,
        external_account_id="ou_feishu_1",
        display_name="郝行军的飞书",
        status="connected",
        capabilities_json={"scopes": ["drive:drive:readonly", "wiki:wiki:readonly"]},
        token_expires_at=datetime.utcnow() + timedelta(hours=1),
        created_by=tenant.owner_id,
    )
    test_session.add(connection)
    await test_session.flush()
    test_session.add(
        SourceResource(
            tenant_id=tenant.id,
            source_connection_id=connection.id,
            resource_type="feishu_doc",
            name="Failed doc",
            external_id="docx_token_1",
            owner_id=tenant.owner_id,
            visibility="workspace",
            sync_mode="manual",
            status="failed",
        )
    )
    await test_session.commit()

    listed = await connection_service.list_resources(
        session=test_session,
        tenant_id=tenant.id,
        connection_id=connection.id,
        scope="recent",
        parent_token=None,
        resource_type=None,
        query=None,
        page_token=None,
        page_size=50,
        adapter=adapter,
    )

    doc = next(item for item in listed["items"] if item["external_id"] == "docx_token_1")
    assert doc["already_added"] is False


async def test_dataset_projection_failure_marks_failed_without_orphan_dataset(test_session, monkeypatch):
    tenant = await _tenant(test_session)
    connection_service = SourceConnectionService()
    resource_service = SourceResourceService()
    adapter = FakeConnectorAdapter()
    connection = await connection_service.create_connection(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceConnectionCreate(
            provider="volcengine_tos",
            auth_mode="access_key",
            display_name="经营分析 TOS",
            credentials={
                "endpoint": "https://tos-cn-beijing.volces.com",
                "region": "cn-beijing",
                "access_key_id": "tos-ak",
                "secret_access_key": "tos-secret",
            },
        ),
        adapter=adapter,
    )

    async def fail_schema(*args, **kwargs):
        raise RuntimeError("schema inference failed")

    monkeypatch.setattr(DataFrameFileService, "get_file_schema_multi", fail_schema)

    imported = await resource_service.import_resources(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceResourceImportRequest(
            connection_id=connection.id,
            selections=[
                {
                    "external_id": "sales-bucket/reports/revenue.csv",
                    "resource_type": "tos_object",
                    "name": "revenue.csv",
                    "selection_config": {"format": "csv"},
                }
            ],
        ),
        adapter=adapter,
    )

    assert imported["succeeded"] == 0
    assert imported["failed"] == 1
    result = imported["results"][0]
    assert result["status"] == "failed"
    assert result["error"]["code"] == "dataset_projection_failed"
    assert result["resource"]["latest_snapshot_id"] is None
    assert result["resource"]["sync_config_json"]["last_error"]["code"] == "dataset_projection_failed"

    resources = (await test_session.execute(select(SourceResource))).scalars().all()
    snapshots = (await test_session.execute(select(SourceSnapshot))).scalars().all()
    knowledge = (await test_session.execute(select(KnowledgeResource))).scalars().all()
    evidence = (await test_session.execute(select(EvidenceFragment))).scalars().all()
    datasets = (await test_session.execute(select(Dataset))).scalars().all()
    files = (await test_session.execute(select(File))).scalars().all()
    assert len(resources) == 1
    assert resources[0].status == "failed"
    assert len(snapshots) == 1
    assert len(knowledge) == 1
    assert len(evidence) == 1
    assert datasets == []
    assert files == []


async def test_sync_failure_keeps_previous_successful_snapshot(test_session):
    tenant = await _tenant(test_session)
    connection_service = SourceConnectionService()
    resource_service = SourceResourceService()
    adapter = FakeConnectorAdapter()
    connection = await connection_service.create_connection(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceConnectionCreate(
            provider="volcengine_tos",
            auth_mode="access_key",
            display_name="经营分析 TOS",
            credentials={
                "endpoint": "https://tos-cn-beijing.volces.com",
                "region": "cn-beijing",
                "access_key_id": "tos-ak",
                "secret_access_key": "tos-secret",
            },
        ),
        adapter=adapter,
    )
    imported = await resource_service.import_resources(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceResourceImportRequest(
            connection_id=connection.id,
            selections=[
                {
                    "external_id": "sales-bucket/reports/revenue.csv",
                    "resource_type": "tos_object",
                    "name": "revenue.csv",
                    "selection_config": {"format": "csv"},
                }
            ],
        ),
        adapter=adapter,
    )
    ready_resource = imported["results"][0]["resource"]
    previous_snapshot_id = ready_resource["latest_snapshot_id"]

    class FailingAdapter(FakeConnectorAdapter):
        async def sync_resource(self, *, session, connection: SourceConnection, resource: SourceResource) -> CapturedSnapshot:
            raise ConnectorError("TOS permission denied", code="permission_lost", permanent=True)

    failed = await resource_service.import_resources(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceResourceImportRequest(
            connection_id=connection.id,
            selections=[
                {
                    "external_id": "sales-bucket/reports/revenue.csv",
                    "resource_type": "tos_object",
                    "name": "revenue.csv",
                    "selection_config": {"format": "csv"},
                }
            ],
        ),
        adapter=FailingAdapter(),
    )
    result = failed["results"][0]
    assert failed["succeeded"] == 0
    assert failed["failed"] == 1
    assert result["status"] == "permission_lost"
    assert result["resource"]["latest_snapshot_id"] == previous_snapshot_id
    assert result["resource"]["sync_config_json"]["last_error"]["code"] == "permission_lost"
    assert result["resource"]["sync_config_json"]["latest_sync_run"]["status"] == "failed"
    assert result["resource"]["sync_config_json"]["latest_sync_run"]["error"]["code"] == "permission_lost"

    connection.status = "reauthorization_required"
    await test_session.flush()
    resource_row = await test_session.get(SourceResource, ready_resource["id"])
    assert resource_row is not None
    stale_payload = await resource_service.resource_payload(session=test_session, resource=resource_row)
    assert stale_payload["status"] == "reauthorization_required"
    assert stale_payload["latest_snapshot_id"] == previous_snapshot_id
    assert stale_payload["sync_config_json"]["connection_status"] == "reauthorization_required"
    assert stale_payload["sync_config_json"]["last_error"]["code"] == "reauthorization_required"

    snapshots = (await test_session.execute(select(SourceSnapshot))).scalars().all()
    datasets = (await test_session.execute(select(Dataset))).scalars().all()
    files = (await test_session.execute(select(File))).scalars().all()
    assert len(snapshots) == 1
    assert len(datasets) == 1
    assert len(files) == 1


async def test_tos_large_object_import_surfaces_confirmation_state(test_session):
    tenant = await _tenant(test_session)
    connection_service = SourceConnectionService()
    resource_service = SourceResourceService()

    class LargeObjectAdapter(FakeConnectorAdapter):
        async def sync_resource(self, *, session, connection: SourceConnection, resource: SourceResource) -> CapturedSnapshot:
            raise ConnectorError(
                "TOS object is too large; confirmation required",
                code="large_file_confirmation_required",
                permanent=True,
            )

    connection = await connection_service.create_connection(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceConnectionCreate(
            provider="volcengine_tos",
            auth_mode="access_key",
            display_name="经营分析 TOS",
            credentials={
                "endpoint": "https://tos-cn-beijing.volces.com",
                "region": "cn-beijing",
                "access_key_id": "tos-ak",
                "secret_access_key": "tos-secret",
            },
        ),
        adapter=FakeConnectorAdapter(),
    )

    imported = await resource_service.import_resources(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceResourceImportRequest(
            connection_id=connection.id,
            selections=[
                {
                    "external_id": "sales-bucket/raw/huge-export.parquet",
                    "resource_type": "tos_object",
                    "name": "huge-export.parquet",
                    "metadata": {"bucket": "sales-bucket", "key": "raw/huge-export.parquet", "size": 209715200},
                }
            ],
        ),
        adapter=LargeObjectAdapter(),
    )

    result = imported["results"][0]
    resource = result["resource"]
    sync_run = resource["sync_config_json"]["latest_sync_run"]

    assert imported["succeeded"] == 0
    assert imported["failed"] == 1
    assert result["status"] == "needs_confirmation"
    assert result["error"]["code"] == "large_file_confirmation_required"
    assert resource["status"] == "needs_confirmation"
    assert resource["latest_snapshot_id"] is None
    assert resource["sync_config_json"]["last_error"]["code"] == "large_file_confirmation_required"
    assert sync_run["status"] == "needs_confirmation"
    assert sync_run["error"]["code"] == "large_file_confirmation_required"
    assert sync_run["checkpoint"] is None

    resource_row = await test_session.get(SourceResource, resource["id"])
    assert resource_row is not None
    processing = await resource_service.processing_payload(
        session=test_session,
        tenant_id=tenant.id,
        resource_id=str(resource_row.id),
    )
    assert processing["status"] == "needs_confirmation"
    assert processing["stage"] == "needs_confirmation"
    assert processing["connector_required"] is False
    assert processing["next_actions"] == ["Review object size", "Confirm large object sync"]


async def test_successful_source_sync_run_records_checkpoint(test_session):
    tenant = await _tenant(test_session)
    connection_service = SourceConnectionService()
    resource_service = SourceResourceService()
    adapter = FakeConnectorAdapter()
    connection = await connection_service.create_connection(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceConnectionCreate(
            provider="volcengine_tos",
            auth_mode="access_key",
            display_name="经营分析 TOS",
            credentials={
                "endpoint": "https://tos-cn-beijing.volces.com",
                "region": "cn-beijing",
                "access_key_id": "tos-ak",
                "secret_access_key": "tos-secret",
            },
        ),
        adapter=adapter,
    )

    imported = await resource_service.import_resources(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceResourceImportRequest(
            connection_id=connection.id,
            selections=[
                {
                    "external_id": "sales-bucket/reports/revenue.csv",
                    "resource_type": "tos_object",
                    "name": "revenue.csv",
                    "selection_config": {"format": "csv"},
                }
            ],
        ),
        adapter=adapter,
    )

    resource = imported["results"][0]["resource"]
    sync_run = resource["sync_config_json"]["latest_sync_run"]
    assert sync_run["status"] == "succeeded"
    assert sync_run["attempt"] == 1
    assert sync_run["checkpoint"]["snapshot_id"] == str(resource["latest_snapshot_id"])
    assert sync_run["checkpoint"]["external_revision"] == "etag-1"
    assert sync_run["checkpoint"]["content_hash"].startswith("sha256:")


async def test_source_sync_run_status_contract_rejects_unknown_status(test_session):
    tenant = await _tenant(test_session)
    resource = SourceResource(
        tenant_id=tenant.id,
        resource_type="tos_object",
        name="revenue.csv",
        sync_mode="manual",
        sync_config_json={},
        status="pending",
    )
    test_session.add(resource)
    await test_session.flush()

    service = SourceResourceService()
    sync_run = service._start_sync_run(resource=resource, trigger="manual")

    assert sync_run["status"] == "running"
    assert sync_run["allowed_statuses"] == [
        "queued",
        "running",
        "succeeded",
        "failed",
        "partial",
        "cancelled",
        "needs_confirmation",
    ]
    with pytest.raises(ValueError, match="Unsupported source sync run status"):
        service._finish_sync_run(resource=resource, sync_run=sync_run, status="mystery")


async def test_feishu_picker_mapping_and_wiki_resolution_contract():
    adapter = FeishuConnectorAdapter()

    doc = adapter._drive_item_to_picker(
        {
            "type": "docx",
            "token": "docx_token",
            "name": "经营规则说明",
            "url": "https://example.feishu.cn/docx/docx_token",
        },
        frozenset({"sheet_token"}),
    )
    sheet = adapter._drive_item_to_picker(
        {
            "type": "sheet",
            "spreadsheet_token": "sheet_token",
            "title": "经营目标表",
        },
        frozenset({"sheet_token"}),
    )
    base = adapter._drive_item_to_picker({"type": "bitable", "token": "base_token", "name": "客户 Base"}, frozenset())
    folder = adapter._drive_item_to_picker({"type": "folder", "token": "folder_token", "name": "团队空间"}, frozenset())
    wiki = adapter._wiki_item_to_picker(
        {
            "node_token": "wiki_node",
            "obj_token": "docx_token_2",
            "obj_type": "docx",
            "title": "Wiki 节点",
            "has_child": True,
        },
        frozenset(),
    )
    wiki_space = adapter._wiki_item_to_picker(
        {
            "space_id": "7043731224849907715",
            "name": "企业纪律与职业道德委员会",
        },
        frozenset(),
    )

    assert doc.resource_type == "feishu_doc"
    assert doc.external_id == "docx_token"
    assert sheet.resource_type == "feishu_sheet"
    assert sheet.external_id == "sheet_token"
    assert sheet.already_added is True
    assert base.resource_type == "feishu_base"
    assert folder.resource_type == "feishu_folder"
    assert folder.is_folder is True
    assert wiki.resource_type == "feishu_wiki"
    assert wiki.has_children is True
    assert wiki.metadata["obj_token"] == "docx_token_2"
    assert wiki.metadata["type"] == "wiki_node"
    assert wiki_space.resource_type == "feishu_folder"
    assert wiki_space.external_id == "7043731224849907715"
    assert wiki_space.has_children is True
    assert wiki_space.is_folder is True
    assert wiki_space.metadata["type"] == "wiki_space"
    assert adapter._split_wiki_parent_token("7043731224849907715") == ("7043731224849907715", None)
    assert adapter._split_wiki_parent_token("7043731224849907715:wiki_node") == ("7043731224849907715", "wiki_node")


async def test_feishu_captured_snapshot_uses_configured_knowledge_provider(test_session, monkeypatch):
    tenant = await _tenant(test_session)
    adapter = FeishuConnectorAdapter()
    monkeypatch.setenv("KNOWLEDGE_PROVIDER", "openviking")
    encrypted = await CryptoService.encrypt_config({"access_token": "access-token"}, test_session)
    connection = SourceConnection(
        tenant_id=tenant.id,
        provider="feishu",
        auth_mode="oauth",
        encrypted_credentials=encrypted,
        external_account_id="ou_feishu_1",
        display_name="郝行军的飞书",
        status="connected",
        capabilities_json={"scopes": []},
        token_expires_at=datetime.utcnow() + timedelta(hours=1),
        created_by=tenant.owner_id,
    )
    resource = SourceResource(
        tenant_id=tenant.id,
        source_connection_id=connection.id,
        resource_type="feishu_doc",
        name="经营规则说明",
        external_id="docx_token_1",
        visibility="workspace",
        sync_mode="manual",
        status="pending",
    )

    async def fake_fetch_docx(*, access_token, document_id):
        assert access_token == "access-token"
        assert document_id == "docx_token_1"
        return "收入定义：已支付订单净额。", {"document": {"title": "经营规则说明"}}, "rev-1"

    monkeypatch.setattr(adapter, "_fetch_docx", fake_fetch_docx)

    captured = await adapter.sync_resource(session=test_session, connection=connection, resource=resource)

    assert captured.provider == "openviking"
    assert captured.metadata["provider"] == "feishu"
    assert captured.parser_version == "feishu-openapi-v1"


async def test_feishu_quick_locate_parses_links_and_returns_picker_item_without_creating_resource(test_session, monkeypatch):
    tenant = await _tenant(test_session)
    adapter = FeishuConnectorAdapter()
    encrypted = await CryptoService.encrypt_config(
        {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "open_id": "ou_feishu_1",
        },
        test_session,
    )
    connection = SourceConnection(
        tenant_id=tenant.id,
        provider="feishu",
        auth_mode="oauth",
        encrypted_credentials=encrypted,
        external_account_id="ou_feishu_1",
        display_name="郝行军的飞书",
        status="connected",
        capabilities_json={"scopes": ["drive:drive:readonly", "wiki:wiki:readonly"]},
        token_expires_at=datetime.utcnow() + timedelta(hours=1),
        created_by=tenant.owner_id,
    )
    test_session.add(connection)
    await test_session.commit()

    parsed_doc = adapter.parse_resource_url("https://example.feishu.cn/docx/docx_token_1?from=from_copylink")
    parsed_sheet = adapter.parse_resource_url("https://example.feishu.cn/sheets/sheet_token_1")
    parsed_base = adapter.parse_resource_url("https://example.feishu.cn/base/base_token_1?table=tbl1")
    parsed_wiki = adapter.parse_resource_url("https://example.feishu.cn/wiki/wiki_node_1")
    assert parsed_doc == {"resource_type": "feishu_doc", "external_id": "docx_token_1"}
    assert parsed_sheet == {"resource_type": "feishu_sheet", "external_id": "sheet_token_1"}
    assert parsed_base == {"resource_type": "feishu_base", "external_id": "base_token_1"}
    assert parsed_wiki == {"resource_type": "feishu_wiki", "external_id": "wiki_node_1"}

    calls: list[tuple[str, str]] = []

    async def fake_request_json(method, path, *, access_token, params=None, json_body=None):
        calls.append((method, path))
        assert access_token == "access-token"
        if path == "/open-apis/docx/v1/documents/docx_token_1":
            return {"data": {"document": {"title": "经营规则说明"}}}
        raise AssertionError(f"Unexpected Feishu API path: {path}")

    monkeypatch.setattr(adapter, "_request_json", fake_request_json)

    located = await SourceConnectionService().locate_resource_from_url(
        session=test_session,
        tenant_id=tenant.id,
        connection_id=connection.id,
        url="https://example.feishu.cn/docx/docx_token_1?from=from_copylink",
        adapter=adapter,
    )

    assert located["connection_status"] == "connected"
    assert located["item"]["external_id"] == "docx_token_1"
    assert located["item"]["resource_type"] == "feishu_doc"
    assert located["item"]["name"] == "经营规则说明"
    assert located["item"]["metadata"]["located_from_url"].startswith("https://example.feishu.cn/docx/docx_token_1")
    assert calls == [("GET", "/open-apis/docx/v1/documents/docx_token_1")]
    assert (await test_session.execute(select(SourceResource))).scalars().all() == []

    with pytest.raises(ConnectorError) as unsupported:
        adapter.parse_resource_url("https://example.feishu.cn/messenger/image_token")
    assert unsupported.value.code == "unsupported_feishu_link"


async def test_feishu_quick_locate_marks_already_added_resources(test_session, monkeypatch):
    tenant = await _tenant(test_session)
    adapter = FeishuConnectorAdapter()
    encrypted = await CryptoService.encrypt_config({"access_token": "access-token"}, test_session)
    connection = SourceConnection(
        tenant_id=tenant.id,
        provider="feishu",
        auth_mode="oauth",
        encrypted_credentials=encrypted,
        external_account_id="ou_feishu_1",
        display_name="郝行军的飞书",
        status="connected",
        capabilities_json={"scopes": []},
        token_expires_at=datetime.utcnow() + timedelta(hours=1),
        created_by=tenant.owner_id,
    )
    test_session.add(connection)
    await test_session.flush()
    test_session.add(
        SourceResource(
            tenant_id=tenant.id,
            source_connection_id=connection.id,
            resource_type="feishu_doc",
            name="已添加文档",
            external_id="docx_token_1",
            owner_id=tenant.owner_id,
            visibility="workspace",
            sync_mode="manual",
            status="ready",
        )
    )
    await test_session.commit()

    async def fake_request_json(method, path, *, access_token, params=None, json_body=None):
        return {"data": {"document": {"title": "已添加文档"}}}

    monkeypatch.setattr(adapter, "_request_json", fake_request_json)
    located = await SourceConnectionService().locate_resource_from_url(
        session=test_session,
        tenant_id=tenant.id,
        connection_id=connection.id,
        url="https://example.feishu.cn/docx/docx_token_1",
        adapter=adapter,
    )

    assert located["item"]["already_added"] is True


async def test_tos_parser_contracts_cover_supported_formats_and_actionable_errors():
    csv_text, csv_parser, csv_hint = parse_object_bytes(key="revenue.csv", raw_bytes=b"region,revenue\nEast,120\n")
    json_text, json_parser, json_hint = parse_object_bytes(key="records.json", raw_bytes=b'{"region":"East","revenue":120}')
    jsonl_text, jsonl_parser, jsonl_hint = parse_object_bytes(
        key="records.jsonl",
        raw_bytes=b'{"region":"East"}\n{"region":"West"}\n',
    )
    markdown_text, markdown_parser, markdown_hint = parse_object_bytes(key="memo.md", raw_bytes="## 复盘".encode())
    html_text, html_parser, html_hint = parse_object_bytes(
        key="report.html",
        raw_bytes=b"<html><body><script>bad()</script><h1>Report</h1><p>Revenue</p></body></html>",
    )
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "Revenue"
    worksheet.append(["region", "revenue"])
    worksheet.append(["East", 120])
    xlsx_buffer = io.BytesIO()
    workbook.save(xlsx_buffer)
    xlsx_text, xlsx_parser, xlsx_hint = parse_object_bytes(key="revenue.xlsx", raw_bytes=xlsx_buffer.getvalue())

    duckdb = pytest.importorskip("duckdb")
    with tempfile.TemporaryDirectory() as parquet_dir:
        parquet_path = Path(parquet_dir) / "revenue.parquet"
        duckdb.sql(f"COPY (SELECT 'East' AS region, 120 AS revenue) TO '{parquet_path}' (FORMAT PARQUET)")
        parquet_text, parquet_parser, parquet_hint = parse_object_bytes(
            key="revenue.parquet",
            raw_bytes=parquet_path.read_bytes(),
        )

    assert "| region | revenue |" in csv_text
    assert csv_parser == "tos-csv-parser-v1"
    assert csv_hint == "csv_rows"
    assert '"region": "East"' in json_text
    assert json_parser == "tos-json-parser-v1"
    assert json_hint == "json_records"
    assert '"region": "West"' in jsonl_text
    assert jsonl_parser == "tos-jsonl-parser-v1"
    assert jsonl_hint == "json_records"
    assert markdown_text == "## 复盘"
    assert markdown_parser == "tos-md-parser-v1"
    assert markdown_hint == "raw_text"
    assert "Report" in html_text and "bad()" not in html_text
    assert html_parser == "tos-html-parser-v1"
    assert html_hint == "html_section"
    assert "| region | revenue |" in xlsx_text
    assert xlsx_parser == "tos-excel-parser-v1"
    assert xlsx_hint == "excel_range"
    assert "| East | 120 |" in parquet_text
    assert parquet_parser == "tos-parquet-parser-v1"
    assert parquet_hint == "parquet_rows"

    with pytest.raises(ConnectorError) as unsupported:
        parse_object_bytes(key="archive.bin", raw_bytes=b"\x00\x01")
    assert unsupported.value.code == "unsupported_format"

    with pytest.raises(ConnectorError) as invalid_json:
        parse_object_bytes(key="records.json", raw_bytes=b"{not json")
    assert invalid_json.value.code == "parser_invalid_json"

    with pytest.raises(ConnectorError) as empty_pdf:
        parse_object_bytes(key="scan.pdf", raw_bytes=b"%PDF-1.7\n")
    assert empty_pdf.value.code == "parser_no_text"


async def test_tos_object_sync_maps_large_missing_and_permission_errors(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_PROVIDER", "openviking")
    resource = SourceResource(
        tenant_id=uuid4(),
        resource_type="tos_object",
        name="revenue.csv",
        external_id="sales-bucket/reports/revenue.csv",
        visibility="workspace",
        sync_mode="manual",
        status="pending",
    )
    adapter = TosConnectorAdapter()

    monkeypatch.setattr(adapter, "_client", lambda credentials: _FakeTosClient(mode="large"))
    with pytest.raises(ConnectorError) as large:
        await adapter._sync_object(credentials={"region": "cn-beijing"}, resource=resource)
    assert large.value.code == "large_file_confirmation_required"

    resource.selection_config_json = {"allow_large_file": True}
    monkeypatch.setattr(adapter, "_client", lambda credentials: _FakeTosClient(mode="ok"))
    captured = await adapter._sync_object(credentials={"region": "cn-beijing"}, resource=resource)
    assert captured.external_revision == "etag-1"
    assert captured.metadata["bucket"] == "sales-bucket"
    assert captured.metadata["key"] == "reports/revenue.csv"
    assert captured.metadata["version_id"] == "version-1"
    assert captured.provider == "openviking"
    assert captured.metadata["provider"] == "volcengine_tos"

    monkeypatch.setattr(adapter, "_client", lambda credentials: _FakeTosClient(mode="missing"))
    with pytest.raises(ConnectorError) as missing:
        await adapter._sync_object(credentials={}, resource=resource)
    assert missing.value.code == "source_unavailable"

    monkeypatch.setattr(adapter, "_client", lambda credentials: _FakeTosClient(mode="forbidden"))
    with pytest.raises(ConnectorError) as forbidden:
        await adapter._sync_object(credentials={}, resource=resource)
    assert forbidden.value.code == "permission_lost"


async def test_tos_prefix_sync_uses_stable_content_addressed_revision(monkeypatch):
    resource = SourceResource(
        tenant_id=uuid4(),
        resource_type="tos_prefix",
        name="reports",
        external_id="sales-bucket/reports/",
        visibility="workspace",
        sync_mode="manual",
        status="pending",
    )
    adapter = TosConnectorAdapter()
    monkeypatch.setattr(adapter, "_client", lambda credentials: _FakeTosClient(mode="ok"))

    first = await adapter._sync_prefix(credentials={"region": "cn-beijing"}, resource=resource)
    second = await adapter._sync_prefix(credentials={"region": "cn-beijing"}, resource=resource)

    assert first.external_revision == second.external_revision
    assert first.external_revision.startswith("collection:sha256:")
    assert first.metadata["object_count"] == 2
    assert first.raw_storage_uri == "tos://sales-bucket/reports/"


async def test_feishu_refresh_failure_marks_connection_reauthorization_required(test_session, monkeypatch):
    tenant = await _tenant(test_session)
    encrypted = await CryptoService.encrypt_config(
        {
            "access_token": "expired-access",
            "refresh_token": "expired-refresh",
        },
        test_session,
    )
    connection = SourceConnection(
        tenant_id=tenant.id,
        provider="feishu",
        auth_mode="oauth",
        encrypted_credentials=encrypted,
        external_account_id="ou_1",
        display_name="郝行军的飞书",
        status="connected",
        capabilities_json={"scopes": []},
        token_expires_at=datetime.utcnow() - timedelta(minutes=5),
        created_by=tenant.owner_id,
    )
    test_session.add(connection)
    await test_session.commit()

    from server.services.source_connectors import ConnectorError, FeishuConnectorAdapter

    async def fake_load_config(*, session):
        return {"app_id": "cli_a", "app_secret": "secret", "redirect_uri": "http://127.0.0.1/callback"}

    async def fake_refresh(self, *, config, refresh_token):
        raise ConnectorError("refresh token expired", code="reauthorization_required", permanent=True)

    monkeypatch.setattr("server.services.source_connectors.FeishuAdminConfigService.load_config", fake_load_config)
    monkeypatch.setattr(FeishuConnectorAdapter, "_refresh_token", fake_refresh)

    adapter = FeishuConnectorAdapter()
    with pytest.raises(ConnectorError):
        await adapter.ensure_access_token(session=test_session, connection=connection)

    refreshed = await test_session.get(SourceConnection, connection.id)
    assert refreshed is not None
    assert refreshed.status == "reauthorization_required"


async def test_feishu_drive_permission_error_requires_user_reauthorization(monkeypatch):
    class FakeResponse:
        status_code = 400
        text = ""

        @staticmethod
        def json():
            return {
                "code": 99991679,
                "msg": (
                    "Unauthorized. required one of these privileges under the user identity: "
                    "[drive:drive, drive:drive:readonly, space:document:retrieve]"
                ),
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def request(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("server.services.source_connectors.httpx.AsyncClient", lambda **kwargs: FakeClient())

    adapter = FeishuConnectorAdapter()
    with pytest.raises(ConnectorError) as error:
        await adapter._request_json(
            "GET",
            "/open-apis/drive/v1/files",
            access_token="old-user-token",
        )

    assert error.value.code == "reauthorization_required"
    assert error.value.permanent is True


async def test_feishu_resource_listing_persists_reauthorization_required(test_session):
    tenant = await _tenant(test_session)
    encrypted = await CryptoService.encrypt_config({"access_token": "old-user-token"}, test_session)
    connection = SourceConnection(
        tenant_id=tenant.id,
        provider="feishu",
        auth_mode="oauth",
        encrypted_credentials=encrypted,
        external_account_id="ou_1",
        display_name="Old Feishu authorization",
        status="connected",
        capabilities_json={"scopes": ["docx:document:readonly"]},
        token_expires_at=datetime.utcnow() + timedelta(hours=1),
        created_by=tenant.owner_id,
    )
    test_session.add(connection)
    await test_session.commit()

    class PermissionDeniedAdapter(FakeFeishuConnectorAdapter):
        async def list_resources(self, *, session, input):
            raise ConnectorError(
                "Feishu user authorization does not include Drive read permission",
                code="reauthorization_required",
                permanent=True,
            )

    with pytest.raises(ConnectorError) as error:
        await SourceConnectionService().list_resources(
            session=test_session,
            tenant_id=tenant.id,
            connection_id=connection.id,
            scope="drive",
            parent_token=None,
            resource_type=None,
            query=None,
            page_token=None,
            page_size=50,
            adapter=PermissionDeniedAdapter(),
        )

    assert error.value.code == "reauthorization_required"
    await test_session.refresh(connection)
    assert connection.status == "reauthorization_required"
