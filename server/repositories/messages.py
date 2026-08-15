from __future__ import annotations

from typing import Any

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import selectinload

from server.models.messages import Message
from server.repositories.base import AsyncCRUDRepository


class MessageRepository(AsyncCRUDRepository[Message]):
    def __init__(self, session):
        super().__init__(session, Message)

    async def list(self, *, filters: dict[str, Any] | None = None) -> list[Message]:
        """Override list to eagerly load attachments"""
        query = select(self._model).options(selectinload(Message.attachments))

        if filters:
            for key, value in filters.items():
                if hasattr(self._model, key):
                    query = query.where(getattr(self._model, key) == value)

        query = query.order_by(self._model.created_at, self._model.id)

        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_recent_messages(self, thread_id: str, limit: int = 5) -> list[Message]:
        query = select(Message).where(Message.thread_id == thread_id).order_by(desc(Message.created_at)).limit(limit)

        result = await self._session.execute(query)
        messages = list(result.scalars().all())

        return list(reversed(messages))

    async def delete_by_thread_id(self, thread_id: str) -> bool:
        """Delete all messages for a specific thread_id (notebook_id)"""
        result = await self._session.execute(delete(Message).where(Message.thread_id == thread_id))
        await self._session.commit()
        affected = getattr(result, "rowcount", None) or 0
        return affected > 0
