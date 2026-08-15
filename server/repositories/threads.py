from __future__ import annotations

from server.models.threads import Thread
from server.repositories.base import AsyncCRUDRepository


class ThreadRepository(AsyncCRUDRepository[Thread]):
    def __init__(self, session):
        super().__init__(session, Thread)
