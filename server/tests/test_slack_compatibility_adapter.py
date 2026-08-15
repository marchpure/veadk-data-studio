from __future__ import annotations

from uuid import uuid4

import pytest

from server.collaboration.slack.compatibility_adapter import SlackCompatibilityAdapter
from server.schemas.agent import AgentRequest

pytestmark = pytest.mark.asyncio


async def test_slack_compatibility_adapter_delegates_agent_run(monkeypatch, test_session):
    async def fake_run_agent(request, session, tenant_id, user_id=None):
        from server.collaboration.channel_agent_service import AgentRunResult

        return AgentRunResult(
            run_id="run-slack",
            raw_response="ok",
            notebook_id=uuid4(),
            dashboard_generated=True,
            query_executed=True,
        )

    monkeypatch.setattr("server.collaboration.channel_agent_service.ChannelAgentService.run_agent", fake_run_agent)

    raw_response, notebook_id, dashboard_generated, query_executed = await SlackCompatibilityAdapter.run_agent(
        request=AgentRequest(message="hello"),
        session=test_session,
        tenant_id=uuid4(),
    )

    assert raw_response == "ok"
    assert notebook_id is not None
    assert dashboard_generated is True
    assert query_executed is True
