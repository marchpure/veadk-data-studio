from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request

app = FastAPI(title="Data Workshop OpenConnector test upstream")
PUBLIC_ORIGIN = "https://s4j054gh1e125mqsipi2e.apigateway-cn-beijing.volceapi.com"

connection = {
    "id": "oracle-prod",
    "service": "oracle",
    "status": "active",
    "alias": "经营分析库",
    "authType": "custom_credential",
    "displayName": "Oracle 经营分析库",
    "accountLabel": "Oracle 经营分析库",
    "isDefault": True,
    "scopes": [],
}
actions = [
    {"id": "discover_schema", "service": "oracle", "name": "discover_schema", "description": "读取可见表和字段"},
    {"id": "query_rows", "service": "oracle", "name": "query_rows", "description": "执行受限 SELECT 查询"},
    {"id": "export_result", "service": "oracle", "name": "export_result", "description": "导出查询结果文件"},
    {"id": "refresh_snapshot", "service": "oracle", "name": "refresh_snapshot", "description": "触发数据快照更新"},
]
subjects = [
    {
        "issuer": "https://identity.example.com/tenant/dw",
        "audience": "data-workshop",
        "userPoolRef": "dw-enterprise-users",
        "sub": "user-alice",
        "groups": ["财务分析组", "运营值班组"],
    },
]
grants: list[dict[str, Any]] = []
providers = [
    {
        "service": "oracle",
        "displayName": "Oracle",
        "categories": [{"id": "数据库", "displayName": "数据库"}],
        "scenario": "企业级关系数据库",
        "authTypes": ["custom_credential"],
    },
    {
        "service": "postgresql",
        "displayName": "PostgreSQL",
        "categories": [{"id": "数据库", "displayName": "数据库"}],
        "scenario": "连接 PostgreSQL 实例",
        "authTypes": ["custom_credential"],
    },
]


def check_auth(request: Request) -> None:
    if request.headers.get("authorization") != "Bearer test-admin-token":
        raise HTTPException(status_code=401, detail="admin authentication required")
    if request.headers.get("x-tenant-id") != "00000000-0000-0000-0000-000000000001":
        raise HTTPException(status_code=403, detail="tenant context required")


@app.get("/v1/health")
async def runtime_health(request: Request):
    check_auth(request)
    return {"ok": True, "runtime": "openconnector"}


@app.get("/v1/apps")
async def list_connections(request: Request):
    check_auth(request)
    return {"items": [connection]}


@app.get("/v1/connections")
async def list_connections_v3(request: Request):
    check_auth(request)
    return {"items": [connection]}


@app.get("/v1/providers")
async def list_providers(request: Request):
    check_auth(request)
    return {"items": providers}


@app.get("/v1/actions")
async def list_actions(request: Request, service: str | None = None):
    check_auth(request)
    return {"items": actions if service in {None, connection["service"]} else []}


@app.get("/v1/access-grants")
async def list_grants(request: Request):
    check_auth(request)
    return {"items": grants}


@app.get("/v1/identity/subjects")
async def list_subjects(request: Request):
    check_auth(request)
    return {"items": subjects}


@app.post("/v1/access-grants")
async def create_grant(request: Request):
    check_auth(request)
    payload = await request.json()
    if payload["role"] in {"reader", "operator"} and payload["customActions"]:
        raise HTTPException(status_code=422, detail="predefined role scope must be resolved by OpenConnector")
    if payload["role"] == "reader":
        payload["customActions"] = [
            action["id"] for action in actions if action["name"].startswith(("get", "list", "query", "discover"))
        ]
    elif payload["role"] == "operator":
        payload["customActions"] = [action["id"] for action in actions]
    grant = {
        **payload,
        "id": f"grant-{len(grants) + 1}",
        "createdAt": datetime.now(UTC).isoformat(),
        "updatedAt": datetime.now(UTC).isoformat(),
    }
    grants.append(grant)
    return grant


@app.patch("/v1/access-grants/{grant_id}")
async def update_grant(grant_id: str, request: Request):
    check_auth(request)
    payload = await request.json()
    if payload["role"] in {"reader", "operator"} and payload["customActions"]:
        raise HTTPException(status_code=422, detail="predefined role scope must be resolved by OpenConnector")
    if payload["role"] == "reader":
        payload["customActions"] = [
            action["id"] for action in actions if action["name"].startswith(("get", "list", "query", "discover"))
        ]
    elif payload["role"] == "operator":
        payload["customActions"] = [action["id"] for action in actions]
    for index, grant in enumerate(grants):
        if grant["id"] == grant_id:
            updated = {**grant, **payload, "updatedAt": datetime.now(UTC).isoformat()}
            grants[index] = updated
            return updated
    raise HTTPException(status_code=404, detail="grant not found")


