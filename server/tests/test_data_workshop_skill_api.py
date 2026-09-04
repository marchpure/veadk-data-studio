from __future__ import annotations

import asyncio
import copy
import io
import zipfile
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.data_workshop.skill import api, service
from server.data_workshop.skill.repository import SkillWorkbenchRepository
from server.data_workshop.skill.service import (
    apply_result,
    apply_status,
    artifact_url_allowed,
    next_revision,
    public_artifact,
    safe_event,
    session_payload,
    validate_refs,
)
from server.data_workshop.skill.w5_adapter import W5Invocation, W5SkillAgentAdapter
from server.db.base import Base
from server.db.session import get_async_session
from server.models.data_workshop_skill import (
    DataWorkshopSkill,
    DataWorkshopSkillRevision,
    DataWorkshopSkillSession,
)
from server.models.tenant import Tenant
from server.models.user import User

CATALOG = {
    "connections": [
        {
            "id": "connection-1",
            "name": "Oracle 生产库",
            "provider": "oracle",
            "actions": [
                {
                    "id": "oracle.query_rows",
                    "kind": "mcp_action",
                    "name": "query_rows",
                    "source": "OpenConnector",
                    "connection_id": "connection-1",
                    "metadata": {"read_only": True},
                }
            ],
        }
    ],
    "knowledge_refs": [
        {
            "id": "viking://resources/revenue",
            "kind": "knowledge_resource",
            "name": "营收口径",
            "source": "OpenViking ResourceRef",
            "connection_id": None,
            "metadata": {},
        }
    ],
}


@pytest_asyncio.fixture
async def skill_app(tmp_path, monkeypatch: pytest.MonkeyPatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'skill.db'}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[
                User.__table__,
                Tenant.__table__,
                DataWorkshopSkill.__table__,
                DataWorkshopSkillSession.__table__,
                DataWorkshopSkillRevision.__table__,
            ],
        )
    owner_id, other_id, tenant_id, other_tenant_id = uuid4(), uuid4(), uuid4(), uuid4()
    async with factory() as db:
        db.add_all(
            [
                User(id=owner_id, email="owner@example.test", hashed_password="x"),
                User(id=other_id, email="other@example.test", hashed_password="x"),
            ]
        )
        await db.flush()
        db.add_all(
            [
                Tenant(id=tenant_id, name="A", slug="a", owner_id=owner_id),
                Tenant(id=other_tenant_id, name="B", slug="b", owner_id=other_id),
            ]
        )
        await db.commit()

    current = {"tenant_id": tenant_id, "user_id": owner_id}

    async def db_override():
        async with factory() as db:
            yield db

    def auth_override():
        return SimpleNamespace(
            tenant_id=current["tenant_id"],
            user_id=current["user_id"],
            user=SimpleNamespace(email="owner@example.test"),
            is_viewer=False,
        )

    async def catalog_override(*_args, **_kwargs):
        return CATALOG

    async def run_override(**_kwargs):
        await asyncio.sleep(0)

    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    app.dependency_overrides[get_async_session] = db_override
    app.dependency_overrides[api.get_skill_session_factory] = lambda: factory
    app.dependency_overrides[api.require_skill_read] = auth_override
    app.dependency_overrides[api.require_skill_write] = auth_override
    monkeypatch.setattr(api, "visible_catalog", catalog_override)
    monkeypatch.setattr(api, "run_invocation", run_override)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory, current, (tenant_id, owner_id, other_tenant_id, other_id)
    await engine.dispose()


def skill_body() -> dict:
    return {
        "title": "营收复盘 Skill",
        "target_skill": "revenue-review",
        "description": "生成周度营收复盘",
        "mcp_refs": [CATALOG["connections"][0]["actions"][0]],
        "knowledge_refs": [CATALOG["knowledge_refs"][0]],
    }


