from __future__ import annotations

from typing import Any

from sqlalchemy import select

from server.models.llm_connections import LLMConnection
from server.repositories.base import AsyncCRUDRepository
from server.services.crypto_service import CryptoService


class LLMConnectionRepository(AsyncCRUDRepository[LLMConnection]):
    def __init__(self, session):
        super().__init__(session, LLMConnection)
        self._session = session

    async def create(self, data: dict[str, Any]) -> LLMConnection:  # type: ignore[override]
        cfg = data.pop("config_dict", None)
        if isinstance(cfg, dict):
            data["config"] = await CryptoService.encrypt_config(cfg, self._session)
        return await super().create(data)

    async def update(self, pk: Any, data: dict[str, Any]) -> LLMConnection | None:  # type: ignore[override]
        cfg = data.pop("config_dict", None)
        if isinstance(cfg, dict):
            data["config"] = await CryptoService.encrypt_config(cfg, self._session)
        return await super().update(pk, data)

    async def get(self, pk: Any) -> LLMConnection | None:  # type: ignore[override]
        rec = await super().get(pk)
        return rec

    async def get_by_type(self, provider_type: str) -> LLMConnection | None:
        """Get connection by provider type (tenant-filtered)"""
        query = select(LLMConnection).where(LLMConnection.type == provider_type)
        # Apply tenant filter
        query = self._apply_tenant_filter(query)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()