@app.post("/v1/access-grants/{grant_id}:revoke")
async def revoke_grant(grant_id: str, request: Request):
    check_auth(request)
    for grant in grants:
        if grant["id"] == grant_id:
            grant["revokedAt"] = datetime.now(UTC).isoformat()
            return grant
    raise HTTPException(status_code=404, detail="grant not found")


@app.post("/v1/access:preview")
async def preview_access(request: Request):
    check_auth(request)
    payload = await request.json()
    subject = payload["subject"]
    action = next(item for item in actions if item["id"] == payload["actionId"])
    active_grants = [grant for grant in grants if not grant.get("revokedAt")]
    matching = [
        grant
        for grant in active_grants
        if grant["connectionId"] == payload["connectionId"]
        and (
            grant["subjectType"] == "user"
            and grant["subject"] == subject["sub"]
            or grant["subjectType"] == "group"
            and grant["subject"] in subject["groups"]
        )
    ]
    allowed = any(
        grant["effect"] == "allow"
        and (
            grant["role"] == "operator"
            or grant["role"] == "reader"
            and action["name"].startswith(("get", "list", "query", "discover"))
            or grant["role"] == "custom"
            and action["id"] in grant["customActions"]
        )
        for grant in matching
    )
    return {
        "subject": subject,
        "connectionId": payload["connectionId"],
        "actionId": payload["actionId"],
        "decision": {
            "allowed": allowed,
            "checks": [
                {
                    "source": "access_grant",
                    "outcome": "allow_match",
                    "grantId": grant["id"],
                    "role": grant["role"],
                    "reason": f"用户组 {grant['subject']}",
                }
                for grant in matching
            ],
        },
        "policyVersion": len(grants),
    }


@app.get("/v1/access/audit")
async def get_audit(request: Request):
    check_auth(request)
    return {
        "items": [
            {
                "id": f"audit-{grant['id']}",
                "subject": subjects[0],
                "connectionId": grant["connectionId"],
                "decision": {
                    "allowed": grant["effect"] == "allow",
                    "checks": [{"source": "access_grant", "outcome": "allow_match", "grantId": grant["id"]}],
                },
                "createdAt": grant["updatedAt"],
            }
            for grant in grants
        ]
    }


@app.get("/v1/mcp/config")
async def get_mcp_config(request: Request):
    check_auth(request)
    return {
        "endpoint": f"{PUBLIC_ORIGIN}/mcp",
        "protocol": "MCP Streamable HTTP 2025-06-18",
        "workbuddy_config": {
            "name": "Data Workshop",
            "transport": "streamable-http",
            "url": f"{PUBLIC_ORIGIN}/mcp",
            "auth": "oauth",
        },
        "api_reference_url": f"{PUBLIC_ORIGIN}/docs",
        "openapi_url": f"{PUBLIC_ORIGIN}/openapi.json",
        "sdk_languages": ["Python", "TypeScript"],
    }


@app.get("/v1/identity-provider")
async def get_identity(request: Request):
    check_auth(request)
    return {
        "status": "ready",
        "issuer": "https://identity.example.com/tenant/dw",
        "audience": ["data-workshop"],
        "user_pool_ref": "dw-enterprise-users",
        "jwks_status": "healthy",
    }


@app.get("/v1/mcp/status")
async def get_mcp_status(request: Request):
    check_auth(request)
    return {"status": "healthy", "protocol": "streamable-http", "checked_at": "2026-09-04T00:00:00Z"}


@app.post("/v1/mcp/tests/tools-list")
async def test_tools_list(request: Request):
    check_auth(request)
    return {
        "tools": [
            {"name": "list_apps"},
            {"name": "list_connections"},
            {"name": "search_actions"},
            {"name": "get_action_guide"},
            {"name": "execute_action"},
        ],
        "filtered_by": "AccessGrant",
    }


@app.post("/v1/mcp/tests/read-only")
async def test_read_only(request: Request):
    check_auth(request)
    return {"connections": [{"id": connection["id"], "name": connection["name"]}], "read_only": True}


@app.get("/{console_path:path}")
async def console(console_path: str, request: Request):
    check_auth(request)
    return {
        "console": console_path or "home",
        "embed": request.query_params.get("embed"),
    }
