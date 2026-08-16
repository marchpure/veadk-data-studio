from __future__ import annotations

import asyncio
import json
import re
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.collaboration.contracts import ChannelEvent, ChannelResult, ChannelResultStatus
from server.collaboration.models import CollaborationConversation, CollaborationInstallation
from server.collaboration.repositories import CollaborationConversationRepository
from server.constants.models import MODELS_BY_PROVIDER
from server.models.llm_connections import LLMConnection
from server.repositories.custom_skill import CustomSkillRepository
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


@dataclass(slots=True)
class ChannelAgentContext:
    tenant_id: UUID
    installation_id: UUID
    conversation_id: UUID
    platform: str
    chat_type: str
    external_chat_id: str
    external_root_id: str | None
    inbound_message_id: str
    sender_external_id: str
    notebook_id: UUID | None
    default_llm_connection_id: UUID | None
    is_followup: bool

    @classmethod
    def from_event(
        cls,
        *,
        installation: CollaborationInstallation,
        conversation: CollaborationConversation,
        event: ChannelEvent,
        is_followup: bool,
    ) -> ChannelAgentContext:
        return cls(
            tenant_id=installation.tenant_id,
            installation_id=installation.id,
            conversation_id=conversation.id,
            platform=installation.platform,
            chat_type=event.chat_type.value,
            external_chat_id=event.chat_id,
            external_root_id=event.conversation_root_id,
            inbound_message_id=event.message_id,
            sender_external_id=event.sender_external_id,
            notebook_id=conversation.notebook_id,
            default_llm_connection_id=installation.default_llm_connection_id,
            is_followup=is_followup,
        )

    def to_prompt_section(self) -> str:
        notebook_id = str(self.notebook_id) if self.notebook_id else "new_notebook_requested"
        llm_connection_id = str(self.default_llm_connection_id) if self.default_llm_connection_id else "not_configured"
        root_id = self.external_root_id or "__root__"
        return f"""Delivery and identity context:
- tenant_id: {self.tenant_id}
- installation_id: {self.installation_id}
- conversation_id: {self.conversation_id}
- platform: {self.platform}
- chat_type: {self.chat_type}
- external_chat_id: {self.external_chat_id}
- external_root_id: {root_id}
- inbound_message_id: {self.inbound_message_id}
- sender_external_id: {self.sender_external_id}
- notebook_id: {notebook_id}
- default_llm_connection_id: {llm_connection_id}
- is_followup: {str(self.is_followup).lower()}

Use these IDs only for routing, audit, and follow-up continuity. Do not expose raw external IDs in the final user-facing answer unless explicitly required for troubleshooting."""


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
    async def get_tenant_llm_connection(
        *,
        llm_connection_id: UUID,
        tenant_id: UUID,
        session: AsyncSession,
    ) -> LLMConnection | None:
        result = await session.execute(
            select(LLMConnection).where(
                LLMConnection.id == llm_connection_id,
                LLMConnection.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def resolve_model_for_connection(
        llm_connection_id: UUID,
        session: AsyncSession,
        *,
        tenant_id: UUID,
    ) -> str | None:
        connection = await ChannelAgentService.get_tenant_llm_connection(
            llm_connection_id=llm_connection_id,
            tenant_id=tenant_id,
            session=session,
        )
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
        channel_context: ChannelAgentContext | None = None,
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
        delivery_context = f"\n{channel_context.to_prompt_section()}\n" if channel_context else ""
        return f"""This message came from a collaboration channel.
Channel context:
- platform: {platform}
- surface: {surface}
- locale: {locale}
- supports_streaming_card: {str(supports_streaming_card).lower()}
- supports_files: {str(supports_files).lower()}
{delivery_context}
{skill_instructions}
When processing this request:
- Route data questions through Published Org Data Skill → Source Skill → Governed raw fallback.
- Use the bound Notebook memory for prior context when present.
- Preserve tenant boundaries and do not use assets outside the current tenant.
- If data access is unavailable or permission is missing, say so explicitly instead of inventing results.
- Keep references to the Notebook, Agent Run, Semantic Skill, data freshness, and evidence when available.
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
            await session.refresh(conversation)
            llm_connection = await ChannelAgentService.get_tenant_llm_connection(
                llm_connection_id=installation.default_llm_connection_id,
                tenant_id=installation.tenant_id,
                session=session,
            )
            if not llm_connection:
                raise ValueError("Default LLM connection must belong to the current tenant")
            resolved_model = await ChannelAgentService.resolve_model_for_connection(
                installation.default_llm_connection_id,
                session,
                tenant_id=installation.tenant_id,
            )
            prompt = await ChannelAgentService.build_prompt(
                platform=installation.platform,
                question=event.text,
                tenant_id=installation.tenant_id,
                session=session,
                channel_context=ChannelAgentContext.from_event(
                    installation=installation,
                    conversation=conversation,
                    event=event,
                    is_followup=is_followup,
                ),
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