@pytest.mark.asyncio
async def test_skill_and_session_persist_across_clients(skill_app) -> None:
    client, factory, _, _ = skill_app
    created = await client.post("/api/v1/skills", json=skill_body())
    assert created.status_code == 201
    skill_id = created.json()["data"]["skill"]["id"]
    session_id = created.json()["data"]["session"]["id"]

    async with factory() as restarted_process_db:
        repo = SkillWorkbenchRepository(
            restarted_process_db,
            UUID(created.json()["data"]["skill"]["id"])
            and (await restarted_process_db.get(DataWorkshopSkill, UUID(skill_id))).tenant_id,
            (await restarted_process_db.get(DataWorkshopSkill, UUID(skill_id))).owner_id,
        )
        assert (await repo.get_skill(UUID(skill_id))).target_skill == "revenue-review"
        assert (await repo.get_session(UUID(session_id))).title == "初始会话"

    listed = await client.get("/api/v1/skills")
    assert listed.json()["data"]["items"][0]["id"] == skill_id
    sessions = await client.get(f"/api/v1/skills/{skill_id}/sessions")
    assert sessions.json()["data"]["items"][0]["id"] == session_id


@pytest.mark.asyncio
async def test_owner_and_tenant_isolation_return_not_found(skill_app) -> None:
    client, _, current, identities = skill_app
    tenant_id, owner_id, other_tenant_id, other_id = identities
    created = await client.post("/api/v1/skills", json=skill_body())
    skill_id = created.json()["data"]["skill"]["id"]
    session_id = created.json()["data"]["session"]["id"]

    current.update(tenant_id=tenant_id, user_id=other_id)
    assert (await client.get(f"/api/v1/skills/{skill_id}")).status_code == 404
    assert (await client.get(f"/api/v1/sessions/{session_id}")).status_code == 404

    current.update(tenant_id=other_tenant_id, user_id=other_id)
    assert (await client.get(f"/api/v1/skills/{skill_id}")).status_code == 404
    assert (await client.get(f"/api/v1/sessions/{session_id}")).status_code == 404

    current.update(tenant_id=tenant_id, user_id=owner_id)


@pytest.mark.asyncio
async def test_rejects_invisible_context_and_duplicate_target(skill_app) -> None:
    client, _, _, _ = skill_app
    invisible = copy.deepcopy(skill_body())
    invisible["mcp_refs"][0]["id"] = "oracle.delete_everything"
    assert (await client.post("/api/v1/skills", json=invisible)).status_code == 403

    assert (await client.post("/api/v1/skills", json=skill_body())).status_code == 201
    duplicate = await client.post("/api/v1/skills", json=skill_body())
    assert duplicate.status_code == 409
    assert "继续修改原 Skill" in duplicate.text


@pytest.mark.asyncio
async def test_w6_provider_accepts_only_openviking_resource_refs(skill_app, monkeypatch: pytest.MonkeyPatch) -> None:
    _, factory, _, identities = skill_app
    tenant_id, owner_id, _, _ = identities

    async def provider(**_kwargs):
        return [
            {
                "id": "viking://resources/approved",
                "kind": "knowledge_resource",
                "name": "已授权知识",
                "source": "OpenViking ResourceRef",
                "metadata": {},
            }
        ]

    monkeypatch.setattr(service.importlib, "import_module", lambda _name: SimpleNamespace(list_refs=provider))
    monkeypatch.setenv("W6_RESOURCE_REF_PROVIDER", "w6_provider:list_refs")
    async with factory() as db:
        refs = await service.visible_knowledge_refs(db, tenant_id, owner_id)
    assert [item["id"] for item in refs] == ["viking://resources/approved"]

    async def invalid_provider(**_kwargs):
        return [
            {
                "id": "https://untrusted.example/resource",
                "kind": "knowledge_resource",
                "name": "错误引用",
                "source": "OpenViking ResourceRef",
                "metadata": {},
            }
        ]

    monkeypatch.setattr(service.importlib, "import_module", lambda _name: SimpleNamespace(list_refs=invalid_provider))
    async with factory() as db:
        assert await service.visible_knowledge_refs(db, tenant_id, owner_id) == []


@pytest.mark.asyncio
async def test_invocation_is_idempotent_and_preserves_history(skill_app) -> None:
    client, _, _, _ = skill_app
    created = await client.post("/api/v1/skills", json=skill_body())
    session_id = created.json()["data"]["session"]["id"]
    invocation = {"message": "先规划再生成", "client_invocation_id": "browser-1", "validate": True}

    first = await client.post(f"/api/v1/sessions/{session_id}/invocations", json=invocation)
    second = await client.post(f"/api/v1/sessions/{session_id}/invocations", json=invocation)
    assert first.status_code == 202
    assert second.status_code == 202
    state = (await client.get(f"/api/v1/sessions/{session_id}")).json()["data"]
    assert [message["content"] for message in state["messages"]] == ["先规划再生成"]
    assert len([event for event in state["events"] if event["type"] == "invocation_started"]) == 1
    skill_id = created.json()["data"]["skill"]["id"]
    assert (await client.get(f"/api/v1/skills/{skill_id}")).json()["data"]["status"] == "running"


