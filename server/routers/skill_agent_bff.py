from __future__ import annotations

import asyncio
import io
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.repositories.custom_skill import CustomSkillRepository
from server.schemas.skill_agent_bff import (
    SkillInvocationCreate,
    SkillRef,
    SkillRetryRequest,
    SkillSessionCreate,
    SkillSessionResponse,
    SkillSessionsResponse,
)
from server.schemas.standard_response import success_response
from server.services.connections import ConnectionService
from server.services.source_resources import SourceResourceService
from server.services.w5_skill_agent_adapter import W5AdapterError, W5Invocation, W5SkillAgentAdapter

router = APIRouter()
_path = Path(os.getenv("SKILL_AGENT_SESSION_STORE", ".data/skill_agent_bff_sessions.json"))
_sessions: dict[str, dict[str, Any]] = {}
_tasks: dict[str, asyncio.Task[None]] = {}
_adapter = W5SkillAgentAdapter()
_backend = os.getenv("SKILL_AGENT_BACKEND", "REAL AGENT").upper()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _persist() -> None:
    _path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _path.with_suffix(".tmp")
    tmp.write_text(json.dumps(_sessions, default=str, separators=(",", ":")))
    tmp.replace(_path)


def _load() -> None:
    global _sessions
    try:
        _sessions = json.loads(_path.read_text())
        changed = False
        for item in _sessions.values():
            if item.get("status") == "running":
                item["status"] = "interrupted"
                item.setdefault("events", []).append({
                    "id": str(uuid4()),
                    "type": "interrupted",
                    "code": "INVOCATION_INTERRUPTED",
                    "message": "The previous backend process stopped before completion. Retry to continue.",
                    "at": _now(),
                })
                changed = True
        if changed:
            _persist()
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        _sessions = {}


_load()


def _public(item: dict[str, Any]) -> dict[str, Any]:
    value = {
        key: value
        for key, value in item.items()
        if key not in {"owner_id", "delegated_auth_ref", "artifact_url", "last_invocation"}
    }
    artifact = value.get("artifact")
    if isinstance(artifact, dict):
        artifact = dict(artifact)
        artifact.pop("download", None)
        if item.get("artifact_url"):
            artifact["download_url"] = f"/api/skill-agent-bff/sessions/{item['id']}/artifact/download"
            artifact["preview_url"] = f"/api/skill-agent-bff/sessions/{item['id']}/artifact/preview"
        else:
            artifact.pop("download_url", None)
            artifact.pop("preview_url", None)
        value["artifact"] = artifact
    return value


def _payload(item: dict[str, Any]) -> dict[str, Any]:
    return _public(item) | {"preview_url": f"/skill/{item['skill_id'] or 'new'}?session={item['id']}"}


async def _catalog(session: AsyncSession, auth: AuthContext) -> tuple[list[SkillRef], list[SkillRef]]:
    rows = await ConnectionService.get_connections_with_names(session)
    rows = await ConnectionService.filter_connections_by_creator_role(rows, auth.user_id, auth.tenant_id, session)
    mcp = []
    for row in rows:
        connection_id = str(row["id"])
        mcp.append(SkillRef(
            id=connection_id,
            kind="connection",
            name=str(row["name"]),
            source="Connection",
            metadata={"type": row["type"], "actions": ["query", "inspect_schema"]},
        ))
    resources = await SourceResourceService().list_resources(session=session, tenant_id=auth.tenant_id)
    knowledge = [
        SkillRef(
            id=str(resource["id"]),
            kind="knowledge_resource",
            name=str(resource["name"]),
            source="OpenViking ResourceRef",
            metadata={"resource_type": resource["resource_type"], "status": resource["status"]},
        )
        for resource in resources
        if resource.get("knowledge_resource")
    ]
    return mcp, knowledge


