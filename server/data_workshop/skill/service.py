from __future__ import annotations

import asyncio
import importlib
import inspect
import os
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlparse
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from server.data_workshop.api import _action_view, _items, _list_apps, _subject_views, get_openconnector_client
from server.data_workshop.skill.repository import SkillWorkbenchRepository
from server.data_workshop.skill.schemas import ContextRef, InvocationCreate
from server.data_workshop.skill.w5_adapter import W5AdapterError, W5Invocation, W5SkillAgentAdapter
from server.db.session import AsyncSessionFactory
from server.models.data_workshop_skill import DataWorkshopSkill, DataWorkshopSkillSession
from server.models.knowledge_resources import KnowledgeResource
from server.models.source_resources import SourceResource

ACTIVE_TASKS: dict[str, asyncio.Task[None]] = {}
BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|credential)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def append_json(item: Any, attribute: str, value: dict[str, Any]) -> None:
    values = list(getattr(item, attribute) or [])
    values.append(value)
    setattr(item, attribute, values)
    flag_modified(item, attribute)


def public_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        allowed = {
            "checks",
            "code",
            "created_at",
            "errors",
            "files",
            "kind",
            "label",
            "manifest",
            "message",
            "mime_type",
            "name",
            "ok",
            "revision",
            "sha256",
            "size",
            "status",
            "summary",
            "skill_slug",
            "validation",
            "zip_size",
        }
        return {key: redact_nested(item) for key, item in value.items() if key.casefold() in allowed}
    if isinstance(value, list):
        return [redact_nested(item) for item in value]
    return value


def redact_nested(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: redact_nested(item)
            for key, item in value.items()
            if not any(marker in key.casefold() for marker in ("token", "secret", "credential", "api_key"))
            and key.casefold() not in {"authorization", "url", "download_url", "preview_url"}
        }
    if isinstance(value, list):
        return [redact_nested(item) for item in value]
    if isinstance(value, str):
        redacted = BEARER_PATTERN.sub("Bearer [REDACTED]", value)
        return SECRET_ASSIGNMENT_PATTERN.sub(r"\1\2[REDACTED]", redacted)
    return value


def artifact_metadata(value: dict[str, Any]) -> dict[str, Any]:
    return public_metadata(value)


