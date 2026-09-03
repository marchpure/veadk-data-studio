from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request

app = FastAPI(title="Data Workshop OpenConnector test upstream")

connection = {
    "id": "oracle-prod",
    "name": "Oracle 经营分析库",
    "provider": "Oracle",
    "description": "核心经营数据，只读查询已验证。",
    "status": "ready",
    "action_count": 4,
    "updated_at": "2026-09-04 11:20",
}
actions = [
    {"id": "discover_schema", "name": "发现 Schema", "description": "读取可见表和字段", "risk": "low", "read_only": True},
    {"id": "query_rows", "name": "查询数据", "description": "执行受限 SELECT 查询", "risk": "low", "read_only": True},
    {"id": "export_result", "name": "导出结果", "description": "导出查询结果文件", "risk": "medium", "read_only": True},
    {"id": "refresh_snapshot", "name": "刷新快照", "description": "触发数据快照更新", "risk": "high", "read_only": False},
]
subjects = [
    {"id": "group-finance", "type": "group", "display_name": "财务分析组", "secondary_text": "18 位成员"},
    {"id": "group-ops", "type": "group", "display_name": "运营值班组", "secondary_text": "9 位成员"},
    {"id": "user-alice", "type": "user", "display_name": "Alice Chen", "secondary_text": "alice.chen@example.com"},
]
grants: list[dict[str, Any]] = []
providers = [
    {
        "id": "oracle-prod",
        "name": "Oracle",
        "category": "数据库",
        "description": "企业级关系数据库，支持 Schema 与只读 Actions 发现。",
        "color": "#c74634",
        "available": True,
    },
    {
        "id": "postgresql",
        "name": "PostgreSQL",
        "category": "数据库",
        "description": "连接 PostgreSQL 实例并发现表、视图和查询能力。",
        "color": "#336791",
        "available": True,
    },
]


def check_auth(request: Request) -> None:
    if request.headers.get("authorization") != "Bearer test-admin-token":
        raise HTTPException(status_code=401, detail="admin authentication required")
    if request.headers.get("x-tenant-id") != "00000000-0000-0000-0000-000000000001":
        raise HTTPException(status_code=403, detail="tenant context required")


@app.get("/v1/connections")
async def list_connections(request: Request):
    check_auth(request)
    return {"items": [connection]}


@app.get("/v1/providers")
async def list_providers(request: Request):
    check_auth(request)
    return {"items": providers}


@app.get("/v1/connections/{connection_id}")
async def get_connection(connection_id: str, request: Request):
    check_auth(request)
    if connection_id != connection["id"]:
        raise HTTPException(status_code=404, detail="connection not found")
    return connection


@app.get("/v1/actions")
async def list_actions(connection_id: str, request: Request):
    check_auth(request)
    return {"items": actions if connection_id == connection["id"] else []}


@app.get("/v1/access-grants")
async def list_grants(connection_id: str, request: Request):
    check_auth(request)
    return {"items": [grant for grant in grants if grant["connection_id"] == connection_id]}


@app.get("/v1/identity/subjects")
async def list_subjects(request: Request, query: str = "", subject_type: str = "all"):
    check_auth(request)
    query_lower = query.lower()
    items = [
        subject
        for subject in subjects
        if (subject_type == "all" or subject["type"] == subject_type)
        and (not query_lower or query_lower in subject["display_name"].lower())
    ]
    return {"items": items}


@app.post("/v1/access-grants")
async def create_grant(request: Request):
    check_auth(request)
    payload = await request.json()
    if payload["role_id"] in {"reader", "operator"} and payload["action_scope"]:
        raise HTTPException(status_code=422, detail="predefined role scope must be resolved by OpenConnector")
    if payload["role_id"] == "reader":
        payload["action_scope"] = [action["id"] for action in actions if action["read_only"]]
    elif payload["role_id"] == "operator":
        payload["action_scope"] = [action["id"] for action in actions]
    grant = {
        **payload,
        "id": f"grant-{len(grants) + 1}",
        "status": "active",
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": "林默",
        "version": 1,
    }
    grants.append(grant)
    return grant


@app.patch("/v1/access-grants/{grant_id}")
async def update_grant(grant_id: str, request: Request):
    check_auth(request)
    payload = await request.json()
    if payload["role_id"] in {"reader", "operator"} and payload["action_scope"]:
        raise HTTPException(status_code=422, detail="predefined role scope must be resolved by OpenConnector")
    if payload["role_id"] == "reader":
        payload["action_scope"] = [action["id"] for action in actions if action["read_only"]]
    elif payload["role_id"] == "operator":
        payload["action_scope"] = [action["id"] for action in actions]
    for index, grant in enumerate(grants):
        if grant["id"] == grant_id:
            updated = {**grant, **payload, "version": grant["version"] + 1}
            grants[index] = updated
            return updated
    raise HTTPException(status_code=404, detail="grant not found")


@app.post("/v1/access-grants/{grant_id}:revoke")
async def revoke_grant(grant_id: str, request: Request):
    check_auth(request)
    for grant in grants:
        if grant["id"] == grant_id:
            grant["status"] = "revoked"
            return grant
    raise HTTPException(status_code=404, detail="grant not found")


@app.post("/v1/access:preview")
async def preview_access(request: Request):
    check_auth(request)
    payload = await request.json()
    subject = next(item for item in subjects if item["id"] == payload["subject_id"])
    active_grants = [grant for grant in grants if grant["status"] == "active"]
    allowed_ids = {
        action_id
        for grant in active_grants
        if grant["subject_id"] in {subject["id"], "group-finance"}
        for action_id in grant["action_scope"]
    }
    return {
        "subject": subject,
        "connections": [
            {
                "connection_id": connection["id"],
                "connection_name": connection["name"],
                "actions": [action for action in actions if action["id"] in allowed_ids],
                "reasons": [
                    {"grant_id": grant["id"], "source": f"用户组 {grant['subject_display_snapshot']}", "effect": "allow"}
                    for grant in active_grants
                    if grant["subject_id"] == "group-finance"
                ],
            }
        ],
    }


@app.get("/v1/access/audit")
async def get_audit(request: Request):
    check_auth(request)
    return {
        "items": [
            {
                "id": f"audit-{grant['id']}",
                "event_type": "AccessGrant 创建",
                "subject_display": grant["subject_display_snapshot"],
                "decision": "allow",
                "created_at": grant["updated_at"],
                "request_id": f"req-{grant['id']}",
            }
            for grant in grants
        ]
    }


@app.get("/v1/mcp/config")
async def get_mcp_config(request: Request):
    check_auth(request)
    return {
        "endpoint": "https://mcp.data-workshop.example.com/mcp",
        "protocol": "MCP Streamable HTTP 2025-06-18",
        "workbuddy_config": {
            "name": "Data Workshop",
            "transport": "streamable-http",
            "url": "https://mcp.data-workshop.example.com/mcp",
            "auth": "oauth",
        },
        "api_reference_url": "https://mcp.data-workshop.example.com/docs",
        "openapi_url": "https://mcp.data-workshop.example.com/openapi.json",
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