@router.get("/skill-agent-bff/catalog")
async def catalog(
    auth: AuthContext = Depends(require_scope(Scope.USER_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    mcp, knowledge = await _catalog(session, auth)
    return success_response(data={
        "mcp_refs": [item.model_dump() for item in mcp],
        "knowledge_refs": [item.model_dump() for item in knowledge],
        "backend": "TEST BACKEND" if _backend == "TEST BACKEND" else "REAL AGENT",
    }, message="Skill Agent catalog retrieved")


@router.post("/skill-agent-bff/sessions")
async def create_session(
    payload: SkillSessionCreate,
    auth: AuthContext = Depends(require_scope(Scope.USER_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    if payload.skill_id and not await CustomSkillRepository(session).get(payload.skill_id, auth.tenant_id):
        raise HTTPException(status_code=404, detail="Skill not found")
    visible_mcp, visible_knowledge = await _catalog(session, auth)
    mcp_ids = {ref.id for ref in visible_mcp}
    knowledge_ids = {ref.id for ref in visible_knowledge}
    sid = str(uuid4())
    item = {
        "id": sid,
        "owner_id": str(auth.user_id),
        "skill_id": str(payload.skill_id) if payload.skill_id else None,
        "target": payload.target,
        "mcp_refs": [ref.model_dump() for ref in payload.mcp_refs if ref.id in mcp_ids],
        "knowledge_refs": [ref.model_dump() for ref in payload.knowledge_refs if ref.id in knowledge_ids],
        "delegated_auth_ref": _adapter.delegated_auth_ref(auth),
        "revision": None,
        "messages": [],
        "events": [{"id": str(uuid4()), "type": "session_created", "at": _now()}],
        "artifact": None,
        "status": "idle",
        "backend": "TEST BACKEND" if _backend == "TEST BACKEND" else "REAL AGENT",
    }
    _sessions[sid] = item
    _persist()
    return success_response(data=_payload(item), message="Session created")


def _owned(sid: str, auth: AuthContext) -> dict[str, Any]:
    item = _sessions.get(sid)
    if not item or item["owner_id"] != str(auth.user_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return item


@router.get("/skill-agent-bff/sessions")
async def sessions(auth: AuthContext = Depends(require_scope(Scope.USER_READ))):
    items = [_payload(item) for item in _sessions.values() if item["owner_id"] == str(auth.user_id)]
    return success_response(data=SkillSessionsResponse(items=[SkillSessionResponse.model_validate(item) for item in items], total=len(items)).model_dump(), message="Sessions retrieved")


@router.get("/skill-agent-bff/sessions/{sid}")
async def get_session(sid: str, auth: AuthContext = Depends(require_scope(Scope.USER_READ))):
    item = _owned(sid, auth)
    return success_response(data=_payload(item), message="Session retrieved")


@router.post("/skill-agent-bff/sessions/{sid}/invocations")
async def invoke(sid: str, payload: SkillInvocationCreate, auth: AuthContext = Depends(require_scope(Scope.USER_UPDATE))):
    item = _owned(sid, auth)
    seen = {event.get("client_invocation_id") for event in item["events"]}
    if payload.client_invocation_id in seen:
        return success_response(data=_payload(item), message="Invocation already accepted")
    item["status"] = "running"
    item["messages"].append({"role": "user", "content": payload.message, "at": _now()})
    item["events"].append({"id": str(uuid4()), "type": "invocation_started", "client_invocation_id": payload.client_invocation_id, "at": _now()})
    item["last_invocation"] = payload.model_dump()
    _persist()
    _tasks[sid] = asyncio.create_task(_run(sid, payload))
    return success_response(data=_payload(item), message="Invocation accepted")


async def _run(sid: str, payload: SkillInvocationCreate) -> None:
    item = _sessions.get(sid)
    if not item:
        return
    try:
        if item["backend"] == "TEST BACKEND":
            await _test_run(item, payload)
            return
        invocation = W5Invocation(
            business_goal=payload.message,
            mcp_capability_refs=[ref["id"] for ref in item["mcp_refs"]],
            knowledge_resource_refs=[ref["id"] for ref in item["knowledge_refs"]],
            target_skill=item["target"] or None,
            revision=item["revision"],
            session_id=sid,
            delegated_auth_ref=item.get("delegated_auth_ref"),
        )
        async for raw_event in _adapter.invoke(invocation):
            nested = raw_event.get("events") if isinstance(raw_event.get("events"), list) else [raw_event]
            for source_event in nested:
                event = {**source_event, "id": str(uuid4()), "at": _now()}
                item["events"].append(event)
                _apply_w5_event(item, source_event)
                _persist()
            _apply_w5_event(item, raw_event)
            _persist()
        if item["status"] == "running":
            item["status"] = "ready" if item.get("artifact") else "error"
        item["messages"].append({"role": "assistant", "content": "W5 AgentKit invocation completed.", "at": _now()})
    except W5AdapterError as exc:
        item["status"] = (
            "blocked_auth"
            if exc.code == "BLOCKED_AUTH"
            else "cancelled"
            if exc.code == "CANCELLED"
            else "retryable"
            if exc.retryable
            else "error"
        )
        item["events"].append({
            "id": str(uuid4()),
            "type": "blocked_auth" if exc.code == "BLOCKED_AUTH" else "cancelled" if exc.code == "CANCELLED" else "error",
            "code": exc.code,
            "message": str(exc),
            "at": _now(),
        })
    finally:
        _persist()
        _tasks.pop(sid, None)


def _apply_w5_event(item: dict[str, Any], event: dict[str, Any]) -> None:
    event_type = str(event.get("type", "observation"))
    status = str(event.get("status", "")).upper()
    code = str(event.get("code", "")).upper()
    if event_type in {"validation.blocked", "blocked_auth"} or code == "BLOCKED_AUTH" or status == "BLOCKED_AUTH":
        item["status"] = "blocked_auth"
    elif code in {"VALIDATION_FAILED", "BLOCKED_VALIDATION"} or status == "VALIDATION_FAILED":
        item["status"] = "validation_failed"
    elif status == "CANCELLED" or event_type == "cancelled":
        item["status"] = "cancelled"
    elif status in {"RETRYABLE", "ERROR"}:
        item["status"] = "retryable" if status == "RETRYABLE" else "error"
    elif event_type in {"validation.completed", "validate", "validation"} and event.get("ok") is False:
        item["status"] = "validation_failed"
    if event.get("revision") is not None:
        item["revision"] = str(event["revision"])
    artifact = event.get("artifact")
    if isinstance(artifact, dict):
        item["artifact"] = dict(artifact)
        if artifact.get("revision") is not None:
            item["revision"] = str(artifact["revision"])
        download = artifact.get("download")
        if isinstance(download, dict) and download.get("download_url"):
            item["artifact_url"] = str(download["download_url"])


async def _test_run(item: dict[str, Any], payload: SkillInvocationCreate) -> None:
    item["events"].append({"id": str(uuid4()), "type": "planning", "at": _now()})
    await asyncio.sleep(0)
    if item["status"] == "cancelled":
        return
    item["events"].append({"id": str(uuid4()), "type": "tool_call", "name": "test_backend", "at": _now()})
    if payload.validate and "invalid" in payload.message.lower():
        item["status"] = "validation_failed"
        item["events"].append({"id": str(uuid4()), "type": "validate", "status": "failed", "at": _now()})
        return
    item["revision"] = f"test-rev-{len(item['events'])}"
    item["events"].append({"id": str(uuid4()), "type": "validate", "status": "passed", "at": _now()})
    item["artifact"] = {"name": "SKILL.md", "mime_type": "text/markdown", "content": f"# {item['target'] or 'skill'}\n\n{payload.message}\n", "files": ["SKILL.md"], "source": "TEST BACKEND"}
    item["events"].append({"id": str(uuid4()), "type": "artifact", "at": _now()})
    item["status"] = "ready"


@router.get("/skill-agent-bff/sessions/{sid}/events")
async def events(sid: str, after: int = Query(0, ge=0), auth: AuthContext = Depends(require_scope(Scope.USER_READ))):
    item = _owned(sid, auth)
    deadline = asyncio.get_running_loop().time() + 2
    while after >= len(item["events"]) and item["status"] == "running" and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.02)
    return success_response(data={"items": item["events"][after:], "next": len(item["events"]), "done": item["status"] not in {"running"}}, message="Events retrieved")


@router.post("/skill-agent-bff/sessions/{sid}/cancel")
async def cancel(sid: str, auth: AuthContext = Depends(require_scope(Scope.USER_UPDATE))):
    item = _owned(sid, auth)
    item["status"] = "cancelled"
    item["events"].append({"id": str(uuid4()), "type": "cancelled", "at": _now()})
    task = _tasks.get(sid)
    if task:
        task.cancel()
    _persist()
    return success_response(data=_payload(item), message="Invocation cancelled")


@router.post("/skill-agent-bff/sessions/{sid}/retry")
async def retry(sid: str, payload: SkillRetryRequest | None = None, auth: AuthContext = Depends(require_scope(Scope.USER_UPDATE))):
    item = _owned(sid, auth)
    previous = item.get("last_invocation")
    if not previous:
        item["status"] = "idle"
        return success_response(data=_public(item), message="Session ready to retry")
    retry_payload = SkillInvocationCreate(
        message=previous["message"],
        validate=previous.get("validate", False),
        client_invocation_id=(payload.client_invocation_id if payload and payload.client_invocation_id else f"retry:{uuid4()}"),
    )
    item["status"] = "running"
    item["events"].append({"id": str(uuid4()), "type": "retry", "at": _now()})
    _persist()
    _tasks[sid] = asyncio.create_task(_run(sid, retry_payload))
    return success_response(data=_payload(item), message="Invocation retry accepted")


@router.get("/skill-agent-bff/sessions/{sid}/artifact/{kind}")
async def artifact(sid: str, kind: str, auth: AuthContext = Depends(require_scope(Scope.USER_READ))):
    item = _owned(sid, auth)
    value = item.get("artifact")
    if not value:
        raise HTTPException(status_code=404, detail="Artifact does not exist")
    if kind not in {"preview", "download"}:
        raise HTTPException(status_code=404, detail="Artifact operation not found")
    download_url = item.get("artifact_url")
    if not download_url:
        raise HTTPException(status_code=409, detail="Artifact download is not available from W5")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            remote = await client.get(download_url)
            remote.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Artifact download failed") from exc
    if kind == "download":
        return Response(content=remote.content, media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="skill-artifact.zip"'})
    try:
        with zipfile.ZipFile(io.BytesIO(remote.content)) as archive:
            names = [name for name in archive.namelist() if not name.endswith("/") and not name.startswith("/") and ".." not in name.split("/")]
            preferred = next((name for name in names if name.lower().endswith(("index.html", "skill.md", ".md", ".html", ".txt"))), None)
            if not preferred:
                raise HTTPException(status_code=409, detail="W5 artifact has no previewable HTML or text file")
            content = archive.read(preferred)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise HTTPException(status_code=502, detail="W5 artifact ZIP is invalid") from exc
    media_type = "text/html" if preferred.lower().endswith((".html", ".htm")) else "text/plain"
    return Response(content=content, media_type=media_type)
