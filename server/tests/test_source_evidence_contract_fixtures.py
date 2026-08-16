from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from tests.test_source_connectors_api import _tenant

from server.models.datasets import Dataset
from server.models.files import File
from server.models.knowledge_resources import EvidenceFragment
from server.models.source_connections import SourceConnection
from server.models.source_resources import SourceResource
from server.models.source_snapshots import SourceSnapshot
from server.schemas.source_connections import SourceConnectionCreate
from server.schemas.source_resources import SourceResourceImportRequest
from server.services.crypto_service import CryptoService
from server.services.file_operations import DataFrameFileService
from server.services.source_connections import SourceConnectionService
from server.services.source_connectors import (
    CapturedSnapshot,
    ConnectorError,
    ResourceListInput,
    ResourceListResult,
    ResourcePickerItem,
)
from server.services.source_resources import SourceResourceService

pytestmark = pytest.mark.asyncio

FEISHU_TOKEN = "sheet_secret_token_abc123"
FEISHU_ACCESS_TOKEN = "feishu-access-secret"
FEISHU_REFRESH_TOKEN = "feishu-refresh-secret"
FEISHU_FULL_URL = f"https://example.feishu.cn/sheets/{FEISHU_TOKEN}?open_in_browser=true&token=leaky"
TOS_BUCKET = "sensitive-sales-bucket"
TOS_KEY = "private/revenue.csv"
TOS_SECRET_KEY = "tos-secret-key-abc123"
TOS_ACCESS_KEY = "tos-access-key-abc123"

_LEAK_STRINGS = {
    FEISHU_TOKEN,
    FEISHU_ACCESS_TOKEN,
    FEISHU_REFRESH_TOKEN,
    FEISHU_FULL_URL,
    TOS_BUCKET,
    TOS_KEY,
    TOS_SECRET_KEY,
    TOS_ACCESS_KEY,
    "confidential source document body",
}


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _assert_no_sensitive_leaks(value: Any) -> None:
    payload = _json_dump(value)
    for secret in _LEAK_STRINGS:
        assert secret not in payload


@dataclass
class ContractFeishuSheetAdapter:
    mode: str = "ok"
    version: int = 1
    sync_calls: int = 0

    async def test_connection(self, credentials: dict[str, Any]) -> dict[str, Any]:
        if self.mode in {"authorization_failed", "token_expired"}:
            raise ConnectorError(
                f"Feishu authorization failed for access_token={credentials.get('access_token')}",
                code="authorization_required" if self.mode == "authorization_failed" else "reauthorization_required",
                permanent=True,
            )
        return {"account_id": "ou_contract_feishu"}

    async def list_resources(self, *, session, input: ResourceListInput) -> ResourceListResult:
        return ResourceListResult(
            items=[
                ResourcePickerItem(
                    external_id=FEISHU_TOKEN,
                    resource_type="feishu_sheet",
                    name="经营目标表",
                    source_url=FEISHU_FULL_URL,
                    metadata={"spreadsheet_token": FEISHU_TOKEN, "sheets": [{"sheet_id": "sh1", "title": "目标"}]},
                    already_added=FEISHU_TOKEN in input.already_added_external_ids,
                )
            ]
        )

    async def sync_resource(
        self, *, session, connection: SourceConnection, resource: SourceResource
    ) -> CapturedSnapshot:
        self.sync_calls += 1
        if self.mode == "not_found":
            raise ConnectorError(
                f"Feishu sheet not found: {resource.external_id}", code="source_unavailable", permanent=True
            )
        if self.mode == "permission_denied":
            raise ConnectorError(
                f"Feishu permission denied for {FEISHU_FULL_URL}", code="permission_lost", permanent=True
            )
        if self.mode == "timeout":
            raise ConnectorError("Feishu sheet request timed out", code="source_timeout")
        if self.mode == "rate_limited":
            raise ConnectorError("Feishu rate limit exceeded", code="rate_limited")
        if self.mode == "revoked":
            raise ConnectorError(
                f"Feishu grant revoked refresh_token={FEISHU_REFRESH_TOKEN}",
                code="reauthorization_required",
                permanent=True,
            )
        if self.mode == "token_expired":
            raise ConnectorError(
                f"Feishu token expired access_token={FEISHU_ACCESS_TOKEN}",
                code="reauthorization_required",
                permanent=True,
            )

        rows = [["region", "target"], ["East", 120], ["West", 80]]
        if self.version == 2:
            rows = [["region", "target"], ["East", 130], ["West", 90]]
        if self.mode == "parse_failure":
            rows = [["region", "target"], ["East", {"not": "flat"}]]

        raw = {
            "metadata": {"spreadsheet": {"title": "经营目标表"}},
            "sheets": [{"sheet": {"sheet_id": "sh1", "title": "目标"}, "range": "sh1!A1:B3", "values": rows}],
        }
        raw_bytes = json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return CapturedSnapshot(
            raw_bytes=raw_bytes,
            content_text=(
                "Feishu Sheet synced. source_url="
                f"{FEISHU_FULL_URL} access_token={FEISHU_ACCESS_TOKEN} confidential source document body"
            ),
            external_revision=f"rev-{self.version}",
            metadata={
                "provider": "feishu",
                "resource_type": "feishu_sheet",
                "spreadsheet_token": FEISHU_TOKEN,
                "source_url": FEISHU_FULL_URL,
                "access_token": FEISHU_ACCESS_TOKEN,
            },
            provider="byaan-native",
            parser_version="feishu-contract-sheet-v1",
            raw_storage_uri=f"feishu://sheet/{FEISHU_TOKEN}",
        )


