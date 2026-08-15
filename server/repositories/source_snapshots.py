from __future__ import annotations

from server.models.source_snapshots import SourceSnapshot
from server.repositories.base import AsyncCRUDRepository


class SourceSnapshotRepository(AsyncCRUDRepository[SourceSnapshot]):
    def __init__(self, session):
        super().__init__(session, SourceSnapshot)
