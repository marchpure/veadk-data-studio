from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.collaboration.channel_agent_service import ChannelAgentService
from server.collaboration.contracts import ChannelResultStatus
from server.collaboration.feishu.adapter import FeishuChannelAdapter
from server.collaboration.feishu.client import FeishuApiError, feishu_error_requires_reauth, safe_feishu_error_message
from server.collaboration.feishu.normalizer import normalize_feishu_message_event, should_trigger_feishu_message
from server.collaboration.feishu.subscription import FEISHU_REQUIRED_EVENT_TYPES, feishu_event_subscription_payload
from server.collaboration.models import CollaborationInstallation
from server.collaboration.repositories import (
    CollaborationConversationRepository,
    CollaborationDeliveryTargetRepository,
    CollaborationEventRepository,
    ExternalIdentityRepository,
)
from server.collaboration.result_renderer import PlainTextChannelRenderer
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

FEISHU_AGENT_TIMEOUT_SECONDS = 120.0


async def _find_enabled_delivery_target(session: AsyncSession, installation: CollaborationInstallation, event) -> bool:
    repo = CollaborationDeliveryTargetRepository(session)
    root_id = None if event.chat_type.value == "p2p" else event.conversation_root_id
    target = await repo.find(
        installation_id=installation.id,
        target_type=event.chat_type.value,
        external_target_id=event.chat_id,
        external_root_id=root_id,
    )
    if CollaborationDeliveryTargetRepository.is_enabled(target):
        return True

    if event.chat_type.value == "topic_group":
        group_target = await repo.find(
            installation_id=installation.id,
            target_type="group",
            external_target_id=event.chat_id,
            external_root_id=None,
        )
        if CollaborationDeliveryTargetRepository.is_enabled(group_target):
            return True

    if event.chat_type.value == "group":
        chat_target = await repo.find(
            installation_id=installation.id,
            target_type="group",
            external_target_id=event.chat_id,
            external_root_id=None,
        )
        if CollaborationDeliveryTargetRepository.is_enabled(chat_target):
            return True

    return False


async def _record_observed_disabled_target(session: AsyncSession, installation: CollaborationInstallation, event) -> None:
    target = await CollaborationDeliveryTargetRepository(session).get_or_create(
        installation_id=installation.id,
        target_type=event.chat_type.value,
        external_target_id=event.chat_id,
        external_root_id=None if event.chat_type.value in {"group", "p2p"} else event.conversation_root_id,
        display_name=None,
        is_verified=False,
    )
    config = dict(target.config_json or {})
    config.setdefault("is_enabled", False)
    config.setdefault("source", "observed_event")
    config["last_seen_event_at"] = datetime.now().isoformat()
    target.config_json = config
    target.is_verified = False
    await session.commit()


def _mark_event_subscription_observed(installation: CollaborationInstallation, *, event_id: str) -> None:
    config = dict(installation.config_json or {})
    subscription = feishu_event_subscription_payload(config)
    now = datetime.now().isoformat()
    subscription.update(
        {
            "required_event_types": FEISHU_REQUIRED_EVENT_TYPES,
            "remote_status": "observed",
            "first_event_observed_at": subscription.get("first_event_observed_at") or now,
            "last_event_observed_at": now,
            "last_event_id": event_id,
            "ready": True,
            "operator_action": "Event im.message.receive_v1 has been observed over the Feishu WebSocket connection.",
        }
    )
    config["event_subscription"] = subscription
    installation.config_json = config


def _mark_installation_needs_reauth_if_required(
    installation: CollaborationInstallation,
    error: object,
) -> bool:
    if not isinstance(error, FeishuApiError) or not feishu_error_requires_reauth(error):
        return False
    installation.is_active = False
    installation.health_status = "needs_reauth"
    installation.health_error = safe_feishu_error_message(error)
    return True


