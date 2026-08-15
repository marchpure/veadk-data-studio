from __future__ import annotations

from server.collaboration.channel_agent_service import ChannelAgentService
from server.schemas.agent import AgentRequest


class SlackCompatibilityAdapter:
    """Migration shim that keeps Slack behavior while core Agent execution moves channel-neutral."""

    @staticmethod
    async def run_agent(*, request: AgentRequest, session, tenant_id, user_id=None):
        result = await ChannelAgentService.run_agent(
            request=request,
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return result.raw_response, result.notebook_id, result.dashboard_generated, result.query_executed

    @staticmethod
    async def build_slack_prompt(*, question: str, tenant_id, session, is_followup: bool = False) -> str:
        base = await ChannelAgentService.build_prompt(
            platform="slack",
            question=question,
            tenant_id=tenant_id,
            session=session,
            is_followup=is_followup,
            locale="en-US",
            supports_streaming_card=False,
            supports_files=True,
        )
        return (
            f"{base}\n\nSlack compatibility requirements:\n"
            "- Format the final message for Slack Markdown.\n"
            "- For query results, use pipe-delimited Markdown tables.\n"
        )
