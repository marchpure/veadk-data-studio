from __future__ import annotations

from server.models.source_resources import SourceResource
from server.repositories.base import AsyncCRUDRepository


class SourceResourceRepository(AsyncCRUDRepository[SourceResource]):
    def __init__(self, session):
        super().__init__(session, SourceResource)
