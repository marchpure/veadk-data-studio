from __future__ import annotations

import asyncio
import difflib
import io
import os
import zipfile
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from server.auth.dependencies import AuthContext, get_current_auth_context
from server.auth.scopes import Scope
from server.data_workshop.skill.repository import SkillWorkbenchRepository
from server.data_workshop.skill.schemas import InvocationCreate, RetryRequest, SessionCreate, SkillCreate
from server.data_workshop.skill.service import (
    ACTIVE_TASKS,
    append_json,
    artifact_url_allowed,
    delegated_auth_ref,
    now_iso,
    public_artifact,
    run_invocation,
    session_payload,
    skill_payload,
    validate_refs,
    visible_catalog,
)
from server.db.session import AsyncSessionFactory, get_async_session
from server.schemas.standard_response import success_response

router = APIRouter(prefix="/v1", tags=["data-workshop-skill"])


async def require_skill_read(
    auth: AuthContext = Depends(get_current_auth_context()),
) -> AuthContext:
    if not auth.has_scope(Scope.CONNECTION_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Skill read permission required")
    return auth


async def require_skill_write(
    auth: AuthContext = Depends(get_current_auth_context()),
) -> AuthContext:
    if auth.is_viewer:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Skill write permission required")
    return auth


def repo_for(db: AsyncSession, auth: AuthContext) -> SkillWorkbenchRepository:
    return SkillWorkbenchRepository(db, auth.tenant_id, auth.user_id)


def get_skill_session_factory() -> async_sessionmaker[AsyncSession]:
    return AsyncSessionFactory


def parse_uuid(value: str, label: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"{label} not found") from exc


async def recover_interrupted(item, db: AsyncSession) -> None:
    if item.status != "running" or str(item.id) in ACTIVE_TASKS:
        return
    item.status = "retryable"
    item.current_invocation_id = None
    append_json(
        item,
        "events_json",
        {
            "id": str(uuid4()),
            "type": "interrupted",
            "code": "INVOCATION_INTERRUPTED",
            "message": "服务重启中断了上次运行，可从当前会话重试。",
            "at": now_iso(),
        },
    )
    await db.commit()
    await db.refresh(item)


@router.get("/skill-catalog")
async def get_catalog(
    auth: AuthContext = Depends(require_skill_read),
    db: AsyncSession = Depends(get_async_session),
):
    data = await visible_catalog(db, auth.tenant_id, auth.user_id, auth.user.email)
    data["backend"] = "TEST BACKEND" if os.getenv("DATA_WORKSHOP_BACKEND_MODE", "REAL").upper() == "TEST" else "REAL"
    data["w5_configured"] = bool(
        os.getenv("W5_SKILL_AGENT_RUNTIME_ID")
        or (os.getenv("W5_SKILL_AGENT_ENDPOINT") and os.getenv("W5_SKILL_AGENT_API_KEY"))
    )
    return success_response(data=data, message="Skill catalog retrieved")


@router.get("/skills")
async def list_skills(
    search: str | None = Query(default=None, max_length=200),
    auth: AuthContext = Depends(require_skill_read),
    db: AsyncSession = Depends(get_async_session),
):
    items = await repo_for(db, auth).list_skills(search)
    return success_response(data={"items": [skill_payload(item) for item in items], "total": len(items)})


@router.post("/skills", status_code=201)
async def create_skill(
    body: SkillCreate,
    auth: AuthContext = Depends(require_skill_write),
    db: AsyncSession = Depends(get_async_session),
):
    repo = repo_for(db, auth)
    catalog = await visible_catalog(db, auth.tenant_id, auth.user_id, auth.user.email)
    try:
        context_refs = validate_refs(body.mcp_refs, body.knowledge_refs, catalog)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if await repo.get_skill_by_target(body.target_skill):
        raise HTTPException(status_code=409, detail="此 target_skill 已存在，请继续修改原 Skill")
    skill = await repo.create_skill(
        title=body.title,
        target_skill=body.target_skill,
        description=body.description,
        context_refs=context_refs,
    )
    work_session = await repo.create_session(
        skill_id=skill.id,
        title="初始会话",
        context_refs=context_refs,
    )
    append_json(
        work_session,
        "events_json",
        {"id": str(uuid4()), "type": "session_created", "message": "会话已创建", "at": now_iso()},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="此 target_skill 已存在") from exc
    await db.refresh(skill)
    await db.refresh(work_session)
    return success_response(
        data={"skill": skill_payload(skill), "session": session_payload(work_session, skill)},
        message="Skill created",
    )


@router.get("/skills/{skill_id}")
async def get_skill(
    skill_id: str,
    auth: AuthContext = Depends(require_skill_read),
    db: AsyncSession = Depends(get_async_session),
):
    item = await repo_for(db, auth).get_skill(parse_uuid(skill_id, "Skill"))
    if item is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return success_response(data=skill_payload(item))


@router.get("/skills/{skill_id}/sessions")
async def list_sessions(
    skill_id: str,
    auth: AuthContext = Depends(require_skill_read),
    db: AsyncSession = Depends(get_async_session),
):
    repo = repo_for(db, auth)
    skill = await repo.get_skill(parse_uuid(skill_id, "Skill"))
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    items = await repo.list_sessions(skill.id)
    for item in items:
        await recover_interrupted(item, db)
    return success_response(data={"items": [session_payload(item, skill) for item in items], "total": len(items)})


@router.post("/skills/{skill_id}/sessions", status_code=201)
async def create_session(
    skill_id: str,
    body: SessionCreate,
    auth: AuthContext = Depends(require_skill_write),
    db: AsyncSession = Depends(get_async_session),
):
    repo = repo_for(db, auth)
    skill = await repo.get_skill(parse_uuid(skill_id, "Skill"))
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    if body.mcp_refs is None and body.knowledge_refs is None:
        context_refs = skill.context_refs_json
    else:
        catalog = await visible_catalog(db, auth.tenant_id, auth.user_id, auth.user.email)
        try:
            context_refs = validate_refs(body.mcp_refs or [], body.knowledge_refs or [], catalog)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    item = await repo.create_session(skill_id=skill.id, title=body.title, context_refs=context_refs)
    skill.updated_at = datetime.now(UTC).replace(tzinfo=None)
    append_json(
        item,
        "events_json",
        {"id": str(uuid4()), "type": "session_created", "message": "会话已创建", "at": now_iso()},
    )
    await db.commit()
    await db.refresh(item)
    return success_response(data=session_payload(item, skill), message="Session created")


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    auth: AuthContext = Depends(require_skill_read),
    db: AsyncSession = Depends(get_async_session),
):
    repo = repo_for(db, auth)
    item = await repo.get_session(parse_uuid(session_id, "Session"))
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await recover_interrupted(item, db)
    skill = await repo.get_skill(item.skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return success_response(data=session_payload(item, skill))


@router.post("/sessions/{session_id}/invocations", status_code=202)
async def invoke(
    session_id: str,
    body: InvocationCreate,
    auth: AuthContext = Depends(require_skill_write),
    db: AsyncSession = Depends(get_async_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_skill_session_factory),
):
    repo = repo_for(db, auth)
    item = await repo.get_session(parse_uuid(session_id, "Session"))
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    skill = await repo.get_skill(item.skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Session not found")
    prior_ids = {event.get("client_invocation_id") for event in (item.events_json or []) if isinstance(event, dict)}
    if body.client_invocation_id in prior_ids:
        return success_response(data=session_payload(item, skill), message="Invocation already accepted")
    if item.status == "running":
        raise HTTPException(status_code=409, detail="Session already has a running invocation")
    item.status = "running"
    skill.status = "running"
    item.current_invocation_id = body.client_invocation_id
    item.last_invocation_json = body.model_dump(by_alias=True)
    flag_modified(item, "last_invocation_json")
    append_json(item, "messages_json", {"role": "user", "content": body.message, "at": now_iso()})
    append_json(
        item,
        "events_json",
        {
            "id": str(uuid4()),
            "type": "invocation_started",
            "client_invocation_id": body.client_invocation_id,
            "message": "W5 已接收任务",
            "at": now_iso(),
        },
    )
    await db.commit()
    await db.refresh(item)
    await db.refresh(skill)
    try:
        auth_ref = delegated_auth_ref(auth)
    except Exception as exc:
        item.status = "blocked_config"
        append_json(
            item,
            "events_json",
            {
                "id": str(uuid4()),
                "type": "blocked_config",
                "code": "BLOCKED_CONFIG",
                "message": str(exc),
                "at": now_iso(),
            },
        )
        await db.commit()
        await db.refresh(item)
        await db.refresh(skill)
        return success_response(data=session_payload(item, skill), message="Invocation blocked")
    task = asyncio.create_task(
        run_invocation(
            tenant_id=auth.tenant_id,
            owner_id=auth.user_id,
            session_id=item.id,
            payload=body,
            delegated_auth=auth_ref,
            session_factory=session_factory,
        )
    )
    ACTIVE_TASKS[str(item.id)] = task
    return success_response(data=session_payload(item, skill), message="Invocation accepted")


@router.get("/sessions/{session_id}/events")
async def events(
    session_id: str,
    after: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(require_skill_read),
    db: AsyncSession = Depends(get_async_session),
):
    repo = repo_for(db, auth)
    item = await repo.get_session(parse_uuid(session_id, "Session"))
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await recover_interrupted(item, db)
    all_events = item.events_json or []
    return success_response(
        data={
            "items": all_events[after:],
            "next": len(all_events),
            "done": item.status != "running",
            "status": item.status,
        }
    )


@router.post("/sessions/{session_id}/cancel")
async def cancel(
    session_id: str,
    auth: AuthContext = Depends(require_skill_write),
    db: AsyncSession = Depends(get_async_session),
):
    repo = repo_for(db, auth)
    item = await repo.get_session(parse_uuid(session_id, "Session"))
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    skill = await repo.get_skill(item.skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Session not found")
    task = ACTIVE_TASKS.get(str(item.id))
    if task:
        task.cancel()
    item.status = "cancelled"
    skill.status = "cancelled"
    item.current_invocation_id = None
    append_json(
        item,
        "events_json",
        {"id": str(uuid4()), "type": "cancelled", "code": "CANCELLED", "message": "已停止", "at": now_iso()},
    )
    await db.commit()
    await db.refresh(item)
    await db.refresh(skill)
    return success_response(data=session_payload(item, skill), message="Invocation cancelled")


@router.post("/sessions/{session_id}/retry", status_code=202)
async def retry(
    session_id: str,
    body: RetryRequest | None = None,
    auth: AuthContext = Depends(require_skill_write),
    db: AsyncSession = Depends(get_async_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_skill_session_factory),
):
    repo = repo_for(db, auth)
    item = await repo.get_session(parse_uuid(session_id, "Session"))
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    skill = await repo.get_skill(item.skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Session not found")
    previous = item.last_invocation_json
    if not previous:
        raise HTTPException(status_code=409, detail="No invocation to retry")
    requested_id = body.client_invocation_id if body and body.client_invocation_id else None
    if requested_id and any(
        event.get("client_invocation_id") == requested_id
        for event in (item.events_json or [])
        if isinstance(event, dict)
    ):
        return success_response(data=session_payload(item, skill), message="Retry already accepted")
    if item.status == "running":
        raise HTTPException(status_code=409, detail="Session already has a running invocation")
    payload = InvocationCreate(
        message=previous["message"],
        run_validation=previous.get("validate", True),
        client_invocation_id=requested_id or f"retry:{uuid4()}",
    )
    item.status = "running"
    skill.status = "running"
    item.current_invocation_id = payload.client_invocation_id
    append_json(
        item,
        "events_json",
        {
            "id": str(uuid4()),
            "type": "retry",
            "client_invocation_id": payload.client_invocation_id,
            "message": "正在重试",
            "at": now_iso(),
        },
    )
    await db.commit()
    await db.refresh(item)
    await db.refresh(skill)
    try:
        auth_ref = delegated_auth_ref(auth)
    except Exception as exc:
        item.status = "blocked_config"
        append_json(
            item,
            "events_json",
            {
                "id": str(uuid4()),
                "type": "blocked_config",
                "code": "BLOCKED_CONFIG",
                "message": str(exc),
                "at": now_iso(),
            },
        )
        await db.commit()
        await db.refresh(item)
        await db.refresh(skill)
        return success_response(data=session_payload(item, skill), message="Invocation blocked")
    task = asyncio.create_task(
        run_invocation(
            tenant_id=auth.tenant_id,
            owner_id=auth.user_id,
            session_id=item.id,
            payload=payload,
            delegated_auth=auth_ref,
            session_factory=session_factory,
        )
    )
    ACTIVE_TASKS[str(item.id)] = task
    return success_response(data=session_payload(item, skill), message="Invocation retry accepted")


@router.get("/skills/{skill_id}/revisions")
async def revisions(
    skill_id: str,
    auth: AuthContext = Depends(require_skill_read),
    db: AsyncSession = Depends(get_async_session),
):
    repo = repo_for(db, auth)
    skill = await repo.get_skill(parse_uuid(skill_id, "Skill"))
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    items = await repo.list_revisions(skill.id)
    items = [item for item in items if item.upstream_artifact_url and artifact_url_allowed(item.upstream_artifact_url)]
    return success_response(
        data={
            "items": [
                {
                    "revision": item.revision,
                    "artifact": public_artifact(skill.id, item.revision, item.artifact_metadata_json),
                    "validation": item.validation_json,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                }
                for item in items
            ],
            "total": len(items),
        }
    )


@router.get("/skills/{skill_id}/revision-diff")
async def revision_diff(
    skill_id: str,
    base: str = Query(min_length=1, max_length=160),
    target: str = Query(min_length=1, max_length=160),
    auth: AuthContext = Depends(require_skill_read),
    db: AsyncSession = Depends(get_async_session),
):
    repo = repo_for(db, auth)
    skill = await repo.get_skill(parse_uuid(skill_id, "Skill"))
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    base_item = await repo.get_revision(skill.id, base)
    target_item = await repo.get_revision(skill.id, target)
    if base_item is None or target_item is None:
        raise HTTPException(status_code=404, detail="Revision not found")
    base_files = set(base_item.artifact_metadata_json.get("files") or [])
    target_files = set(target_item.artifact_metadata_json.get("files") or [])
    changed_fields = sorted(
        key
        for key in set(base_item.artifact_metadata_json) | set(target_item.artifact_metadata_json)
        if base_item.artifact_metadata_json.get(key) != target_item.artifact_metadata_json.get(key)
        and key not in {"download", "download_url", "preview_url", "url", "content"}
    )
    text_diff: list[str] = []
    if base_item.upstream_artifact_url and target_item.upstream_artifact_url and base != target:
        base_name, base_content, _ = preview_from_zip(await fetch_artifact(base_item.upstream_artifact_url))
        target_name, target_content, _ = preview_from_zip(await fetch_artifact(target_item.upstream_artifact_url))
        text_diff = list(
            difflib.unified_diff(
                base_content.decode("utf-8", errors="replace").splitlines(),
                target_content.decode("utf-8", errors="replace").splitlines(),
                fromfile=f"{base}:{base_name}",
                tofile=f"{target}:{target_name}",
                lineterm="",
            )
        )[:1000]
    return success_response(
        data={
            "base": base,
            "target": target,
            "files_added": sorted(target_files - base_files),
            "files_removed": sorted(base_files - target_files),
            "metadata_changed": changed_fields,
            "validation_changed": base_item.validation_json != target_item.validation_json,
            "text_diff": text_diff,
        }
    )


async def fetch_artifact(url: str) -> bytes:
    if not artifact_url_allowed(url):
        raise HTTPException(status_code=502, detail="W5 Artifact URL is not trusted")
    try:
        headers = {"Accept": "application/zip"}
        artifact_token = os.getenv("W5_ARTIFACT_BEARER_TOKEN", "").strip()
        if artifact_token:
            headers["Authorization"] = f"Bearer {artifact_token}"
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            if len(response.content) > 50 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="Artifact exceeds preview limit")
            return response.content
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Artifact download failed") from exc


def safe_zip_names(archive: zipfile.ZipFile) -> list[str]:
    names = []
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        if info.is_dir() or path.is_absolute() or ".." in path.parts or info.file_size > 10 * 1024 * 1024:
            continue
        names.append(info.filename)
    return names


def preview_from_zip(content: bytes) -> tuple[str, bytes, str]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = safe_zip_names(archive)
            selected = next(
                (name for name in names if name.lower().endswith((".html", ".htm"))),
                None,
            ) or next(
                (name for name in names if name.lower().endswith(("skill.md", ".md", ".txt", ".json"))),
                None,
            )
            if selected is None:
                raise HTTPException(status_code=409, detail="Artifact has no safe preview file")
            preview = archive.read(selected)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise HTTPException(status_code=502, detail="W5 Artifact ZIP is invalid") from exc
    media_type = (
        "text/html; charset=utf-8" if selected.lower().endswith((".html", ".htm")) else "text/plain; charset=utf-8"
    )
    return selected, preview, media_type


@router.get("/skills/{skill_id}/revisions/{revision}/{operation}")
async def artifact(
    skill_id: str,
    revision: str,
    operation: str,
    auth: AuthContext = Depends(require_skill_read),
    db: AsyncSession = Depends(get_async_session),
):
    if operation not in {"preview", "download"}:
        raise HTTPException(status_code=404, detail="Artifact operation not found")
    repo = repo_for(db, auth)
    skill = await repo.get_skill(parse_uuid(skill_id, "Skill"))
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    item = await repo.get_revision(skill.id, revision)
    if item is None or not item.upstream_artifact_url:
        raise HTTPException(status_code=404, detail="Artifact not found")
    content = await fetch_artifact(item.upstream_artifact_url)
    if operation == "download":
        return Response(
            content=content,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{skill.target_skill}-artifact.zip"'},
        )
    _, preview, media_type = preview_from_zip(content)
    return Response(
        content=preview,
        media_type=media_type,
        headers={
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )
