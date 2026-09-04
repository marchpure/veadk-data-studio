import asyncio
import io
import json
import zipfile

import pytest

from server.routers import skill_agent_bff
from server.services.w5_skill_agent_adapter import W5AdapterError, W5Invocation, W5SkillAgentAdapter


@pytest.mark.asyncio
async def test_adapter_forwards_runtime_request_and_parses_incremental_events(monkeypatch):
    calls = []

    class FakeStream:
        def __init__(self, lines):
            self.lines = iter(lines)

        async def readline(self):
            await asyncio.sleep(0)
            return next(self.lines, b"")

        async def read(self):
            return b""

    class FakeProcess:
        returncode = 0
        stdout = FakeStream([
            b'data: {"type":"planning"}\n',
            b'data: {"type":"revision.created","revision":"rev-1"}\n',
            b'data: {"type":"artifact.created","artifact":{"files":["SKILL.md"]}}\n',
        ])
        stderr = FakeStream([])

        async def wait(self):
            return self.returncode

    async def fake_exec(*command, **kwargs):
        calls.append(command)
        return FakeProcess()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    adapter = W5SkillAgentAdapter(runtime_id="runtime-1", region="cn-beijing", cli_path="agentkit", transport_mode="LOCAL_DEBUG")
    events = [
        event
        async for event in adapter.invoke(
            W5Invocation(
                business_goal="build a report skill",
                mcp_capability_refs=["connection-1"],
                knowledge_resource_refs=["resource-1"],
                target_skill="report-skill",
                revision=None,
                session_id="session-1",
                delegated_auth_ref="delegated-ref",
            )
        )
    ]

    command = calls[0]
    forwarded = json.loads(json.loads(command[command.index("--payload") + 1])["prompt"])
    assert forwarded["business_goal"] == "build a report skill"
    assert forwarded["mcp_capability_refs"] == ["connection-1"]
    assert forwarded["knowledge_resource_refs"] == ["resource-1"]
    assert command[command.index("--runtime-id") + 1] == "runtime-1"
    headers = json.loads(command[command.index("--headers") + 1])
    assert headers["delegated_auth_ref"] == "delegated-ref"
    assert [event["type"] for event in events] == [
        "planning",
        "revision.created",
        "artifact.created",
    ]


def test_bff_maps_w5_final_result_envelope():
    item = {"status": "running", "revision": None, "artifact": None}
    skill_agent_bff._apply_w5_result(
        item,
        {
            "status": "SUCCEEDED",
            "target_skill": "report-skill",
            "revision": "rev-3",
            "validation": {"ok": True, "code": "OK"},
            "artifact": {
                "skill_slug": "report-skill",
                "revision": "rev-3",
                "files": ["report-skill/SKILL.md"],
                "download": {"download_url": "https://artifact.example/rev-3.zip"},
            },
            "events": [],
        },
    )
    assert item["status"] == "ready"
    assert item["revision"] == "rev-3"
    assert item["artifact"]["files"] == ["report-skill/SKILL.md"]
    assert item["artifact_url"].endswith("rev-3.zip")

    failed = {"status": "running", "revision": None, "artifact": None}
    skill_agent_bff._apply_w5_result(
        failed,
        {"status": "VALIDATION_FAILED", "validation": {"ok": False, "code": "INVALID_TARGET"}},
    )
    assert failed["status"] == "validation_failed"
    assert failed["artifact"] is None


@pytest.mark.asyncio
async def test_adapter_fails_closed_without_auth_or_endpoint():
    with pytest.raises(W5AdapterError, match="OAuth"):
        async for _ in W5SkillAgentAdapter(base_url="https://w5.example").invoke(
            W5Invocation("goal", [], [], None, None, "session", None)
        ):
            pass
    with pytest.raises(W5AdapterError) as exc_info:
        async for _ in W5SkillAgentAdapter().invoke(
            W5Invocation("goal", [], [], None, None, "session", "delegated-ref")
        ):
            pass
    assert exc_info.value.code == "BLOCKED_CONFIG"