@dataclass
class ContractTosAdapter:
    mode: str = "ok"
    version: int = 1
    sync_calls: int = 0

    async def test_connection(self, credentials: dict[str, Any]) -> dict[str, Any]:
        if self.mode == "authorization_failed":
            raise ConnectorError(
                f"TOS authorization failed for secret_access_key={credentials.get('secret_access_key')}",
                code="authorization_required",
                permanent=True,
            )
        return {"account_id": "tos-contract", "endpoint": credentials.get("endpoint")}

    async def list_resources(self, *, session, input: ResourceListInput) -> ResourceListResult:
        return ResourceListResult(
            items=[
                ResourcePickerItem(
                    external_id=f"{TOS_BUCKET}/{TOS_KEY}",
                    resource_type="tos_object",
                    name="revenue.csv",
                    metadata={"bucket": TOS_BUCKET, "key": TOS_KEY, "etag": f"etag-{self.version}"},
                    already_added=f"{TOS_BUCKET}/{TOS_KEY}" in input.already_added_external_ids,
                )
            ]
        )

    async def sync_resource(
        self, *, session, connection: SourceConnection, resource: SourceResource
    ) -> CapturedSnapshot:
        self.sync_calls += 1
        if self.mode == "not_found":
            raise ConnectorError(
                f"TOS object not found: {TOS_BUCKET}/{TOS_KEY}", code="source_unavailable", permanent=True
            )
        if self.mode == "permission_denied":
            raise ConnectorError(f"TOS permission denied for key {TOS_KEY}", code="permission_lost", permanent=True)
        if self.mode == "timeout":
            raise ConnectorError("TOS request timed out", code="source_timeout")
        if self.mode == "rate_limited":
            raise ConnectorError("TOS rate limited", code="rate_limited")
        if self.mode == "revoked":
            raise ConnectorError(
                f"TOS credentials revoked secret_access_key={TOS_SECRET_KEY}",
                code="authorization_required",
                permanent=True,
            )

        raw = b"region,revenue\nEast,120\nWest,80\n" if self.version == 1 else b"region,revenue\nEast,130\nWest,90\n"
        if self.mode == "parse_failure":
            raw = b'region,revenue\nEast,"unterminated\n'
        return CapturedSnapshot(
            raw_bytes=raw,
            content_text=(
                "| region | revenue |\n| --- | --- |\n| East | 120 |\n"
                f"tos_key={TOS_KEY} secret_access_key={TOS_SECRET_KEY}"
            ),
            external_revision=f"etag-{self.version}",
            metadata={
                "provider": "volcengine_tos",
                "bucket": TOS_BUCKET,
                "key": TOS_KEY,
                "etag": f"etag-{self.version}",
                "version_id": f"version-{self.version}",
                "secret_access_key": TOS_SECRET_KEY,
            },
            provider="byaan-native",
            parser_version="tos-contract-csv-v1",
            raw_storage_uri=f"tos://{TOS_BUCKET}/{TOS_KEY}",
        )


