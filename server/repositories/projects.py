from __future__ import annotations

from server.models.projects import Project
from server.repositories.base import AsyncCRUDRepository


class ProjectRepository(AsyncCRUDRepository[Project]):
    def __init__(self, session):
        super().__init__(session, Project)