@pytest.mark.asyncio
async def test_production_transport_fails_closed_without_i4_runtime():
    with pytest.raises(W5AdapterError) as exc_info:
        async for _ in W5SkillAgentAdapter(transport_mode="PRODUCTION").invoke(
            W5Invocation("goal", [], [], None, None, "session", "delegated-ref")
        ):
            pass
    assert exc_info.value.code == "BLOCKED_CONFIG"


@pytest.mark.asyncio
async def test_adapter_terminates_process_when_cancelled(monkeypatch):
    terminated = []

    class FakeStream:
        async def readline(self):
            await asyncio.sleep(60)
            return b""

        async def read(self):
            return b""

    class FakeProcess:
        returncode = None
        stdout = FakeStream()
        stderr = FakeStream()

        def terminate(self):
            terminated.append("terminate")
            self.returncode = 0

        async def wait(self):
            return self.returncode

    async def fake_exec(*command, **kwargs):
        return FakeProcess()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    adapter = W5SkillAgentAdapter(runtime_id="runtime-1", transport_mode="LOCAL_DEBUG")
    stream = adapter.invoke(W5Invocation("goal", [], [], None, None, "s", "auth"))
    task = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(W5AdapterError, match="cancelled"):
        await task


def test_bff_restart_marks_running_sessions_interrupted(tmp_path, monkeypatch):
    path = tmp_path / "sessions.json"
    path.write_text(json.dumps({"session-1": {"id": "session-1", "status": "running", "events": []}}))
    monkeypatch.setattr(skill_agent_bff, "_path", path)
    skill_agent_bff._load()
    assert skill_agent_bff._sessions["session-1"]["status"] == "interrupted"
    assert skill_agent_bff._sessions["session-1"]["events"][0]["code"] == "INVOCATION_INTERRUPTED"


@pytest.fixture
def isolated_bff(monkeypatch, tmp_path):
    monkeypatch.setattr(skill_agent_bff, "_path", tmp_path / "sessions.json")
    monkeypatch.setattr(skill_agent_bff, "_backend", "TEST BACKEND")
    monkeypatch.setattr(
        skill_agent_bff,
        "_catalog",
        lambda session, auth: _catalog_fixture(),
    )
    skill_agent_bff._sessions.clear()
    skill_agent_bff._tasks.clear()
    yield
    for task in list(skill_agent_bff._tasks.values()):
        task.cancel()
    skill_agent_bff._tasks.clear()
    skill_agent_bff._sessions.clear()


async def _catalog_fixture():
    return (
        [
            skill_agent_bff.SkillRef(
                id="connection-1",
                kind="connection",
                name="Sales DB",
                source="Connection",
                metadata={"actions": ["query"]},
            )
        ],
        [
            skill_agent_bff.SkillRef(
                id="resource-1",
                kind="knowledge_resource",
                name="Sales guide",
                source="OpenViking ResourceRef",
                metadata={"status": "ready"},
            )
        ],
    )