async def _feishu_connection(test_session, tenant) -> SourceConnection:
    encrypted = await CryptoService.encrypt_config(
        {
            "access_token": FEISHU_ACCESS_TOKEN,
            "refresh_token": FEISHU_REFRESH_TOKEN,
            "scope": ["sheets:spreadsheet:readonly"],
        },
        test_session,
    )
    connection = SourceConnection(
        tenant_id=tenant.id,
        provider="feishu",
        auth_mode="oauth",
        encrypted_credentials=encrypted,
        external_account_id="ou_contract_feishu",
        display_name="Contract Feishu",
        status="connected",
        capabilities_json={"scopes": ["sheets:spreadsheet:readonly"]},
        token_expires_at=datetime.utcnow() + timedelta(hours=1),
        created_by=tenant.owner_id,
    )
    test_session.add(connection)
    await test_session.commit()
    await test_session.refresh(connection)
    return connection


async def _tos_connection(test_session, tenant, adapter: ContractTosAdapter) -> SourceConnection:
    return await SourceConnectionService().create_connection(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceConnectionCreate(
            provider="volcengine_tos",
            auth_mode="access_key",
            display_name="Contract TOS",
            credentials={
                "endpoint": "https://tos-cn-beijing.volces.com",
                "region": "cn-beijing",
                "access_key_id": TOS_ACCESS_KEY,
                "secret_access_key": TOS_SECRET_KEY,
            },
        ),
        adapter=adapter,
    )


@pytest.mark.parametrize(
    ("adapter", "payload"),
    [
        (
            ContractFeishuSheetAdapter(mode="authorization_failed"),
            SourceConnectionCreate(
                provider="feishu",
                auth_mode="oauth",
                display_name="Rejected Feishu",
                credentials={"access_token": FEISHU_ACCESS_TOKEN},
            ),
        ),
        (
            ContractTosAdapter(mode="authorization_failed"),
            SourceConnectionCreate(
                provider="volcengine_tos",
                auth_mode="access_key",
                display_name="Rejected TOS",
                credentials={
                    "endpoint": "https://tos-cn-beijing.volces.com",
                    "region": "cn-beijing",
                    "access_key_id": TOS_ACCESS_KEY,
                    "secret_access_key": TOS_SECRET_KEY,
                },
            ),
        ),
    ],
)
async def test_contract_authorization_failure_does_not_store_connection_or_leak_sensitive_values(
    test_session,
    adapter,
    payload,
):
    tenant = await _tenant(test_session)

    with pytest.raises(ConnectorError) as exc:
        await SourceConnectionService().create_connection(
            session=test_session,
            tenant_id=tenant.id,
            user_id=tenant.owner_id,
            payload=payload,
            adapter=adapter,
        )

    assert exc.value.code == "authorization_required"
    _assert_no_sensitive_leaks(str(exc.value))
    assert (await test_session.execute(select(SourceConnection))).scalars().all() == []


async def _import_one(
    test_session,
    tenant,
    connection: SourceConnection,
    adapter,
    *,
    resource_type: str,
    external_id: str,
    name: str,
    source_url: str | None = None,
):
    return await SourceResourceService().import_resources(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceResourceImportRequest(
            connection_id=connection.id,
            selections=[
                {
                    "external_id": external_id,
                    "resource_type": resource_type,
                    "name": name,
                    "source_url": source_url,
                }
            ],
        ),
        adapter=adapter,
    )


