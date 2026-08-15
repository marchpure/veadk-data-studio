from __future__ import annotations

from sqlalchemy import select

from server.models.refresh_token import RefreshToken
from server.repositories.base import AsyncCRUDRepository


class RefreshTokenRepository(AsyncCRUDRepository[RefreshToken]):
    def __init__(self, session):
        super().__init__(session, RefreshToken)

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(select(self._model).where(self._model.token_hash == token_hash))
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: str) -> list[RefreshToken]:
        result = await self._session.execute(select(self._model).where(self._model.user_id == user_id))
        return list(result.scalars().all())
