from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.skill_credentials import SkillCredential
from server.repositories.base import AsyncCRUDRepository
from server.services.crypto_service import CryptoService


class SkillCredentialRepository(AsyncCRUDRepository[SkillCredential]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, SkillCredential)

    async def get_by_skill(
        self, skill_name: str, tenant_id: UUID, user_id: UUID | None, scope: str = "user"
    ) -> SkillCredential | None:
        stmt = select(SkillCredential).where(
            SkillCredential.tenant_id == tenant_id,
            SkillCredential.skill_name == skill_name,
            SkillCredential.scope == scope,
        )
        if scope == "user":
            stmt = stmt.where(SkillCredential.user_id == user_id)
        else:
            stmt = stmt.where(SkillCredential.user_id.is_(None))

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_for_tenant_user(self, tenant_id: UUID, user_id: UUID) -> list[SkillCredential]:
        """Get both org-level AND user-level skills for a tenant/user."""
        stmt = select(SkillCredential).where(
            SkillCredential.tenant_id == tenant_id,
            or_(
                SkillCredential.scope == "org",
                and_(
                    SkillCredential.scope == "user",
                    SkillCredential.user_id == user_id,
                ),
            ),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_org_skills(self, tenant_id: UUID) -> list[SkillCredential]:
        """Get only org-level skills for a tenant."""
        stmt = select(SkillCredential).where(
            SkillCredential.tenant_id == tenant_id,
            SkillCredential.scope == "org",
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_decrypted_credentials(self, credential: SkillCredential) -> dict | None:
        if not credential.credentials_encrypted:
            return None
        return await CryptoService.decrypt_config(credential.credentials_encrypted, self._session)

    async def upsert(
        self,
        skill_name: str,
        credentials: dict,
        tenant_id: UUID,
        user_id: UUID | None,
        scope: str = "user",
        created_by: UUID | None = None,
    ) -> SkillCredential:
        encrypted = await CryptoService.encrypt_config(credentials, self._session)
        existing = await self.get_by_skill(skill_name, tenant_id, user_id, scope)

        if existing:
            existing.credentials_encrypted = encrypted
        else:
            existing = SkillCredential(
                tenant_id=tenant_id,
                user_id=user_id if scope == "user" else None,
                skill_name=skill_name,
                scope=scope,
                credentials_encrypted=encrypted,
                created_by=created_by,
            )
            self._session.add(existing)

        await self._session.commit()
        await self._session.refresh(existing)
        return existing

    async def delete_by_skill(
        self, skill_name: str, tenant_id: UUID, user_id: UUID | None, scope: str = "user"
    ) -> bool:
        existing = await self.get_by_skill(skill_name, tenant_id, user_id, scope)
        if existing:
            await self._session.delete(existing)
            await self._session.commit()
            return True
        return False

    async def share_to_org(self, skill_name: str, tenant_id: UUID, user_id: UUID) -> SkillCredential | None:
        """Copy user's credentials to org scope (share with team)."""
        user_cred = await self.get_by_skill(skill_name, tenant_id, user_id, scope="user")
        if not user_cred or not user_cred.credentials_encrypted:
            return None

        decrypted = await self.get_decrypted_credentials(user_cred)
        if not decrypted:
            return None

        return await self.upsert(
            skill_name=skill_name,
            credentials=decrypted,
            tenant_id=tenant_id,
            user_id=None,
            scope="org",
            created_by=user_id,
        )

    async def get_created_by_map(self, tenant_id: UUID, user_id: UUID) -> dict[str, dict[str, UUID | None]]:
        """Get a map of skill_name -> {scope -> created_by} for all credentials visible to user."""
        credentials = await self.get_all_for_tenant_user(tenant_id, user_id)
        result: dict[str, dict[str, UUID | None]] = {}
        for cred in credentials:
            if cred.skill_name not in result:
                result[cred.skill_name] = {}
            # For user-scope: if created_by is NULL, the owner is whoever has user_id on the credential
            if cred.scope == "user" and cred.created_by is None:
                result[cred.skill_name][cred.scope] = cred.user_id
            else:
                result[cred.skill_name][cred.scope] = cred.created_by
        return result