@pytest.mark.asyncio
async def test_bff_test_backend_session_flow_is_incremental_and_artifact_gated(
    test_client, isolated_bff
):
    created = await test_client.post(
        "/api/skill-agent-bff/sessions",
        json={
            "target": "sales-skill",
            "mcp_refs": [{"id": "connection-1", "kind": "connection", "name": "Sales DB", "source": "Connection"}],
            "knowledge_refs": [{"id": "resource-1", "kind": "knowledge_resource", "name": "Sales guide", "source": "OpenViking ResourceRef"}],
        },
    )
    assert created.status_code == 200
    session = created.json()["data"]
    session_id = session["id"]
    assert session["backend"] == "TEST BACKEND"
    assert session["mcp_refs"][0]["id"] == "connection-1"
    assert session["knowledge_refs"][0]["id"] == "resource-1"
    assert session["preview_url"].endswith(f"session={session_id}")

    before = await test_client.get(f"/api/skill-agent-bff/sessions/{session_id}/artifact/preview")
    assert before.status_code == 404

    invoked = await test_client.post(
        f"/api/skill-agent-bff/sessions/{session_id}/invocations",
        json={"message": "Create the sales skill", "client_invocation_id": "invoke-1"},
    )
    assert invoked.status_code == 200
    repeated = await test_client.post(
        f"/api/skill-agent-bff/sessions/{session_id}/invocations",
        json={"message": "Create the sales skill", "client_invocation_id": "invoke-1"},
    )
    assert repeated.json()["message"] == "Invocation already accepted"

    await asyncio.sleep(0.05)
    events = await test_client.get(f"/api/skill-agent-bff/sessions/{session_id}/events?after=1")
    assert events.status_code == 200
    event_payload = events.json()["data"]
    assert event_payload["done"] is True
    assert {event["type"] for event in event_payload["items"]} >= {"planning", "tool_call", "validate", "artifact"}

    recovered = await test_client.get(f"/api/skill-agent-bff/sessions/{session_id}")
    assert recovered.json()["data"]["status"] == "ready"
    assert "download_url" not in recovered.json()["data"]["artifact"]
    assert "preview_url" not in recovered.json()["data"]["artifact"]


@pytest.mark.asyncio
async def test_bff_validation_failure_is_not_success(test_client, isolated_bff):
    created = await test_client.post("/api/skill-agent-bff/sessions", json={"target": "sales-skill"})
    session_id = created.json()["data"]["id"]
    await test_client.post(
        f"/api/skill-agent-bff/sessions/{session_id}/invocations",
        json={"message": "invalid request", "client_invocation_id": "invalid-1", "validate": True},
    )
    await asyncio.sleep(0.05)
    recovered = await test_client.get(f"/api/skill-agent-bff/sessions/{session_id}")
    assert recovered.json()["data"]["status"] == "validation_failed"
    assert recovered.json()["data"]["artifact"] is None


def test_delegated_auth_reference_refreshes_for_existing_session(monkeypatch):
    item = {"delegated_auth_ref": None}
    auth = object()
    refs = iter(["oauth-ref-after-reauthorize"])

    class FakeAdapter:
        def delegated_auth_ref(self, received_auth):
            assert received_auth is auth
            return next(refs)

    monkeypatch.setattr(skill_agent_bff, "_adapter", FakeAdapter())
    skill_agent_bff._refresh_delegated_auth(item, auth)
    assert item["delegated_auth_ref"] == "oauth-ref-after-reauthorize"


@pytest.mark.asyncio
async def test_bff_artifact_download_and_preview_proxy_w5_zip(test_client, isolated_bff, monkeypatch):
    created = await test_client.post("/api/skill-agent-bff/sessions", json={"target": "sales-skill"})
    session_id = created.json()["data"]["id"]
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("sales-skill/SKILL.md", "# sales")
        archive.writestr("sales-skill/index.html", "<!doctype html><p>sales</p>")
    skill_agent_bff._sessions[session_id]["artifact"] = {
        "revision": "rev-1",
        "files": ["sales-skill/SKILL.md", "sales-skill/index.html"],
        "download": {"download_url": "https://artifact.example/rev-1.zip"},
    }
    skill_agent_bff._sessions[session_id]["artifact_url"] = "https://artifact.example/rev-1.zip"
    skill_agent_bff._persist()

    class FakeResponse:
        content = archive_bytes.getvalue()

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            assert url == "https://artifact.example/rev-1.zip"
            return FakeResponse()

    monkeypatch.setattr(skill_agent_bff.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    download = await test_client.get(f"/api/skill-agent-bff/sessions/{session_id}/artifact/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/zip")
    preview = await test_client.get(f"/api/skill-agent-bff/sessions/{session_id}/artifact/preview")
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("text/html")
    assert "sales" in preview.text