@pytest.mark.asyncio
async def test_cancel_and_retry_keep_the_same_session(skill_app) -> None:
    client, _, _, _ = skill_app
    created = await client.post("/api/v1/skills", json=skill_body())
    session_id = created.json()["data"]["session"]["id"]
    await client.post(
        f"/api/v1/sessions/{session_id}/invocations",
        json={"message": "生成后校验", "client_invocation_id": "first", "validate": True},
    )
    cancelled = await client.post(f"/api/v1/sessions/{session_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["id"] == session_id
    assert cancelled.json()["data"]["status"] == "cancelled"
    skill_id = created.json()["data"]["skill"]["id"]
    assert (await client.get(f"/api/v1/skills/{skill_id}")).json()["data"]["status"] == "cancelled"

    retried = await client.post(
        f"/api/v1/sessions/{session_id}/retry",
        json={"client_invocation_id": "retry-1"},
    )
    assert retried.status_code == 202
    assert retried.json()["data"]["id"] == session_id
    assert retried.json()["data"]["status"] == "running"
    repeated = await client.post(
        f"/api/v1/sessions/{session_id}/retry",
        json={"client_invocation_id": "retry-1"},
    )
    assert repeated.status_code == 202
    assert repeated.json()["message"] == "Retry already accepted"
    assert (
        len([event for event in repeated.json()["data"]["events"] if event.get("client_invocation_id") == "retry-1"])
        == 1
    )


@pytest.mark.asyncio
async def test_running_session_recovers_as_retryable_after_restart(skill_app) -> None:
    client, factory, _, _ = skill_app
    created = await client.post("/api/v1/skills", json=skill_body())
    session_id = created.json()["data"]["session"]["id"]
    async with factory() as db:
        item = await db.get(DataWorkshopSkillSession, UUID(session_id))
        item.status = "running"
        item.current_invocation_id = "lost-worker"
        await db.commit()

    api.ACTIVE_TASKS.clear()
    recovered = (await client.get(f"/api/v1/sessions/{session_id}")).json()["data"]
    assert recovered["status"] == "retryable"
    assert recovered["current_invocation_id"] is None
    assert recovered["events"][-1]["code"] == "INVOCATION_INTERRUPTED"

    async with factory() as db:
        item = await db.get(DataWorkshopSkillSession, UUID(session_id))
        item.status = "running"
        item.current_invocation_id = "another-lost-worker"
        await db.commit()
    event_page = (await client.get(f"/api/v1/sessions/{session_id}/events")).json()["data"]
    assert event_page["status"] == "retryable"
    assert event_page["done"] is True


@pytest.mark.asyncio
async def test_follow_up_results_create_revisions_on_the_same_skill(skill_app) -> None:
    client, factory, _, identities = skill_app
    tenant_id, owner_id, _, _ = identities
    created = await client.post("/api/v1/skills", json=skill_body())
    skill_id = UUID(created.json()["data"]["skill"]["id"])
    session_id = UUID(created.json()["data"]["session"]["id"])

    async with factory() as db:
        repo = SkillWorkbenchRepository(db, tenant_id, owner_id)
        skill = await repo.get_skill(skill_id)
        work_session = await repo.get_session(session_id)
        for revision in ("r1", "r2"):
            await apply_result(
                repo,
                skill,
                work_session,
                {
                    "status": "SUCCEEDED",
                    "revision": revision,
                    "artifact": {
                        "revision": revision,
                        "files": ["SKILL.md"],
                        "download": {"download_url": f"https://w5.example.test/{revision}.zip"},
                    },
                    "validation": {"ok": True},
                },
            )
            await db.commit()
        revisions = await repo.list_revisions(skill_id)
        assert skill.active_revision == "r2"
        assert work_session.active_revision == "r2"
        assert {item.revision for item in revisions} == {"r1", "r2"}
        assert len(await repo.list_skills()) == 1

        other_session = await repo.create_session(
            skill_id=skill.id,
            title="另一个会话",
            context_refs={"mcp_refs": [], "knowledge_refs": []},
        )
        await db.commit()
        assert session_payload(other_session, skill)["artifact"] is None


def test_context_validation_is_fail_closed() -> None:
    valid_action = CATALOG["connections"][0]["actions"][0]
    valid_knowledge = CATALOG["knowledge_refs"][0]
    from server.data_workshop.skill.schemas import ContextRef

    result = validate_refs(
        [ContextRef.model_validate(valid_action)], [ContextRef.model_validate(valid_knowledge)], CATALOG
    )
    assert result["mcp_refs"][0]["id"] == "oracle.query_rows"
    with pytest.raises(ValueError, match="不可见"):
        validate_refs(
            [ContextRef.model_validate({**valid_action, "id": "hidden.action"})],
            [],
            CATALOG,
        )


def test_next_revision_matches_w5_contract() -> None:
    assert next_revision(None) == "rev-1"
    assert next_revision("rev-1") == "rev-2"
    assert next_revision("unexpected") == "rev-1"


def test_w5_event_parser_maps_sse_without_fabricating_artifacts() -> None:
    assert W5SkillAgentAdapter.parse_event('data: {"type":"planning","message":"分析需求"}') == {
        "type": "planning",
        "message": "分析需求",
    }
    assert W5SkillAgentAdapter.parse_event("data: not-json") is None
    assert W5SkillAgentAdapter.parse_event("Using custom payload: {'prompt': 'secret'}") is None
    assert W5SkillAgentAdapter.parse_event(": keepalive") is None


def test_w5_parser_unwraps_agentkit_tool_response() -> None:
    envelope = {
        "content": {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": "create_or_update_skill",
                        "response": {
                            "status": "SUCCEEDED",
                            "target_skill": "report",
                            "revision": "rev-1",
                            "validation": {"ok": True, "checks": {"secret_free": True}},
                            "artifact": {
                                "revision": "rev-1",
                                "files": ["report/SKILL.md"],
                                "download": {"download_url": "https://w5.example.test/rev-1.zip"},
                            },
                            "events": [{"type": "validation.completed", "ok": True}],
                        },
                    }
                }
            ],
        }
    }
    parsed = W5SkillAgentAdapter.parse_event(f"data: {__import__('json').dumps(envelope)}")
    assert parsed["status"] == "SUCCEEDED"
    assert parsed["artifact"]["revision"] == "rev-1"


