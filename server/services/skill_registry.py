"""Skill Registry - Manages skill credentials and loads skill documentation."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.repositories.skill_credentials import SkillCredentialRepository
from server.services.skill_discovery import SkillDiscovery
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


class SkillRegistry:
    @staticmethod
    def get_skill_docs(skill_name: str) -> str | None:
        """Get skill documentation from discovered config."""
        config = SkillDiscovery.get_skill_config(skill_name)
        return config.docs if config else None

    @staticmethod
    async def get_enabled_skills(tenant_id: UUID, user_id: UUID, session: AsyncSession) -> dict[str, dict[str, Any]]:
        """Get all skills (org + user) with credentials configured for a tenant/user.

        Returns dict keyed by "{skill_name}:{scope}" to allow both org and user
        credentials for the same skill.
        """
        repo = SkillCredentialRepository(session)
        credentials = await repo.get_all_for_tenant_user(tenant_id, user_id)

        enabled: dict[str, dict[str, Any]] = {}
        for cred in credentials:
            try:
                decrypted = await repo.get_decrypted_credentials(cred)
                if decrypted:
                    # Key includes scope to allow both org + user for same skill
                    key = f"{cred.skill_name}:{cred.scope}"
                    enabled[key] = {
                        "credentials": decrypted,
                        "docs": SkillRegistry.get_skill_docs(cred.skill_name),
                        "scope": cred.scope,
                        "skill_name": cred.skill_name,
                    }
            except Exception as e:
                logger.error(f"Error decrypting credentials for {cred.skill_name}: {e}")

        return enabled

    @staticmethod
    async def get_org_enabled_skills(tenant_id: UUID, session: AsyncSession) -> dict[str, dict[str, Any]]:
        """Get org-scoped skills with credentials configured for a tenant (no user required)."""
        repo = SkillCredentialRepository(session)
        credentials = await repo.get_org_skills(tenant_id)

        enabled: dict[str, dict[str, Any]] = {}
        for cred in credentials:
            try:
                decrypted = await repo.get_decrypted_credentials(cred)
                if decrypted:
                    key = f"{cred.skill_name}:{cred.scope}"
                    enabled[key] = {
                        "credentials": decrypted,
                        "docs": SkillRegistry.get_skill_docs(cred.skill_name),
                        "scope": cred.scope,
                        "skill_name": cred.skill_name,
                    }
            except Exception as e:
                logger.error(f"Error decrypting credentials for {cred.skill_name}: {e}")

        return enabled

    @staticmethod
    async def get_skill_credentials(
        skill_name: str, tenant_id: UUID, user_id: UUID, session: AsyncSession, scope: str = "user"
    ) -> dict | None:
        """Get decrypted credentials for a specific skill and scope."""
        repo = SkillCredentialRepository(session)
        user_id_for_query = user_id if scope == "user" else None
        cred = await repo.get_by_skill(skill_name, tenant_id, user_id_for_query, scope)
        if cred:
            return await repo.get_decrypted_credentials(cred)
        return None
