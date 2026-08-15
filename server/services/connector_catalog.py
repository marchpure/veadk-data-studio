from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ConnectorAvailability = Literal["available", "beta", "planned"]
ConnectorAuthMode = Literal["oauth", "access_key", "connection_string", "none"]


@dataclass(frozen=True)
class ConnectorDefinition:
    id: str
    category: str
    display_name: str
    icon: str
    auth_mode: ConnectorAuthMode
    capabilities: tuple[str, ...]
    config_schema: dict[str, Any]
    resource_picker_schema: dict[str, Any]
    supported_resource_types: tuple[str, ...]
    availability: ConnectorAvailability
    description: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "display_name": self.display_name,
            "icon": self.icon,
            "auth_mode": self.auth_mode,
            "capabilities": list(self.capabilities),
            "config_schema": self.config_schema,
            "resource_picker_schema": self.resource_picker_schema,
            "supported_resource_types": list(self.supported_resource_types),
            "availability": self.availability,
            "description": self.description,
        }


def _field(name: str, field_type: str, *, required: bool = True, secret: bool = False) -> dict[str, Any]:
    return {"name": name, "type": field_type, "required": required, "secret": secret}


def _planned(
    *,
    id: str,
    category: str,
    display_name: str,
    icon: str,
    auth_mode: ConnectorAuthMode,
    capabilities: tuple[str, ...] = (),
    planned_adapter: str | None = None,
) -> ConnectorDefinition:
    return ConnectorDefinition(
        id=id,
        category=category,
        display_name=display_name,
        icon=icon,
        auth_mode=auth_mode,
        capabilities=capabilities,
        config_schema={"fields": []},
        resource_picker_schema={"planned_adapter": planned_adapter} if planned_adapter else {},
        supported_resource_types=(),
        availability="planned",
    )