@pytest.mark.asyncio
async def test_w5_adapter_uses_documented_agentkit_invocation_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    commands = []

    class Stream:
        def __init__(self, lines):
            self.lines = list(lines)

        async def readline(self):
            return self.lines.pop(0) if self.lines else b""

        async def read(self):
            return b""

    class Process:
        returncode = 0
        stdout = Stream([b'data: {"status":"BLOCKED_AUTH","target_skill":"report","artifact":null}\n'])
        stderr = Stream([])

        async def wait(self):
            return 0

    async def subprocess(*command, **_kwargs):
        commands.append(command)
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", subprocess)
    adapter = W5SkillAgentAdapter(runtime_id="runtime-1", region="cn-beijing", cli_path="agentkit")
    events = [
        event
        async for event in adapter.invoke(
            W5Invocation(
                business_goal="Build",
                mcp_capability_refs=["mcp://read"],
                knowledge_resource_refs=["viking://resources/guide"],
                target_skill="report",
                revision=None,
                session_id="session-1",
                delegated_auth_ref="opaque-reference",
            )
        )
    ]
    command = list(commands[0])
    assert command[:3] == ["agentkit", "invoke", "run"]
    assert command[command.index("--runtime-id") + 1] == "runtime-1"
    assert command[command.index("--region") + 1] == "cn-beijing"
    assert "--raw" in command
    assert events == [{"status": "BLOCKED_AUTH", "target_skill": "report", "artifact": None}]


@pytest.mark.asyncio
async def test_w5_endpoint_transport_requires_and_uses_server_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    invocation = W5Invocation(
        business_goal="Build",
        mcp_capability_refs=[],
        knowledge_resource_refs=[],
        target_skill="report",
        revision=None,
        session_id="session-1",
        delegated_auth_ref="opaque-reference",
    )
    with pytest.raises(Exception, match="API key"):
        async for _ in W5SkillAgentAdapter(endpoint="https://w5.example.test", api_key="").invoke(invocation):
            pass

    requests = []

    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def json(self):
            return {"status": "BLOCKED_AUTH", "target_skill": "report", "artifact": None}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def stream(self, method, url, **kwargs):
            requests.append((method, url, kwargs))
            return Response()

    monkeypatch.setattr("server.data_workshop.skill.w5_adapter.httpx.AsyncClient", lambda **_kwargs: Client())
    events = [
        event
        async for event in W5SkillAgentAdapter(
            endpoint="https://w5.example.test",
            api_key="server-only-key",
        ).invoke(invocation)
    ]
    method, url, kwargs = requests[0]
    assert (method, url) == ("POST", "https://w5.example.test/invoke")
    assert kwargs["headers"]["Authorization"] == "Bearer server-only-key"
    assert events[0]["status"] == "BLOCKED_AUTH"


@pytest.mark.asyncio
async def test_background_runner_persists_nested_w5_artifact(skill_app, monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory, _, identities = skill_app
    tenant_id, owner_id, _, _ = identities
    created = await client.post("/api/v1/skills", json=skill_body())
    skill_id = UUID(created.json()["data"]["skill"]["id"])
    session_id = UUID(created.json()["data"]["session"]["id"])

    async with factory() as db:
        item = await db.get(DataWorkshopSkillSession, session_id)
        item.status = "running"
        await db.commit()

    class FakeAdapter:
        async def invoke(self, invocation: W5Invocation):
            assert invocation.target_skill == "revenue-review"
            yield {
                "events": [
                    {"type": "planning", "message": "制定计划"},
                    {
                        "type": "artifact",
                        "revision": "r-live",
                        "artifact": {
                            "revision": "r-live",
                            "files": ["SKILL.md"],
                            "download": {"download_url": "https://w5.example.test/r-live.zip"},
                        },
                    },
                ],
                "status": "SUCCEEDED",
                "validation": {"ok": True},
            }

    monkeypatch.setattr(service, "AsyncSessionFactory", factory)
    await service.run_invocation(
        tenant_id=tenant_id,
        owner_id=owner_id,
        session_id=session_id,
        payload=api.InvocationCreate(message="生成", client_invocation_id="run-1"),
        delegated_auth="opaque-ref",
        adapter=FakeAdapter(),
    )
    async with factory() as db:
        repo = SkillWorkbenchRepository(db, tenant_id, owner_id)
        skill = await repo.get_skill(skill_id)
        work_session = await repo.get_session(session_id)
        assert skill.active_revision == "r-live"
        assert work_session.active_revision == "r-live"
        assert work_session.status == "ready"
        assert [event["type"] for event in work_session.events_json][-3:] == ["planning", "artifact", "validation"]


@pytest.mark.asyncio
async def test_validation_after_artifact_is_attached_to_revision(skill_app) -> None:
    client, factory, _, identities = skill_app
    tenant_id, owner_id, _, _ = identities
    created = await client.post("/api/v1/skills", json=skill_body())
    skill_id = UUID(created.json()["data"]["skill"]["id"])
    session_id = UUID(created.json()["data"]["session"]["id"])

    async with factory() as db:
        repo = SkillWorkbenchRepository(db, tenant_id, owner_id)
        skill = await repo.get_skill(skill_id)
        work_session = await repo.get_session(session_id)
        await apply_result(
            repo,
            skill,
            work_session,
            {
                "revision": "r1",
                "artifact": {
                    "files": ["SKILL.md"],
                    "download": {"download_url": "https://w5.example.test/r1.zip"},
                },
            },
        )
        await apply_result(
            repo,
            skill,
            work_session,
            {
                "status": "VALIDATION_FAILED",
                "validation": {"ok": False, "checks": [{"name": "manifest", "ok": False}]},
            },
        )
        await db.commit()
        revision = await repo.get_revision(skill_id, "r1")
        assert revision.validation_json["checks"][0]["name"] == "manifest"
        assert revision.updated_at is not None
        assert work_session.artifact_metadata_json["validation"]["ok"] is False


def test_nested_validation_failure_updates_status_and_preserves_checks() -> None:
    item = SimpleNamespace(status="running")
    event = {
        "type": "validation.completed",
        "status": "FAILED",
        "validation": {
            "ok": False,
            "code": "VALIDATION_FAILED",
            "checks": [{"name": "manifest", "ok": False, "message": "缺少 name"}],
        },
    }
    apply_status(item, event)
    assert item.status == "validation_failed"
    assert event["validation"]["checks"][0]["message"] == "缺少 name"
    direct = SimpleNamespace(status="running")
    apply_status(direct, {"type": "validation.completed", "ok": False})
    assert direct.status == "validation_failed"


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ({"status": "BLOCKED_AUTH"}, "blocked_auth"),
        ({"status": "BLOCKED_CONFIG"}, "blocked_config"),
        ({"status": "VALIDATION_FAILED"}, "validation_failed"),
        ({"status": "CANCELLED"}, "cancelled"),
        ({"status": "RETRYABLE"}, "retryable"),
    ],
)
def test_w5_terminal_status_matrix(event: dict, expected: str) -> None:
    item = SimpleNamespace(status="running")
    apply_status(item, event)
    assert item.status == expected