async def test_feishu_sheet_contract_is_repeatable_versioned_and_redacted(test_session):
    tenant = await _tenant(test_session)
    connection = await _feishu_connection(test_session, tenant)
    adapter = ContractFeishuSheetAdapter()

    imported = await _import_one(
        test_session,
        tenant,
        connection,
        adapter,
        resource_type="feishu_sheet",
        external_id=FEISHU_TOKEN,
        name="经营目标表",
        source_url=FEISHU_FULL_URL,
    )
    resource = imported["results"][0]["resource"]
    assert imported["succeeded"] == 1
    assert resource["status"] == "ready"
    assert resource["projected_dataset_id"]
    first_snapshot_id = resource["latest_snapshot_id"]
    first_dataset_id = resource["projected_dataset_id"]
    dataset = await test_session.get(Dataset, first_dataset_id)
    assert dataset is not None
    table_name = next(iter(json.loads(dataset.schema_cache)["schema"].keys()))

    query = await DataFrameFileService.execute_duckdb_query_on_dataset(
        session=test_session,
        dataset_id=first_dataset_id,
        query=f'SELECT SUM(target) AS total_target FROM "{table_name}"',
        limit=10,
    )
    assert query["success"] is True
    assert query["result"][0]["total_target"] == 200

    evidence = (await test_session.execute(select(EvidenceFragment))).scalars().all()
    snapshots = (await test_session.execute(select(SourceSnapshot))).scalars().all()
    datasets = (await test_session.execute(select(Dataset))).scalars().all()
    assert len(evidence) == 1
    assert len(snapshots) == 1
    assert len(datasets) == 1
    _assert_no_sensitive_leaks(evidence[0].locator_json)
    _assert_no_sensitive_leaks(evidence[0].text)
    _assert_no_sensitive_leaks(snapshots[0].metadata_json)
    _assert_no_sensitive_leaks(resource["sync_config_json"]["projected_dataset"])
    assert "spreadsheet_ref" in evidence[0].locator_json
    assert "spreadsheet_ref" in resource["sync_config_json"]["projected_dataset"]["files"][0]["source_locator"]

    imported_again = await _import_one(
        test_session,
        tenant,
        connection,
        adapter,
        resource_type="feishu_sheet",
        external_id=FEISHU_TOKEN,
        name="经营目标表",
        source_url=FEISHU_FULL_URL,
    )
    assert imported_again["succeeded"] == 1
    assert imported_again["results"][0]["resource"]["latest_snapshot_id"] == first_snapshot_id
    assert len((await test_session.execute(select(SourceSnapshot))).scalars().all()) == 1

    adapter.version = 2
    updated = await _import_one(
        test_session,
        tenant,
        connection,
        adapter,
        resource_type="feishu_sheet",
        external_id=FEISHU_TOKEN,
        name="经营目标表",
        source_url=FEISHU_FULL_URL,
    )
    assert updated["succeeded"] == 1
    assert updated["results"][0]["resource"]["latest_snapshot_id"] != first_snapshot_id
    assert updated["results"][0]["resource"]["projected_dataset_id"] != first_dataset_id
    assert len((await test_session.execute(select(SourceSnapshot))).scalars().all()) == 2


async def test_tos_contract_is_repeatable_versioned_and_redacted(test_session):
    tenant = await _tenant(test_session)
    adapter = ContractTosAdapter()
    connection = await _tos_connection(test_session, tenant, adapter)

    imported = await _import_one(
        test_session,
        tenant,
        connection,
        adapter,
        resource_type="tos_object",
        external_id=f"{TOS_BUCKET}/{TOS_KEY}",
        name="revenue.csv",
    )
    resource = imported["results"][0]["resource"]
    assert imported["succeeded"] == 1
    assert resource["projected_dataset_id"]
    first_snapshot_id = resource["latest_snapshot_id"]

    evidence = (await test_session.execute(select(EvidenceFragment))).scalars().all()
    snapshot = await test_session.get(SourceSnapshot, first_snapshot_id)
    assert snapshot is not None
    _assert_no_sensitive_leaks(evidence[0].locator_json)
    _assert_no_sensitive_leaks(evidence[0].text)
    _assert_no_sensitive_leaks(snapshot.metadata_json)
    _assert_no_sensitive_leaks(resource["sync_config_json"]["projected_dataset"])
    assert "bucket_ref" in evidence[0].locator_json
    assert "key_ref" in evidence[0].locator_json
    assert "bucket_ref" in resource["sync_config_json"]["projected_dataset"]["files"][0]["source_locator"]

    imported_again = await _import_one(
        test_session,
        tenant,
        connection,
        adapter,
        resource_type="tos_object",
        external_id=f"{TOS_BUCKET}/{TOS_KEY}",
        name="revenue.csv",
    )
    assert imported_again["results"][0]["resource"]["latest_snapshot_id"] == first_snapshot_id
    assert len((await test_session.execute(select(SourceSnapshot))).scalars().all()) == 1

    adapter.version = 2
    updated = await _import_one(
        test_session,
        tenant,
        connection,
        adapter,
        resource_type="tos_object",
        external_id=f"{TOS_BUCKET}/{TOS_KEY}",
        name="revenue.csv",
    )
    assert updated["succeeded"] == 1
    assert updated["results"][0]["resource"]["latest_snapshot_id"] != first_snapshot_id
    assert len((await test_session.execute(select(SourceSnapshot))).scalars().all()) == 2


@pytest.mark.parametrize(
    ("adapter_factory", "provider", "auth_mode", "resource_type", "external_id", "name", "source_url", "modes"),
    [
        (
            ContractFeishuSheetAdapter,
            "feishu",
            "oauth",
            "feishu_sheet",
            FEISHU_TOKEN,
            "经营目标表",
            FEISHU_FULL_URL,
            {
                "not_found": "source_unavailable",
                "permission_denied": "permission_lost",
                "timeout": "failed",
                "rate_limited": "failed",
                "revoked": "reauthorization_required",
                "token_expired": "reauthorization_required",
            },
        ),
        (
            ContractTosAdapter,
            "volcengine_tos",
            "access_key",
            "tos_object",
            f"{TOS_BUCKET}/{TOS_KEY}",
            "revenue.csv",
            None,
            {
                "not_found": "source_unavailable",
                "permission_denied": "permission_lost",
                "timeout": "failed",
                "rate_limited": "failed",
                "revoked": "authorization_required",
            },
        ),
    ],
)
async def test_contract_errors_do_not_overwrite_previous_snapshot_or_leak_sensitive_values(
    test_session,
    adapter_factory,
    provider,
    auth_mode,
    resource_type,
    external_id,
    name,
    source_url,
    modes,
):
    tenant = await _tenant(test_session)
    adapter = adapter_factory()
    if provider == "feishu":
        connection = await _feishu_connection(test_session, tenant)
    else:
        connection = await _tos_connection(test_session, tenant, adapter)

    first = await _import_one(
        test_session,
        tenant,
        connection,
        adapter,
        resource_type=resource_type,
        external_id=external_id,
        name=name,
        source_url=source_url,
    )
    previous_snapshot_id = first["results"][0]["resource"]["latest_snapshot_id"]
    previous_evidence_ids = {item.id for item in (await test_session.execute(select(EvidenceFragment))).scalars().all()}

    for mode, expected_status in modes.items():
        adapter.mode = mode
        failed = await _import_one(
            test_session,
            tenant,
            connection,
            adapter,
            resource_type=resource_type,
            external_id=external_id,
            name=name,
            source_url=source_url,
        )
        result = failed["results"][0]
        assert result["status"] == expected_status
        assert result["resource"]["latest_snapshot_id"] == previous_snapshot_id
        assert result["error"] is not None
        assert result["error"]["code"] in {
            "authorization_required",
            "permission_lost",
            "rate_limited",
            "reauthorization_required",
            "source_timeout",
            "source_unavailable",
        }
        _assert_no_sensitive_leaks(result["error"])
        _assert_no_sensitive_leaks(result["resource"]["sync_config_json"]["latest_sync_run"])

    evidence_ids = {item.id for item in (await test_session.execute(select(EvidenceFragment))).scalars().all()}
    assert previous_evidence_ids.issubset(evidence_ids)
    assert len((await test_session.execute(select(SourceSnapshot))).scalars().all()) == 1


async def test_contract_parse_failure_does_not_publish_new_dataset_or_snapshot(test_session):
    tenant = await _tenant(test_session)
    adapter = ContractFeishuSheetAdapter()
    connection = await _feishu_connection(test_session, tenant)

    first = await _import_one(
        test_session,
        tenant,
        connection,
        adapter,
        resource_type="feishu_sheet",
        external_id=FEISHU_TOKEN,
        name="经营目标表",
        source_url=FEISHU_FULL_URL,
    )
    previous_snapshot_id = first["results"][0]["resource"]["latest_snapshot_id"]
    previous_dataset_id = first["results"][0]["resource"]["projected_dataset_id"]

    async def fail_schema(*args, **kwargs):
        raise RuntimeError("parser failure leaked source_url=https://example.feishu.cn/sheets/leaky")

    adapter.mode = "parse_failure"
    original_schema = DataFrameFileService.get_file_schema_multi
    DataFrameFileService.get_file_schema_multi = fail_schema
    try:
        failed = await _import_one(
            test_session,
            tenant,
            connection,
            adapter,
            resource_type="feishu_sheet",
            external_id=FEISHU_TOKEN,
            name="经营目标表",
            source_url=FEISHU_FULL_URL,
        )
    finally:
        DataFrameFileService.get_file_schema_multi = original_schema

    result = failed["results"][0]
    assert result["status"] == "failed"
    assert result["resource"]["latest_snapshot_id"] == previous_snapshot_id
    assert result["resource"]["projected_dataset_id"] == previous_dataset_id
    assert result["error"]["code"] == "dataset_projection_failed"
    _assert_no_sensitive_leaks(result["error"])
    assert len((await test_session.execute(select(SourceSnapshot))).scalars().all()) == 2
    assert len((await test_session.execute(select(Dataset))).scalars().all()) == 1
    assert len((await test_session.execute(select(File))).scalars().all()) == 1
