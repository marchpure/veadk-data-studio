from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.collaboration.contracts import ChannelResult, ResponseRef
from server.collaboration.feishu.client import FeishuApiClient
from server.collaboration.models import CollaborationConversation, CollaborationInstallation
from server.collaboration.repositories import CollaborationInstallationRepository, CollaborationResponseRefRepository
from server.services.crypto_service import CryptoService


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
            "health_status": "ok",
            "health_error": None,
        }
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
            result = await client.reply_text_message(message_id=reply_to_message_id, text=response.summary)
        else:
            result = await client.send_text_message(
                receive_id_type="chat_id",
                receive_id=conversation.external_chat_id,
                text=response.summary,
                root_id=conversation.external_root_id,
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
        if response_ref.platform_message_id:
            sent = await client.reply_text_message(message_id=response_ref.platform_message_id, text=result.summary)
        else:
            sent = await client.send_text_message(
                receive_id_type="chat_id",
                receive_id=conversation.external_chat_id,
                text=result.summary,
                root_id=conversation.external_root_id,
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


async def feishu_adapter_for_installation(session: AsyncSession, installation_id: UUID) -> FeishuChannelAdapter:
    installation = await CollaborationInstallationRepository(session).get(installation_id)
    if not installation:
        raise ValueError(f"Feishu installation not found: {installation_id}")
    return FeishuChannelAdapter(session, installation)
