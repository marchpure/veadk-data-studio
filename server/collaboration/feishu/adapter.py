from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.collaboration.contracts import ChannelResult, ResponseRef
from server.collaboration.feishu.client import FeishuApiClient, feishu_error_requires_reauth
from server.collaboration.models import CollaborationConversation, CollaborationInstallation
from server.collaboration.repositories import CollaborationInstallationRepository, CollaborationResponseRefRepository
from server.services.crypto_service import CryptoService

FEISHU_TEXT_MESSAGE_MAX_CHARS = 3800
FEISHU_TRUNCATION_NOTICE = "结果较长，已截断。请在 Byaan 中打开 Notebook 查看完整结果。"
FEISHU_DELIVERY_ATTEMPTS = 3


class FeishuChannelAdapter:
    def __init__(self, session: AsyncSession, installation: CollaborationInstallation) -> None:
        self.session = session
        self.installation = installation

    async def _client(self) -> FeishuApiClient:
        credentials = await CryptoService.decrypt_config(self.installation.credentials_encrypted, self.session)
        return FeishuApiClient(app_id=credentials["app_id"], app_secret=credentials["app_secret"])

    async def probe(self) -> dict:
        client = await self._client()
        result = await client.probe()
        updates = {
            "bot_external_id": result.get("bot_external_id"),
            "external_tenant_id": result.get("external_tenant_id") or self.installation.external_tenant_id,
            "external_tenant_name": result.get("external_tenant_name") or self.installation.external_tenant_name,
            "health_status": "configured",
            "health_error": None,
        }
        config = dict(self.installation.config_json or {})
        if result.get("tenant_token_expires_at"):
            config["tenant_token_expires_at"] = result.get("tenant_token_expires_at")
        if config:
            updates["config_json"] = config
        await CollaborationInstallationRepository(self.session).update(self.installation, **updates)
        return result

    async def start_response(
        self,
        conversation: CollaborationConversation,
        response: ChannelResult,
        *,
        reply_to_message_id: str | None = None,
    ) -> ResponseRef:
        client = await self._client()
        if reply_to_message_id:
            result = await _with_delivery_retry(
                lambda: client.reply_text_message(
                    message_id=reply_to_message_id,
                    text=response.summary,
                    request_uuid=f"feishu-ack-{conversation.id}-{reply_to_message_id}",
                )
            )
        else:
            result = await _with_delivery_retry(
                lambda: client.send_text_message(
                    receive_id_type="chat_id",
                    receive_id=conversation.external_chat_id,
                    text=response.summary,
                    root_id=conversation.external_root_id,
                    request_uuid=f"feishu-ack-{conversation.id}",
                )
            )
        message_id = (
            result.get("message_id")
            or result.get("message", {}).get("message_id")
            or result.get("data", {}).get("message_id")
            or ""
        )
        ref = await CollaborationResponseRefRepository(self.session).create(
            run_id=response.run_id,
            conversation_id=conversation.id,
            platform_message_id=str(message_id),
            status=response.status.value if hasattr(response.status, "value") else str(response.status),
        )
        return ResponseRef(
            run_id=ref.run_id,
            conversation_id=ref.conversation_id,
            platform_message_id=ref.platform_message_id,
            platform_card_id=ref.platform_card_id,
            sequence=ref.sequence,
            status=ref.status,
        )

    async def finish_response(
        self,
        response_ref: ResponseRef,
        result: ChannelResult,
        *,
        conversation: CollaborationConversation,
    ) -> ResponseRef:
        client = await self._client()
        summary = self._render_final_text(result, conversation)
        if response_ref.platform_message_id:
            sent = await _with_delivery_retry(
                lambda: client.reply_text_message(
                    message_id=response_ref.platform_message_id,
                    text=summary,
                    request_uuid=f"feishu-final-{conversation.id}-{result.run_id}-{response_ref.sequence}",
                )
            )
        else:
            sent = await _with_delivery_retry(
                lambda: client.send_text_message(
                    receive_id_type="chat_id",
                    receive_id=conversation.external_chat_id,
                    text=summary,
                    root_id=conversation.external_root_id,
                    request_uuid=f"feishu-final-{conversation.id}-{result.run_id}-{response_ref.sequence}",
                )
            )
        message_id = (
            sent.get("message_id")
            or sent.get("message", {}).get("message_id")
            or sent.get("data", {}).get("message_id")
            or response_ref.platform_message_id
        )
        previous_platform_message_id = response_ref.platform_message_id
        response_ref.platform_message_id = str(message_id)
        response_ref.status = result.status.value if hasattr(result.status, "value") else str(result.status)
        response_ref.sequence += 1
        await CollaborationResponseRefRepository(self.session).update_by_message(
            conversation_id=conversation.id,
            platform_message_id=previous_platform_message_id,
            run_id=result.run_id,
            next_platform_message_id=response_ref.platform_message_id,
            platform_card_id=response_ref.platform_card_id,
            status=response_ref.status,
            sequence=response_ref.sequence,
        )
        return response_ref

    @staticmethod
    def _render_final_text(result: ChannelResult, conversation: CollaborationConversation) -> str:
        refs: list[str] = []
        notebook_id = result.artifact_id or (str(conversation.notebook_id) if conversation.notebook_id else None)
        if notebook_id:
            refs.append(f"Notebook: {notebook_id}")
            refs.append(f"Open in Byaan: /notebooks/{notebook_id}")
        if result.run_id:
            refs.append(f"Run: {result.run_id}")
        if not refs:
            return _truncate_text(result.summary)
        refs_block = "\n\n---\n" + "\n".join(refs)
        text = f"{result.summary}{refs_block}"
        if len(text) <= FEISHU_TEXT_MESSAGE_MAX_CHARS:
            return text

        truncation_block = f"\n\n{FEISHU_TRUNCATION_NOTICE}{refs_block}"
        available_summary_chars = FEISHU_TEXT_MESSAGE_MAX_CHARS - len(truncation_block) - 2
        truncated_summary = result.summary[: max(0, available_summary_chars)].rstrip()
        return f"{truncated_summary}\n…{truncation_block}"[:FEISHU_TEXT_MESSAGE_MAX_CHARS]


def _truncate_text(text: str) -> str:
    if len(text) <= FEISHU_TEXT_MESSAGE_MAX_CHARS:
        return text
    suffix = f"\n\n{FEISHU_TRUNCATION_NOTICE}"
    available_chars = FEISHU_TEXT_MESSAGE_MAX_CHARS - len(suffix) - 2
    return f"{text[: max(0, available_chars)].rstrip()}\n…{suffix}"[:FEISHU_TEXT_MESSAGE_MAX_CHARS]


async def _with_delivery_retry(operation: Callable[[], Awaitable[dict]]) -> dict:
    last_error: Exception | None = None
    for attempt in range(FEISHU_DELIVERY_ATTEMPTS):
        try:
            return await operation()
        except Exception as exc:
            last_error = exc
            if feishu_error_requires_reauth(exc) or attempt == FEISHU_DELIVERY_ATTEMPTS - 1:
                raise
            await asyncio.sleep(0.2 * (attempt + 1))
    assert last_error is not None
    raise last_error


async def feishu_adapter_for_installation(session: AsyncSession, installation_id: UUID) -> FeishuChannelAdapter:
    installation = await CollaborationInstallationRepository(session).get(installation_id)
    if not installation:
        raise ValueError(f"Feishu installation not found: {installation_id}")
    return FeishuChannelAdapter(session, installation)