CONNECTOR_CATALOG: tuple[ConnectorDefinition, ...] = (
    ConnectorDefinition(
        id="feishu",
        category="documents",
        display_name="飞书文档 / Wiki / Sheets / Base",
        icon="feishu",
        auth_mode="oauth",
        capabilities=(
            "oauth_authorization_code",
            "token_refresh",
            "resource_browse",
            "resource_search",
            "multi_select_import",
            "snapshot_sync",
            "knowledge_evidence",
        ),
        config_schema={
            "admin_fields": [
                _field("app_id", "string"),
                _field("app_secret", "string", secret=True),
                _field("redirect_uri", "url"),
                _field("scopes", "string[]", required=False),
            ]
        },
        resource_picker_schema={
            "scopes": ["recent", "drive", "wiki", "search"],
            "supports_children": True,
            "supports_pagination": True,
            "supports_multi_select": True,
        },
        supported_resource_types=("feishu_doc", "feishu_wiki", "feishu_sheet", "feishu_base"),
        availability="available",
        description="一次 OAuth 授权后重复浏览、选择和同步飞书资源。",
    ),
    ConnectorDefinition(
        id="volcengine_tos",
        category="object_storage",
        display_name="火山引擎 TOS",
        icon="tos",
        auth_mode="access_key",
        capabilities=(
            "test_connection",
            "bucket_browse",
            "prefix_browse",
            "object_import",
            "prefix_import",
            "etag_idempotency",
            "snapshot_sync",
            "knowledge_evidence",
        ),
        config_schema={
            "fields": [
                _field("endpoint", "url"),
                _field("region", "string"),
                _field("access_key_id", "string", secret=True),
                _field("secret_access_key", "string", secret=True),
                _field("session_token", "string", required=False, secret=True),
                _field("default_bucket", "string", required=False),
                _field("default_prefix", "string", required=False),
                _field("verify_ssl", "boolean", required=False),
            ]
        },
        resource_picker_schema={
            "hierarchy": ["bucket", "prefix", "object"],
            "supports_children": True,
            "supports_pagination": True,
            "supports_multi_select": True,
            "supports_prefix_import": True,
        },
        supported_resource_types=("tos_bucket", "tos_prefix", "tos_object"),
        availability="available",
        description="连接火山引擎 TOS 后浏览 Bucket/Prefix/Object 并同步对象内容。",
    ),
    _planned(
        id="aliyun_oss",
        category="object_storage",
        display_name="阿里云 OSS",
        icon="oss",
        auth_mode="access_key",
        capabilities=("object_storage_contract",),
        planned_adapter="object_storage",
    ),
    _planned(
        id="tencent_cos",
        category="object_storage",
        display_name="腾讯云 COS",
        icon="cos",
        auth_mode="access_key",
        capabilities=("object_storage_contract",),
        planned_adapter="object_storage",
    ),
    _planned(
        id="huawei_obs",
        category="object_storage",
        display_name="华为云 OBS",
        icon="obs",
        auth_mode="access_key",
        capabilities=("object_storage_contract",),
        planned_adapter="object_storage",
    ),
    _planned(
        id="minio_s3",
        category="object_storage",
        display_name="MinIO / S3 Compatible",
        icon="s3",
        auth_mode="access_key",
        capabilities=("object_storage_contract",),
        planned_adapter="object_storage",
    ),
    _planned(
        id="dingtalk_docs",
        category="documents",
        display_name="钉钉文档 / 表格 / 宜搭",
        icon="dingtalk",
        auth_mode="oauth",
        capabilities=("oauth_picker_contract",),
        planned_adapter="oauth_picker",
    ),
    _planned(
        id="tencent_docs",
        category="documents",
        display_name="腾讯文档",
        icon="tencent-docs",
        auth_mode="oauth",
        capabilities=("oauth_picker_contract",),
        planned_adapter="oauth_picker",
    ),
    _planned(
        id="wechat_work_files",
        category="documents",
        display_name="企业微信文件",
        icon="wechat-work",
        auth_mode="oauth",
        capabilities=("oauth_picker_contract",),
        planned_adapter="oauth_picker",
    ),
    _planned(
        id="oceanbase",
        category="databases",
        display_name="OceanBase",
        icon="database",
        auth_mode="connection_string",
        capabilities=("mysql_protocol_planned",),
    ),
    _planned(
        id="tidb",
        category="databases",
        display_name="TiDB",
        icon="database",
        auth_mode="connection_string",
        capabilities=("mysql_protocol_planned",),
    ),
    _planned(
        id="polardb_mysql",
        category="databases",
        display_name="PolarDB MySQL",
        icon="database",
        auth_mode="connection_string",
        capabilities=("mysql_protocol_planned",),
    ),
    _planned(
        id="polardb_postgresql",
        category="databases",
        display_name="PolarDB PostgreSQL",
        icon="database",
        auth_mode="connection_string",
        capabilities=("postgres_protocol_planned",),
    ),
    _planned(
        id="opengauss",
        category="databases",
        display_name="openGauss / GaussDB",
        icon="database",
        auth_mode="connection_string",
        capabilities=("postgres_protocol_planned",),
    ),
    _planned(
        id="dameng_dm",
        category="databases",
        display_name="达梦 DM",
        icon="database",
        auth_mode="connection_string",
        capabilities=("sql_dialect_planned",),
    ),
    _planned(
        id="kingbase_es",
        category="databases",
        display_name="人大金仓 KingbaseES",
        icon="database",
        auth_mode="connection_string",
        capabilities=("postgres_protocol_planned",),
    ),
    _planned(
        id="clickhouse",
        category="databases",
        display_name="ClickHouse",
        icon="database",
        auth_mode="connection_string",
        capabilities=("sql_dialect_planned",),
    ),
    _planned(
        id="apache_doris",
        category="databases",
        display_name="Apache Doris",
        icon="database",
        auth_mode="connection_string",
        capabilities=("mysql_protocol_planned",),
    ),
    _planned(
        id="starrocks",
        category="databases",
        display_name="StarRocks",
        icon="database",
        auth_mode="connection_string",
        capabilities=("mysql_protocol_planned",),
    ),
    _planned(
        id="bytehouse",
        category="databases",
        display_name="ByteHouse",
        icon="database",
        auth_mode="connection_string",
        capabilities=("sql_dialect_planned",),
    ),
    _planned(
        id="maxcompute",
        category="databases",
        display_name="MaxCompute",
        icon="database",
        auth_mode="connection_string",
        capabilities=("sql_dialect_planned",),
    ),
    _planned(
        id="hologres",
        category="databases",
        display_name="Hologres",
        icon="database",
        auth_mode="connection_string",
        capabilities=("postgres_protocol_planned",),
    ),
    _planned(
        id="analyticdb",
        category="databases",
        display_name="AnalyticDB",
        icon="database",
        auth_mode="connection_string",
        capabilities=("sql_dialect_planned",),
    ),
    _planned(
        id="hive_trino",
        category="databases",
        display_name="Hive / Trino",
        icon="database",
        auth_mode="connection_string",
        capabilities=("sql_dialect_planned",),
    ),
    _planned(
        id="volcengine_las",
        category="data_lake",
        display_name="火山引擎 LAS",
        icon="lake",
        auth_mode="access_key",
    ),
    _planned(
        id="kafka",
        category="messages",
        display_name="Kafka",
        icon="message",
        auth_mode="connection_string",
    ),
    _planned(
        id="rocketmq",
        category="messages",
        display_name="RocketMQ",
        icon="message",
        auth_mode="connection_string",
    ),
    _planned(
        id="elasticsearch",
        category="search",
        display_name="Elasticsearch / OpenSearch",
        icon="search",
        auth_mode="connection_string",
    ),
)


def list_connector_definitions() -> list[dict[str, Any]]:
    return [definition.to_payload() for definition in CONNECTOR_CATALOG]


def get_connector_definition(provider: str) -> ConnectorDefinition | None:
    return next((item for item in CONNECTOR_CATALOG if item.id == provider), None)


def available_resource_types() -> set[str]:
    values: set[str] = set()
    for definition in CONNECTOR_CATALOG:
        if definition.availability == "available":
            values.update(definition.supported_resource_types)
    return values
