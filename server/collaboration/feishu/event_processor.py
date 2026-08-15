from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from server.collaboration.channel_agent_service import ChannelAgentService
from server.collaboration.contracts import ChannelResultStatus
from server.collaboration.feishu.adapter import FeishuChannelAdapter
from server.collaboration.feishu.normalizer import normalize_feishu_message_event, should_trigger_feishu_message
from server.collaboration.models import CollaborationInstallation
from server.collaboration.repositories import CollaborationConversationRepository, CollaborationEventRepository
from server.collaboration.result_renderer import PlainTextChannelRenderer
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


class FeishuEventProcessor:
    def __init__(self, session: AsyncSession, installation: CollaborationInstallation) -> None:
        self.session = session
        self.installation = installation

    async def process_raw_message_event(self, raw_event: dict | object) -> dict:
        event = normalize_feishu_message_event(
            raw_event,
            installation_id=self.installation.id,
            bot_external_id=self.installation.bot_external_id,
        )
        repo = CollaborationEventRepository(self.session)
        event_log, duplicate = await repo.record_received(
            installation_id=self.installation.id,
            platform="feishu",
            external_event_id=event.event_id,
            event_type=event.event_type.value,
            external_chat_id=event.chat_id,
            external_user_id=event.sender_external_id,
        )
        if duplicate:
            return {"status": "duplicate", "event_id": event.event_id}

        try:
            await repo.mark(event_log, "processing")
            self.installation.last_event_at = event.occurred_at or datetime.now()
            await self.session.commit()

            conversation_repo = CollaborationConversationRepository(self.session)
            existing_conversation = await conversation_repo.get_by_external_key(
                self.installation.id,
                event.chat_id,
                event.conversation_root_id,
            )
            is_followup = bool(
                existing_conversation
                and existing_conversation.bot_owned
                and event.conversation_root_id
                and (not self.installation.bot_external_id or self.installation.bot_external_id not in event.mentions)
            )
            if not should_trigger_feishu_message(
                event,
                self.installation.bot_external_id,
                has_existing_conversation=bool(existing_conversation and existing_conversation.bot_owned),
            ):
                await repo.mark(event_log, "ignored")
                return {"status": "ignored", "event_id": event.event_id}

            conversation = existing_conversation or await ChannelAgentService.get_or_create_conversation(
                installation=self.installation,
                event=event,
                session=self.session,
                bot_owned=True,
            )
            adapter = FeishuChannelAdapter(self.session, self.installation)
            ack = PlainTextChannelRenderer.started()
            response_ref = await adapter.start_response(conversation, ack, reply_to_message_id=event.message_id)
            agent_result = await ChannelAgentService.process_event(
                installation=self.installation,
                conversation=conversation,
                event=event,
                session=self.session,
                user_id=None,
                is_followup=is_followup,
            )
            channel_result = agent_result.to_channel_result()
            channel_result.status = ChannelResultStatus.COMPLETED
            await adapter.finish_response(response_ref, channel_result, conversation=conversation)
            await repo.mark(event_log, "completed")
            return {
                "status": "completed",
                "event_id": event.event_id,
                "conversation_id": str(conversation.id),
                "notebook_id": str(conversation.notebook_id) if conversation.notebook_id else None,
            }
        except Exception as exc:
            logger.error(f"Failed to process Feishu event {event.event_id}: {exc}", exc_info=True)
            await repo.mark(event_log, "failed_terminal", error_message=str(exc))
            raise


async def process_feishu_event(session: AsyncSession, installation: CollaborationInstallation, raw_event: dict | object) -> dict:
    return await FeishuEventProcessor(session, installation).process_raw_message_event(raw_event)
