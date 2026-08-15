from __future__ import annotations

from server.models.files import File
from server.repositories.base import AsyncCRUDRepository


class FileRepository(AsyncCRUDRepository[File]):
    def __init__(self, session):
        super().__init__(session, File)
