from __future__ import annotations

import asyncio
import json
import re
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from server.collaboration.contracts import ChannelEvent, ChannelResult, ChannelResultStatus
from server.collaboration.models import CollaborationConversation, CollaborationInstallation
from server.collaboration.repositories import CollaborationConversationRepository
from server.constants.models import MODELS_BY_PROVIDER
from server.repositories.custom_skill import CustomSkillRepository
from server.repositories.llm_connections import LLMConnectionRepository
from server.schemas.agent import AgentRequest
from server.services.crypto_service import CryptoService
from server.services.unified_agent import stream_handoff_agent_response
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

_conversation_locks: dict[str, threading.Lock] = {}
_conversation_locks_guard = threading.Lock()


@dataclass(slots=True)
class AgentRunResult:
    run_id: str
    raw_response: str
    notebook_id: UUID | None
    dashboard_generated: bool
    query_executed: bool

    def to_channel_result(self) -> ChannelResult:
        return ChannelResult(
            run_id=self.run_id,
            status=ChannelResultStatus.COMPLETED,
            summary=self.raw_response,
            artifact_id=str(self.notebook_id) if self.notebook_id else None,
        )


def conversation_lock_key(conversation: CollaborationConversation) -> str:
    return f"{conversation.installation_id}:{conversation.external_chat_id}:{conversation.normalized_root_id}"


def _conversation_lock(key: str) -> threading.Lock:
    with _conversation_locks_guard:
        lock = _conversation_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _conversation_locks[key] = lock
        return lock


@asynccontextmanager
async def ordered_conversation_execution(conversation: CollaborationConversation):
    """Serialize agent runs for one external conversation across event loops."""

    lock = _conversation_lock(conversation_lock_key(conversation))
    await asyncio.to_thread(lock.acquire)
    try:
        yield
    finally:
        lock.release()