def artifact_url_allowed(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    configured = urlparse(os.getenv("W5_SKILL_AGENT_ENDPOINT", "")).hostname
    allowed = {host.strip().lower() for host in os.getenv("W5_ARTIFACT_HOSTS", "").split(",") if host.strip()}
    if configured:
        allowed.add(configured.lower())
    return parsed.hostname.lower() in allowed


def safe_event(value: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "checks",
        "client_invocation_id",
        "code",
        "message",
        "name",
        "ok",
        "phase",
        "progress",
        "status",
        "summary",
        "text",
        "type",
        "validation",
        "value",
    }
    return {
        key: redact_nested(item)
        for key, item in value.items()
        if key.casefold() in allowed
        and not any(marker in key.casefold() for marker in ("token", "secret", "credential"))
    }


def public_artifact(skill_id: UUID, revision: str, metadata: dict[str, Any]) -> dict[str, Any]:
    safe = public_metadata(metadata)
    safe["revision"] = revision
    encoded_revision = quote(revision, safe="")
    safe["preview_url"] = f"/api/v1/skills/{skill_id}/revisions/{encoded_revision}/preview"
    safe["download_url"] = f"/api/v1/skills/{skill_id}/revisions/{encoded_revision}/download"
    return safe


def skill_payload(skill: DataWorkshopSkill) -> dict[str, Any]:
    artifact = None
    if skill.active_revision and skill.artifact_metadata_json and skill.artifact_metadata_json.get("_proxy_ready"):
        artifact = public_artifact(skill.id, skill.active_revision, skill.artifact_metadata_json)
    return {
        "id": str(skill.id),
        "target_skill": skill.target_skill,
        "title": skill.title,
        "description": skill.description,
        "status": skill.status,
        "context_refs": skill.context_refs_json or {"mcp_refs": [], "knowledge_refs": []},
        "active_revision": skill.active_revision,
        "artifact": artifact,
        "created_at": skill.created_at.isoformat() if skill.created_at else None,
        "updated_at": skill.updated_at.isoformat() if skill.updated_at else None,
    }


def session_payload(item: DataWorkshopSkillSession, skill: DataWorkshopSkill) -> dict[str, Any]:
    artifact = None
    if item.active_revision and item.artifact_metadata_json and item.artifact_metadata_json.get("_proxy_ready"):
        artifact = public_artifact(skill.id, item.active_revision, item.artifact_metadata_json)
    return {
        "id": str(item.id),
        "skill_id": str(item.skill_id),
        "title": item.title,
        "status": item.status,
        "context_refs": item.context_refs_json or {"mcp_refs": [], "knowledge_refs": []},
        "messages": item.messages_json or [],
        "events": item.events_json or [],
        "current_invocation_id": item.current_invocation_id,
        "active_revision": item.active_revision,
        "artifact": artifact,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


async def visible_catalog(
    session: AsyncSession,
    tenant_id: UUID,
    owner_id: UUID,
    owner_email: str | None = None,
) -> dict[str, Any]:
    """Return only references whose access can be established for this user."""
    client = get_openconnector_client()
    connections: list[dict[str, Any]] = []
    try:
        raw_connections = await _list_apps(client, str(tenant_id))
        raw_actions = _items(await client.request_admin("GET", "/api/actions", tenant_id=str(tenant_id)))
        subjects = _subject_views(
            _items(await client.request_admin("GET", "/api/identity/subjects", tenant_id=str(tenant_id)))
        )
        identity = next(
            (
                subject.get("_runtime_subject")
                for subject in subjects
                if subject["type"] == "user"
                and (
                    subject["id"] == str(owner_id) or bool(owner_email and subject.get("secondary_text") == owner_email)
                )
            ),
            None,
        )
        if identity is None:
            return {
                "connections": [],
                "knowledge_refs": await visible_knowledge_refs(session, tenant_id, owner_id),
            }
        for connection in raw_connections:
            connection_id = str(connection.get("id") or "")
            service = connection.get("service")
            actions: list[dict[str, Any]] = []
            for raw_action in raw_actions:
                if raw_action.get("service") != service:
                    continue
                action = _action_view(raw_action)
                try:
                    preview = await client.request_admin(
                        "POST",
                        "/api/access/preview",
                        json={
                            "subject": identity,
                            "connectionId": connection_id,
                            "actionId": action["id"],
                        },
                        tenant_id=str(tenant_id),
                    )
                    decision = preview.get("decision", {}) if isinstance(preview, dict) else {}
                    if not decision.get("allowed"):
                        continue
                except Exception:
                    continue
                actions.append(
                    ContextRef(
                        id=str(action["id"]),
                        kind="mcp_action",
                        name=str(action["name"]),
                        source="OpenConnector",
                        connection_id=connection_id,
                        metadata={"risk": action["risk"], "read_only": action["read_only"]},
                    ).model_dump()
                )
            if actions:
                connections.append(
                    {
                        "id": connection_id,
                        "name": str(
                            connection.get("displayName")
                            or connection.get("connectionName")
                            or connection.get("alias")
                            or service
                        ),
                        "provider": str(service or ""),
                        "actions": actions,
                    }
                )
    except Exception:
        connections = []

    return {
        "connections": connections,
        "knowledge_refs": await visible_knowledge_refs(session, tenant_id, owner_id),
    }


async def visible_knowledge_refs(session: AsyncSession, tenant_id: UUID, owner_id: UUID) -> list[dict[str, Any]]:
    provider = os.getenv("W6_RESOURCE_REF_PROVIDER", "").strip()
    if provider:
        module_name, separator, function_name = provider.partition(":")
        if not separator:
            return []
        try:
            value = getattr(importlib.import_module(module_name), function_name)(
                tenant_id=tenant_id,
                owner_id=owner_id,
                session=session,
            )
            if inspect.isawaitable(value):
                value = await value
            refs = [ContextRef.model_validate(item) for item in value]
            if any(item.kind != "knowledge_resource" or not item.id.startswith("viking://") for item in refs):
                return []
            return [item.model_dump() for item in refs]
        except Exception:
            return []
    resources = await session.execute(
        select(SourceResource, KnowledgeResource)
        .join(KnowledgeResource, KnowledgeResource.resource_id == SourceResource.id)
        .where(
            SourceResource.tenant_id == tenant_id,
            KnowledgeResource.tenant_id == tenant_id,
            KnowledgeResource.index_status == "indexed",
        )
    )
    knowledge_refs = []
    for resource, knowledge in resources:
        if resource.visibility != "workspace" and resource.owner_id != owner_id:
            continue
        selection = resource.selection_config_json or {}
        resource_ref = selection.get("openviking_resource_ref")
        if not isinstance(resource_ref, str) or not resource_ref.startswith("viking://"):
            continue
        knowledge_refs.append(
            ContextRef(
                id=resource_ref,
                kind="knowledge_resource",
                name=resource.name,
                source="OpenViking ResourceRef",
                metadata={"resource_id": str(resource.id), "provider": knowledge.provider},
            ).model_dump()
        )
    return knowledge_refs


def validate_refs(
    requested_mcp: list[ContextRef],
    requested_knowledge: list[ContextRef],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    visible_mcp = {item["id"]: item for connection in catalog["connections"] for item in connection["actions"]}
    visible_knowledge = {item["id"]: item for item in catalog["knowledge_refs"]}
    unknown_mcp = [item.id for item in requested_mcp if item.id not in visible_mcp]
    unknown_knowledge = [item.id for item in requested_knowledge if item.id not in visible_knowledge]
    if unknown_mcp or unknown_knowledge:
        raise ValueError("包含当前用户不可见的 Connection Action 或 Knowledge ResourceRef")
    return {
        "mcp_refs": [visible_mcp[item.id] for item in requested_mcp],
        "knowledge_refs": [visible_knowledge[item.id] for item in requested_knowledge],
    }


def delegated_auth_ref(auth: Any) -> str | None:
    provider = os.getenv("W5_DELEGATED_AUTH_PROVIDER", "").strip()
    if not provider:
        return None
    module_name, separator, function_name = provider.partition(":")
    if not separator:
        raise W5AdapterError("BLOCKED_CONFIG", "W5_DELEGATED_AUTH_PROVIDER 必须是 module:function。")
    value = getattr(importlib.import_module(module_name), function_name)(auth)
    return value if isinstance(value, str) and value else None


def status_from_error(error: W5AdapterError) -> str:
    if error.code == "BLOCKED_AUTH":
        return "blocked_auth"
    if error.code == "BLOCKED_CONFIG":
        return "blocked_config"
    if error.code == "CANCELLED":
        return "cancelled"
    return "retryable" if error.retryable else "error"


def next_revision(active_revision: str | None) -> str:
    match = re.fullmatch(r"rev-(\d+)", active_revision or "")
    return f"rev-{int(match.group(1)) + 1}" if match else "rev-1"


async def run_invocation(
    *,
    tenant_id: UUID,
    owner_id: UUID,
    session_id: UUID,
    payload: InvocationCreate,
    delegated_auth: str | None,
    adapter: W5SkillAgentAdapter | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    adapter = adapter or W5SkillAgentAdapter()
    factory = session_factory or AsyncSessionFactory
    async with factory() as db:
        repo = SkillWorkbenchRepository(db, tenant_id, owner_id)
        item = await repo.get_session(session_id)
        if item is None:
            return
        skill = await repo.get_skill(item.skill_id)
        if skill is None:
            return
        try:
            invocation = W5Invocation(
                business_goal=payload.message,
                mcp_capability_refs=[ref["id"] for ref in item.context_refs_json.get("mcp_refs", [])],
                knowledge_resource_refs=[ref["id"] for ref in item.context_refs_json.get("knowledge_refs", [])],
                target_skill=skill.target_skill,
                revision=next_revision(skill.active_revision),
                session_id=str(item.id),
                delegated_auth_ref=delegated_auth,
            )
            async for envelope in adapter.invoke(invocation):
                for raw_event in envelope["events"] if isinstance(envelope.get("events"), list) else [envelope]:
                    event = {**safe_event(raw_event), "id": str(uuid4()), "at": now_iso()}
                    append_json(item, "events_json", event)
                    apply_status(item, event)
                    await apply_result(repo, skill, item, raw_event)
                if isinstance(envelope.get("validation"), dict):
                    append_json(
                        item,
                        "events_json",
                        {
                            "id": str(uuid4()),
                            "type": "validation",
                            "validation": public_metadata(envelope["validation"]),
                            "at": now_iso(),
                        },
                    )
                await apply_result(repo, skill, item, envelope)
                await db.commit()
            if item.status == "running":
                item.status = "ready" if skill.active_revision else "error"
            if item.status == "ready":
                append_json(
                    item,
                    "messages_json",
                    {"role": "assistant", "content": "W5 已完成本轮处理。", "at": now_iso()},
                )
        except asyncio.CancelledError:
            item.status = "cancelled"
            append_json(
                item,
                "events_json",
                {"id": str(uuid4()), "type": "cancelled", "code": "CANCELLED", "at": now_iso()},
            )
        except W5AdapterError as exc:
            item.status = status_from_error(exc)
            append_json(
                item,
                "events_json",
                {
                    "id": str(uuid4()),
                    "type": item.status,
                    "code": exc.code,
                    "message": str(exc),
                    "at": now_iso(),
                },
            )
        except Exception:
            item.status = "retryable"
            append_json(
                item,
                "events_json",
                {
                    "id": str(uuid4()),
                    "type": "retryable",
                    "code": "RETRYABLE",
                    "message": "运行暂时失败，可从当前会话重试。",
                    "at": now_iso(),
                },
            )
        finally:
            item.current_invocation_id = None
            skill.status = item.status
            skill.updated_at = datetime.now(UTC).replace(tzinfo=None)
            await db.commit()
            ACTIVE_TASKS.pop(str(session_id), None)


def apply_status(item: DataWorkshopSkillSession, event: dict[str, Any]) -> None:
    value = str(event.get("status") or event.get("code") or event.get("type") or "").upper()
    validation = event.get("validation")
    validation_code = (
        str(validation.get("code") or validation.get("status") or "").upper() if isinstance(validation, dict) else ""
    )
    if value == "BLOCKED_AUTH" or validation_code == "BLOCKED_AUTH":
        item.status = "blocked_auth"
    elif value == "BLOCKED_CONFIG" or validation_code == "BLOCKED_CONFIG":
        item.status = "blocked_config"
    elif value in {"VALIDATION_FAILED", "BLOCKED_VALIDATION"} or validation_code in {
        "VALIDATION_FAILED",
        "BLOCKED_VALIDATION",
        "FAILED",
    }:
        item.status = "validation_failed"
    elif isinstance(validation, dict) and validation.get("ok") is False:
        item.status = "validation_failed"
    elif value.startswith("VALIDATION.") and event.get("ok") is False:
        item.status = "validation_failed"
    elif value == "CANCELLED":
        item.status = "cancelled"
    elif value == "RETRYABLE":
        item.status = "retryable"
    elif value == "ERROR":
        item.status = "error"
    elif value == "SUCCEEDED":
        item.status = "ready"


async def apply_result(
    repo: SkillWorkbenchRepository,
    skill: DataWorkshopSkill,
    item: DataWorkshopSkillSession,
    result: dict[str, Any],
) -> None:
    apply_status(item, result)
    artifact = result.get("artifact")
    revision = result.get("revision")
    validation = result.get("validation") if isinstance(result.get("validation"), dict) else None
    if validation is not None and skill.active_revision:
        current = await repo.get_revision(skill.id, skill.active_revision)
        if current is not None:
            current.validation_json = validation
            current.artifact_metadata_json = {
                **current.artifact_metadata_json,
                "validation": public_metadata(validation),
            }
            if item.active_revision == current.revision:
                item.artifact_metadata_json = current.artifact_metadata_json
    if isinstance(artifact, dict):
        revision = revision or artifact.get("revision")
    if not revision or not isinstance(artifact, dict):
        return
    download = artifact.get("download")
    upstream_url = (
        str(download["download_url"])
        if isinstance(download, dict) and download.get("download_url")
        else str(artifact["download_url"])
        if artifact.get("download_url")
        else None
    )
    metadata = artifact_metadata(artifact)
    metadata["_proxy_ready"] = bool(upstream_url and artifact_url_allowed(upstream_url))
    if validation is None:
        validation = next(
            (
                event["validation"]
                for event in reversed(item.events_json or [])
                if isinstance(event, dict) and isinstance(event.get("validation"), dict)
            ),
            None,
        )
    if validation is not None:
        metadata["validation"] = public_metadata(validation)
    await repo.save_revision(
        skill=skill,
        work_session=item,
        revision=str(revision),
        artifact_metadata=metadata,
        upstream_artifact_url=upstream_url,
        validation=validation,
    )
