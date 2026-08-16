from __future__ import annotations

import os

import pytest
from tests.test_source_connectors_api import _tenant

from server.models.source_connections import SourceConnection
from server.schemas.source_connections import SourceConnectionCreate
from server.schemas.source_resources import SourceResourceImportRequest
from server.services.crypto_service import CryptoService
from server.services.source_connections import SourceConnectionService
from server.services.source_resources import SourceResourceService

pytestmark = pytest.mark.asyncio


def _required_env(names: list[str]) -> dict[str, str]:
    values = {name: os.environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        pytest.skip(f"real source connector E2E requires env vars: {', '.join(missing)}")
    return values


async def test_real_tos_object_source_snapshot_evidence_dataset_e2e(test_session):
    env = _required_env(
        [
            "BYAAN_REAL_TOS_ENDPOINT",
            "BYAAN_REAL_TOS_REGION",
            "BYAAN_REAL_TOS_ACCESS_KEY_ID",
            "BYAAN_REAL_TOS_SECRET_ACCESS_KEY",
            "BYAAN_REAL_TOS_BUCKET",
            "BYAAN_REAL_TOS_OBJECT_KEY",
        ]
    )
    object_key = env["BYAAN_REAL_TOS_OBJECT_KEY"]
    if not object_key.lower().rsplit(".", 1)[-1:] or object_key.lower().rsplit(".", 1)[-1] not in {
        "csv",
        "xlsx",
        "xlsm",
        "json",
        "jsonl",
        "parquet",
    }:
        pytest.skip("BYAAN_REAL_TOS_OBJECT_KEY must point to a CSV/XLSX/JSON/JSONL/Parquet object for Dataset E2E")

    tenant = await _tenant(test_session)
    connection_service = SourceConnectionService()
    resource_service = SourceResourceService()

    connection = await connection_service.create_connection(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceConnectionCreate(
            provider="volcengine_tos",
            auth_mode="access_key",
            display_name="Real TOS E2E",
            credentials={
                "endpoint": env["BYAAN_REAL_TOS_ENDPOINT"],
                "region": env["BYAAN_REAL_TOS_REGION"],
                "access_key_id": env["BYAAN_REAL_TOS_ACCESS_KEY_ID"],
                "secret_access_key": env["BYAAN_REAL_TOS_SECRET_ACCESS_KEY"],
                "default_bucket": env["BYAAN_REAL_TOS_BUCKET"],
            },
        ),
    )

    external_id = f"{env['BYAAN_REAL_TOS_BUCKET']}/{object_key}"
    imported = await resource_service.import_resources(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceResourceImportRequest(
            connection_id=connection.id,
            selections=[
                {
                    "external_id": external_id,
                    "resource_type": "tos_object",
                    "name": object_key.rsplit("/", 1)[-1] or object_key,
                    "selection_config": {},
                }
            ],
        ),
    )

    assert imported["succeeded"] == 1
    resource = imported["results"][0]["resource"]
    assert resource["status"] == "ready"
    assert resource["latest_snapshot"]["raw_storage_uri"].startswith("url:ref:")
    assert resource["latest_snapshot"]["metadata_json"]["bucket"].startswith("tos_bucket:ref:")
    assert resource["latest_snapshot"]["metadata_json"]["key"].startswith("tos_key:ref:")
    assert resource["knowledge_resource"]["evidence_count"] >= 1
    assert resource["projected_dataset_id"]
    projection = resource["sync_config_json"]["projected_dataset"]
    assert projection["status"] == "ready"
    assert projection["source_snapshot_id"] == resource["latest_snapshot_id"]
    assert projection["files"][0]["source_locator"]["bucket_ref"].startswith("tos_bucket:ref:")
    assert projection["files"][0]["source_locator"]["key_ref"].startswith("tos_key:ref:")


async def test_real_feishu_sheet_source_snapshot_evidence_dataset_e2e(test_session):
    env = _required_env(
        [
            "BYAAN_REAL_FEISHU_ACCESS_TOKEN",
            "BYAAN_REAL_FEISHU_SPREADSHEET_TOKEN",
            "BYAAN_REAL_FEISHU_SHEET_ID",
            "BYAAN_REAL_FEISHU_RANGE",
        ]
    )

    tenant = await _tenant(test_session)
    encrypted = await CryptoService.encrypt_config(
        {
            "access_token": env["BYAAN_REAL_FEISHU_ACCESS_TOKEN"],
            "refresh_token": os.environ.get("BYAAN_REAL_FEISHU_REFRESH_TOKEN"),
            "scope": ["sheets:spreadsheet:readonly"],
        },
        test_session,
    )
    connection = SourceConnection(
        tenant_id=tenant.id,
        provider="feishu",
        auth_mode="oauth",
        encrypted_credentials=encrypted,
        external_account_id="real-feishu-e2e",
        display_name="Real Feishu E2E",
        status="connected",
        capabilities_json={"scopes": ["sheets:spreadsheet:readonly"]},
        created_by=tenant.owner_id,
    )
    test_session.add(connection)
    await test_session.commit()
    await test_session.refresh(connection)

    resource_service = SourceResourceService()
    imported = await resource_service.import_resources(
        session=test_session,
        tenant_id=tenant.id,
        user_id=tenant.owner_id,
        payload=SourceResourceImportRequest(
            connection_id=connection.id,
            selections=[
                {
                    "external_id": env["BYAAN_REAL_FEISHU_SPREADSHEET_TOKEN"],
                    "resource_type": "feishu_sheet",
                    "name": "Real Feishu Sheet E2E",
                    "source_url": f"https://example.feishu.cn/sheets/{env['BYAAN_REAL_FEISHU_SPREADSHEET_TOKEN']}",
                    "selection_config": {
                        "sheets": [
                            {
                                "sheet_id": env["BYAAN_REAL_FEISHU_SHEET_ID"],
                                "range": env["BYAAN_REAL_FEISHU_RANGE"],
                            }
                        ]
                    },
                }
            ],
        ),
    )

    assert imported["succeeded"] == 1
    resource = imported["results"][0]["resource"]
    assert resource["status"] == "ready"
    assert resource["knowledge_resource"]["evidence_count"] >= 1
    assert resource["projected_dataset_id"]
    projection = resource["sync_config_json"]["projected_dataset"]
    assert projection["status"] == "ready"
    assert projection["files"][0]["source_locator"]["spreadsheet_ref"].startswith("feishu_spreadsheet:ref:")
    assert projection["files"][0]["source_locator"]["sheet_id"] == env["BYAAN_REAL_FEISHU_SHEET_ID"]
    assert projection["files"][0]["source_locator"]["range"] == env["BYAAN_REAL_FEISHU_RANGE"]
