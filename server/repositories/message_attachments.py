from __future__ import annotations

from sqlalchemy import select

from server.models.message_attachments import MessageAttachment
from server.repositories.base import AsyncCRUDRepository


class MessageAttachmentRepository(AsyncCRUDRepository[MessageAttachment]):
    def __init__(self, session):
        super().__init__(session, MessageAttachment)

    async def get_by_message_id(self, message_id: str) -> list[MessageAttachment]:
        query = select(MessageAttachment).where(MessageAttachment.message_id == message_id)
        result = await self._session.execute(query)
        return list(result.scalars().all())
