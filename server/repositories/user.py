from __future__ import annotations

from sqlalchemy import select

from server.models.user import User
from server.repositories.base import AsyncCRUDRepository


class UserRepository(AsyncCRUDRepository[User]):
    def __init__(self, session):
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(self._model).where(self._model.email == email))
        return result.scalar_one_or_none()

    async def get_by_google_id(self, google_id: str) -> User | None:
        result = await self._session.execute(select(self._model).where(self._model.google_id == google_id))
        return result.scalar_one_or_none()
