import json

import pytest

from server.routers import skill_agent_bff
from server.services.w5_skill_agent_adapter import W5AdapterError, W5Invocation, W5SkillAgentAdapter


@pytest.mark.asyncio
async def test_adapter_forwards_runtime_request_and_parses_incremental_events(monkeypatch):
    calls = []

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return (
                b'data: {"type":"planning"}\n'
                b'data: {"type":"revision.created","revision":"rev-1"}\n'
                b'data: {"type":"artifact.created","artifact":{"files":["SKILL.md"]}}\n',
                b"",
            )

    async def fake_exec(*command, **kwargs):
        calls.append(command)
        return FakeProcess()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    adapter = W5SkillAgentAdapter(runtime_id="runtime-1", region="cn-beijing", cli_path="agentkit")
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


@pytest.mark.asyncio
async def test_adapter_fails_closed_without_auth_or_endpoint():
    with pytest.raises(W5AdapterError, match="OAuth"):
        async for _ in W5SkillAgentAdapter(base_url="https://w5.example").invoke(
            W5Invocation("goal", [], [], None, None, "session", None)
        ):
            pass
    with pytest.raises(W5AdapterError, match="RUNTIME_ID"):
        async for _ in W5SkillAgentAdapter().invoke(
            W5Invocation("goal", [], [], None, None, "session", "delegated-ref")
        ):
            pass


def test_bff_restart_marks_running_sessions_interrupted(tmp_path, monkeypatch):
    path = tmp_path / "sessions.json"
    path.write_text(json.dumps({"session-1": {"id": "session-1", "status": "running", "events": []}}))
    monkeypatch.setattr(skill_agent_bff, "_path", path)
    skill_agent_bff._load()
    assert skill_agent_bff._sessions["session-1"]["status"] == "interrupted"
    assert skill_agent_bff._sessions["session-1"]["events"][0]["code"] == "INVOCATION_INTERRUPTED"
