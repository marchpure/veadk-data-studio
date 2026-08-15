from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from server.models.connections import Connection
from server.repositories.base import AsyncCRUDRepository


class ConnectionRepository(AsyncCRUDRepository[Connection]):
    def __init__(self, session):
        super().__init__(session, Connection)

    async def update_schema_cache(self, connection_id: str, schema_data: dict[str, Any]) -> Connection | None:
        connection = await self.get(connection_id)
        if connection is None:
            return None

        connection.schema_cache = json.dumps(schema_data)
        connection.schema_updated_at = datetime.utcnow()

        await self._session.commit()
        await self._session.refresh(connection)
        return connection

    async def get_schema_cache(self, connection_id: str) -> dict[str, Any] | None:
        connection = await self.get(connection_id)
        if connection is None or connection.schema_cache is None:
            return None

        try:
            return json.loads(connection.schema_cache)
        except json.JSONDecodeError:
            return None

    async def clear_schema_cache(self, connection_id: str) -> bool:
        connection = await self.get(connection_id)
        if connection is None:
            return False

        connection.schema_cache = None
        connection.schema_updated_at = None

        await self._session.commit()
        return True

    async def is_schema_cache_valid(self, connection_id: str, max_age_hours: int = 24) -> bool:
        connection = await self.get(connection_id)
        if connection is None or connection.schema_cache is None or connection.schema_updated_at is None:
            return False

        age = datetime.utcnow() - connection.schema_updated_at
        return age.total_seconds() < (max_age_hours * 3600)