def test_public_artifact_recursively_removes_sensitive_fields() -> None:
    public = public_artifact(
        uuid4(),
        "r1",
        {
            "files": ["SKILL.md"],
            "download": {"download_url": "https://private.example/artifact.zip", "token": "secret"},
            "validation": {
                "credential": "secret",
                "label": "safe",
                "checks": {"safe": True, "nested": {"api_key": "hidden"}},
            },
        },
    )
    assert public["validation"] == {"label": "safe", "checks": {"safe": True, "nested": {}}}
    assert "private.example" not in str(public)
    assert "secret" not in str(public)


def test_w5_events_are_allowlisted_before_browser_persistence() -> None:
    event = safe_event(
        {
            "type": "tool",
            "message": "查询完成；Authorization: Bearer abc.def；api_key=visible-value",
            "authorization": "Bearer hidden",
            "runtime_token": "hidden",
            "validation": {"ok": False, "checks": [{"name": "lint", "ok": False}], "secret": "hidden"},
        }
    )
    assert "abc.def" not in event["message"]
    assert "visible-value" not in event["message"]
    assert event["validation"]["checks"][0]["name"] == "lint"
    assert "hidden" not in str(event)


@pytest.mark.asyncio
async def test_artifact_proxy_requires_metadata_and_sandboxes_html(skill_app, monkeypatch: pytest.MonkeyPatch) -> None:
    client, factory, _, identities = skill_app
    tenant_id, owner_id, _, _ = identities
    created = await client.post("/api/v1/skills", json=skill_body())
    skill_id = created.json()["data"]["skill"]["id"]
    session_id = created.json()["data"]["session"]["id"]

    assert (await client.get(f"/api/v1/skills/{skill_id}/revisions/r1/preview")).status_code == 404

    async with factory() as db:
        repo = SkillWorkbenchRepository(db, tenant_id, owner_id)
        skill = await repo.get_skill(UUID(skill_id))
        work_session = await repo.get_session(UUID(session_id))
        await repo.save_revision(
            skill=skill,
            work_session=work_session,
            revision="r1",
            artifact_metadata={"files": ["preview.html"], "validation": {"ok": True}, "_proxy_ready": True},
            upstream_artifact_url="https://w5.example.test/artifact.zip",
            validation={"ok": True},
        )
        await db.commit()

    diff = await client.get(
        f"/api/v1/skills/{skill_id}/revision-diff",
        params={"base": "r1", "target": "r1"},
    )
    assert diff.status_code == 200
    assert diff.json()["data"]["files_added"] == []

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("preview.html", "<script>parent.alert('bad')</script><h1>预览</h1>")

    async def fetch_override(_url: str) -> bytes:
        return archive_buffer.getvalue()

    monkeypatch.setattr(api, "fetch_artifact", fetch_override)
    preview = await client.get(f"/api/v1/skills/{skill_id}/revisions/r1/preview")
    assert preview.status_code == 200
    assert "sandbox" in preview.headers["content-security-policy"]
    assert preview.headers["x-content-type-options"] == "nosniff"
    public = (await client.get(f"/api/v1/skills/{skill_id}")).json()["data"]["artifact"]
    assert public["preview_url"].endswith("/preview")
    assert "w5.example.test" not in str(public)


def test_artifact_host_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("W5_SKILL_AGENT_ENDPOINT", "https://w5.example.test")
    monkeypatch.setenv("W5_ARTIFACT_HOSTS", "artifacts.example.test")
    assert artifact_url_allowed("https://w5.example.test/a.zip")
    assert artifact_url_allowed("https://artifacts.example.test/a.zip")
    assert not artifact_url_allowed("http://w5.example.test/a.zip")
    assert not artifact_url_allowed("https://attacker.example/a.zip")