class FeishuEventProcessor:
    def __init__(self, session: AsyncSession, installation: CollaborationInstallation) -> None:
        self.session = session
        self.installation = installation

    async def process_raw_message_event(
        self,
        raw_event: dict | object,
        *,
        preaccepted_event_log_id: UUID | None = None,
    ) -> dict:
        event = normalize_feishu_message_event(
            raw_event,
            installation_id=self.installation.id,
            bot_external_id=self.installation.bot_external_id,
        )
        repo = CollaborationEventRepository(self.session)
        if preaccepted_event_log_id:
            event_log = await repo.get(preaccepted_event_log_id)
            if not event_log or event_log.installation_id != self.installation.id or event_log.external_event_id != event.event_id:
                raise ValueError("Preaccepted Feishu event log does not match the message event")
        else:
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

        conversation = None
        try:
            await repo.mark(event_log, "processing")
            external_identity = await ExternalIdentityRepository(self.session).get_or_create_seen(
                tenant_id=self.installation.tenant_id,
                platform="feishu",
                installation_id=self.installation.id,
                external_user_id=event.sender_external_id,
                union_id=event.raw_reference.get("sender_id", {}).get("union_id"),
            )
            mapped_user_id = external_identity.byaan_user_id or external_identity.user_id
            has_mapped_identity = mapped_user_id is not None
            self.installation.last_event_at = event.occurred_at or datetime.now()
            _mark_event_subscription_observed(self.installation, event_id=event.event_id)
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

            if not await _find_enabled_delivery_target(self.session, self.installation, event):
                await _record_observed_disabled_target(self.session, self.installation, event)
                await repo.mark(event_log, "target_unbound")
                return {"status": "target_unbound", "event_id": event.event_id}

            conversation = existing_conversation or await ChannelAgentService.get_or_create_conversation(
                installation=self.installation,
                event=event,
                session=self.session,
                bot_owned=has_mapped_identity,
            )
            adapter = FeishuChannelAdapter(self.session, self.installation)
            if not has_mapped_identity:
                identity_required = PlainTextChannelRenderer.failed(
                    "identity_unmapped",
                    "无法处理此数据请求：请先联系管理员完成飞书身份与 Byaan 用户的映射。",
                )
                await adapter.start_response(conversation, identity_required, reply_to_message_id=event.message_id)
                await repo.mark(
                    event_log,
                    "identity_unmapped",
                    conversation_id=conversation.id,
                    notebook_id=conversation.notebook_id,
                )
                return {
                    "status": "identity_unmapped",
                    "event_id": event.event_id,
                    "conversation_id": str(conversation.id),
                    "notebook_id": str(conversation.notebook_id) if conversation.notebook_id else None,
                }

            ack = PlainTextChannelRenderer.started()
            response_ref = await adapter.start_response(conversation, ack, reply_to_message_id=event.message_id)
            try:
                agent_result = await asyncio.wait_for(
                    ChannelAgentService.process_event(
                        installation=self.installation,
                        conversation=conversation,
                        event=event,
                        session=self.session,
                        user_id=mapped_user_id,
                        is_followup=is_followup,
                    ),
                    timeout=FEISHU_AGENT_TIMEOUT_SECONDS,
                )
                channel_result = agent_result.to_channel_result()
                channel_result.status = ChannelResultStatus.COMPLETED
                await adapter.finish_response(response_ref, channel_result, conversation=conversation)
                await repo.mark(
                    event_log,
                    "completed",
                    conversation_id=conversation.id,
                    notebook_id=conversation.notebook_id,
                    run_id=agent_result.run_id,
                )
                return {
                    "status": "completed",
                    "event_id": event.event_id,
                    "conversation_id": str(conversation.id),
                    "notebook_id": str(conversation.notebook_id) if conversation.notebook_id else None,
                }
            except TimeoutError:
                safe_error = "Agent processing timed out"
                logger.error("Timed out processing Feishu event %s", event.event_id)
                timeout_result = PlainTextChannelRenderer.failed(
                    "timed_out",
                    "处理超时：当前分析耗时过长，已停止本次处理。请稍后重试，或缩小问题范围后再次发送。",
                )
                try:
                    await adapter.finish_response(response_ref, timeout_result, conversation=conversation)
                except Exception as delivery_exc:
                    _mark_installation_needs_reauth_if_required(self.installation, delivery_exc)
                    delivery_error = safe_feishu_error_message(delivery_exc)
                    logger.error(
                        "Failed to send Feishu timeout response for event %s: %s",
                        event.event_id,
                        delivery_error,
                    )
                    safe_error = safe_feishu_error_message(
                        f"{safe_error}; timeout response delivery failed: {delivery_error}"
                    )
                await repo.mark(
                    event_log,
                    "timed_out",
                    error_message=safe_error,
                    conversation_id=conversation.id,
                    notebook_id=conversation.notebook_id,
                    run_id="timed_out",
                )
                return {
                    "status": "timed_out",
                    "event_id": event.event_id,
                    "conversation_id": str(conversation.id),
                    "notebook_id": str(conversation.notebook_id) if conversation.notebook_id else None,
                }
            except Exception as exc:
                _mark_installation_needs_reauth_if_required(self.installation, exc)
                safe_error = safe_feishu_error_message(exc)
                logger.error("Failed to process Feishu event %s: %s", event.event_id, safe_error)
                failure = PlainTextChannelRenderer.failed(
                    "failed",
                    "处理失败：当前无法完成这次分析。错误已记录，管理员可在协作集成页面查看。",
                )
                try:
                    await adapter.finish_response(response_ref, failure, conversation=conversation)
                except Exception as delivery_exc:
                    _mark_installation_needs_reauth_if_required(self.installation, delivery_exc)
                    delivery_error = safe_feishu_error_message(delivery_exc)
                    logger.error(
                        "Failed to send Feishu failure response for event %s: %s",
                        event.event_id,
                        delivery_error,
                    )
                    safe_error = safe_feishu_error_message(
                        f"{safe_error}; failure response delivery failed: {delivery_error}"
                    )
                await repo.mark(
                    event_log,
                    "failed_terminal",
                    error_message=safe_error,
                    conversation_id=conversation.id,
                    notebook_id=conversation.notebook_id,
                    run_id="failed",
                )
                return {
                    "status": "failed_terminal",
                    "event_id": event.event_id,
                    "conversation_id": str(conversation.id),
                    "notebook_id": str(conversation.notebook_id) if conversation.notebook_id else None,
                }
        except Exception as exc:
            _mark_installation_needs_reauth_if_required(self.installation, exc)
            safe_error = safe_feishu_error_message(exc)
            logger.error("Failed to process Feishu event %s: %s", event.event_id, safe_error)
            await repo.mark(
                event_log,
                "failed_terminal",
                error_message=safe_error,
                conversation_id=conversation.id if conversation else None,
                notebook_id=conversation.notebook_id if conversation else None,
            )
            return {
                "status": "failed_terminal",
                "event_id": event.event_id,
                "conversation_id": str(conversation.id) if conversation else None,
                "notebook_id": str(conversation.notebook_id) if conversation and conversation.notebook_id else None,
            }


async def process_feishu_event(
    session: AsyncSession,
    installation: CollaborationInstallation,
    raw_event: dict | object,
    *,
    preaccepted_event_log_id: UUID | None = None,
) -> dict:
    return await FeishuEventProcessor(session, installation).process_raw_message_event(
        raw_event,
        preaccepted_event_log_id=preaccepted_event_log_id,
    )
