from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select

from server.auth.tenant_context import set_tenant_id
from server.models.datasets import Dataset
from server.models.files import File
from server.models.knowledge_resources import EvidenceFragment, KnowledgeResource
from server.models.settings import Setting
from server.models.source_connections import SourceConnection
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
                        "table": {"table_id": "tbl1", "name": "线索"},
                        "fields": {"items": [{"field_name": "region"}, {"field_name": "lead_count"}]},
                        "records": {
                            "items": [
                                {"fields": {"region": "East", "lead_count": 3}},
                                {"fields": {"region": "West", "lead_count": 2}},
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
                },
            },
            provider="byaan-native",
            parser_version="feishu-contract-parser-v1",
            raw_storage_uri=f"feishu://{resource.resource_type}/{resource.external_id}",
        )


class _FakeTosHead:
    def __init__(self, *, size: int = 12, etag: str = '"etag-1"', last_modified: str = "2026-08-14T00:00:00Z"):
        self.content_length = size
        self.etag = etag
        self.last_modified = last_modified


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
    assert by_id["feishu"]["availability"] == "available"
    assert by_id["volcengine_tos"]["availability"] == "available"
    assert by_id["aliyun_oss"]["availability"] == "planned"
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
        scopes=["drive:drive:readonly", "docs:doc:readonly"],
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
    assert "open-apis/authen/v1/authorize" in authorization_url
    assert "app_id=cli_a" in authorization_url
    assert "feishu-secret" not in authorization_url

    async def fake_exchange_code(*, config, code):
        assert code == "oauth-code"
        assert config["app_secret"] == "feishu-secret"
        return {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "scope": ["drive:drive:readonly", "docs:doc:readonly"],
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


async def test_feishu_oauth_state_is_single_use_and_expired_state_is_rejected(test_session):
    tenant = await _tenant(test_session)
    state = FeishuOAuthStateStore.create(
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        redirect_uri="http://127.0.0.1/callback",
    )
    first = FeishuOAuthStateStore.pop(state)
    second = FeishuOAuthStateStore.pop(state)
    assert first is not None
    assert first["tenant_id"] == str(tenant.id)
    assert second is None

    expired_state = FeishuOAuthStateStore.create(
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        redirect_uri="http://127.0.0.1/callback",
    )
    FeishuOAuthStateStore._states[expired_state]["created_at"] = datetime.utcnow() - timedelta(hours=1)
    assert FeishuOAuthStateStore.pop(expired_state) is None


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
