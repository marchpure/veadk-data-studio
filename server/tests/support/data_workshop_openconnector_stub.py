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


def check_admin_auth(request: Request) -> None:
    if request.headers.get("authorization") != "Bearer test-admin-token":
        raise HTTPException(status_code=401, detail="admin authentication required")
    if request.headers.get("x-tenant-id") != "00000000-0000-0000-0000-000000000001":
        raise HTTPException(status_code=403, detail="tenant context required")


def check_runtime_auth(request: Request) -> None:
    if request.headers.get("authorization") != "Bearer test-runtime-token":
        raise HTTPException(status_code=401, detail="runtime authentication required")


@app.get("/health")
async def health():
    return {"ok": True, "runtime": "openconnector"}


@app.get("/api/connections")
async def list_connections(request: Request):
    check_admin_auth(request)
    return [connection]


@app.get("/api/providers")
async def list_providers(request: Request):
    check_admin_auth(request)
    return providers


@app.get("/api/actions")
async def list_actions(request: Request, service: str | None = None):
    check_admin_auth(request)
    return actions if service in {None, connection["service"]} else []


@app.get("/api/access-grants")
async def list_grants(request: Request):
    check_admin_auth(request)
    return grants


@app.get("/api/identity/subjects")
async def list_subjects(request: Request):
    check_admin_auth(request)
    return subjects


@app.post("/api/access-grants")
async def create_grant(request: Request):
    check_admin_auth(request)
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


@app.patch("/api/access-grants/{grant_id}")
async def update_grant(grant_id: str, request: Request):
    check_admin_auth(request)
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


@app.post("/api/access-grants/{grant_id}/revoke")
async def revoke_grant(grant_id: str, request: Request):
    check_admin_auth(request)
    for grant in grants:
        if grant["id"] == grant_id:
            grant["revokedAt"] = datetime.now(UTC).isoformat()
            return grant
    raise HTTPException(status_code=404, detail="grant not found")


@app.post("/api/access/preview")
async def preview_access(request: Request):
    check_admin_auth(request)
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


@app.get("/api/access/audit")
async def get_audit(request: Request):
    check_admin_auth(request)
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


@app.get("/api/identity-provider")
async def get_identity(request: Request):
    check_admin_auth(request)
    return {
        "status": "ready",
        "issuer": "https://identity.example.com/tenant/dw",
        "audience": ["data-workshop"],
        "jwksUri": "https://identity.example.com/tenant/dw/.well-known/jwks.json",
        "user_pool_ref": "dw-enterprise-users",
        "jwks_status": "healthy",
    }


@app.get("/openapi.json")
async def get_openapi(request: Request):
    check_admin_auth(request)
    return {"openapi": "3.1.0", "info": {"title": "OpenConnector", "version": "test"}}


@app.post("/mcp")
async def mcp(request: Request):
    check_runtime_auth(request)
    payload = await request.json()
    if payload.get("method") == "tools/list":
        result = {
            "tools": [
                {"name": "list_apps"},
                {"name": "list_connections"},
                {"name": "search_actions"},
                {"name": "get_action_guide"},
                {"name": "execute_action"},
            ]
        }
    elif payload.get("method") == "tools/call" and payload.get("params", {}).get("name") == "list_connections":
        result = {"content": [], "structuredContent": {"ok": True, "data": [connection]}}
    else:
        raise HTTPException(status_code=400, detail="unsupported MCP test operation")
    return {"jsonrpc": "2.0", "id": payload.get("id"), "result": result}


@app.get("/{console_path:path}")
async def console(console_path: str, request: Request):
    check_admin_auth(request)
    return {
        "console": console_path or "home",
        "embed": request.query_params.get("embed"),
    }