class ChannelAgentService:
    """Platform-neutral Notebook + Agent orchestration for collaboration channels."""

    CONFIRMATION_MESSAGE = "正在分析，我会在当前会话里回复结果。"

    @staticmethod
    async def resolve_model_for_connection(llm_connection_id: UUID, session: AsyncSession) -> str | None:
        connection = await LLMConnectionRepository(session).get(llm_connection_id)
        if not connection:
            return None
        try:
            cfg = await CryptoService.decrypt_config(connection.config, session) if connection.config else {}
        except Exception:
            cfg = {}
        stored_model = cfg.get("model") if isinstance(cfg, dict) else None
        if stored_model:
            return stored_model
        provider_models = MODELS_BY_PROVIDER.get(connection.type, [])
        return provider_models[0] if provider_models else None

    @staticmethod
    async def build_prompt(
        *,
        platform: str,
        question: str,
        tenant_id: UUID,
        session: AsyncSession,
        is_followup: bool = False,
        locale: str = "zh-CN",
        supports_streaming_card: bool = False,
        supports_files: bool = True,
    ) -> str:
        inbound_skills = await CustomSkillRepository(session).get_by_type(tenant_id, f"{platform}_inbound")
        generic_channel_skills = await CustomSkillRepository(session).get_by_type(tenant_id, "channel_inbound")
        all_skills = [s for s in [*inbound_skills, *generic_channel_skills] if s.is_active]

        skill_instructions = ""
        if all_skills:
            combined = "\n\n".join(f"### {skill.name}\n{skill.instructions}" for skill in all_skills)
            skill_instructions = f"\nCHANNEL INBOUND SKILLS:\n{combined}\n"

        surface = "follow-up" if is_followup else "new request"
        return f"""This message came from a collaboration channel.
Channel context:
- platform: {platform}
- surface: {surface}
- locale: {locale}
- supports_streaming_card: {str(supports_streaming_card).lower()}
- supports_files: {str(supports_files).lower()}
{skill_instructions}
When processing this request:
- Use the bound Notebook memory for prior context when present.
- Return the final business answer in concise Markdown.
- Keep transport-specific formatting out of the core answer.
- If query results are tabular, use plain Markdown tables.

User's message:
{question}"""

    @staticmethod
    async def run_agent(
        request: AgentRequest,
        session: AsyncSession,
        tenant_id: UUID,
        user_id: UUID | None = None,
    ) -> AgentRunResult:
        response_parts: list[str] = []
        notebook_id: UUID | None = None
        dashboard_generated = False
        query_executed = False
        run_id = uuid4().hex

        async for event in stream_handoff_agent_response(request, session, tenant_id=tenant_id, user_id=user_id):
            if not event.startswith("data: "):
                continue
            try:
                data = json.loads(event[6:])
            except json.JSONDecodeError:
                continue
            if data.get("type") == "content":
                response_parts.append(data.get("text", ""))
            elif data.get("type") == "notebook_created":
                notebook_id = UUID(str(data.get("notebook_id")))
            elif data.get("type") == "html_edit_complete":
                dashboard_generated = True
            elif data.get("type") == "datasource_selected":
                query_executed = True
            elif data.get("type") == "error":
                response_parts.append(f"Error: {data.get('text', 'Unknown error occurred')}")
                break

        return AgentRunResult(
            run_id=run_id,
            raw_response="".join(response_parts) or "I processed your request but have no response to share.",
            notebook_id=notebook_id,
            dashboard_generated=dashboard_generated,
            query_executed=query_executed,
        )

    @staticmethod
    async def get_or_create_conversation(
        *,
        installation: CollaborationInstallation,
        event: ChannelEvent,
        session: AsyncSession,
        title_text: str | None = None,
        root_id_override: str | None = None,
        bot_owned: bool = False,
    ) -> CollaborationConversation:
        title = ChannelAgentService.derive_title(title_text or event.text)
        return await CollaborationConversationRepository(session).get_or_create(
            installation_id=installation.id,
            external_chat_id=event.chat_id,
            external_root_id=root_id_override if root_id_override is not None else event.conversation_root_id,
            external_user_id=event.sender_external_id,
            chat_type=event.chat_type.value,
            title=title,
            bot_owned=bot_owned,
        )

    @staticmethod
    async def process_event(
        *,
        installation: CollaborationInstallation,
        conversation: CollaborationConversation,
        event: ChannelEvent,
        session: AsyncSession,
        user_id: UUID | None = None,
        is_followup: bool = False,
    ) -> AgentRunResult:
        if not installation.default_llm_connection_id:
            raise ValueError("No LLM connection configured for collaboration installation")

        async with ordered_conversation_execution(conversation):
            resolved_model = await ChannelAgentService.resolve_model_for_connection(
                installation.default_llm_connection_id, session
            )
            prompt = await ChannelAgentService.build_prompt(
                platform=installation.platform,
                question=event.text,
                tenant_id=installation.tenant_id,
                session=session,
                is_followup=is_followup,
                supports_streaming_card=False,
            )
            agent_request = AgentRequest(
                message=prompt,
                notebook_id=conversation.notebook_id,
                llm_connection_id=installation.default_llm_connection_id,
                create_notebook=conversation.notebook_id is None,
                model=resolved_model,
            )
            result = await ChannelAgentService.run_agent(
                request=agent_request,
                session=session,
                tenant_id=installation.tenant_id,
                user_id=user_id,
            )
            if result.notebook_id and conversation.notebook_id is None:
                conversation.notebook_id = result.notebook_id
                await session.commit()
                await session.refresh(conversation)
            conversation.bot_owned = True
            await session.commit()
            return result

    @staticmethod
    def derive_title(text: str | None) -> str | None:
        if not text:
            return None
        collapsed = " ".join(text.split())
        return collapsed[:120] if collapsed else None

    @staticmethod
    def clean_mentions(text: str, mention_patterns: list[str]) -> str:
        cleaned = text
        for pattern in mention_patterns:
            cleaned = cleaned.replace(pattern, "")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()
