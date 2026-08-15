from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from server.models.tenant_invitation import InvitationStatus, TenantInvitation
from server.repositories.base import AsyncCRUDRepository


class TenantInvitationRepository(AsyncCRUDRepository[TenantInvitation]):
    def __init__(self, session):
        super().__init__(session, TenantInvitation)

    async def list_by_tenant(self, tenant_id: UUID) -> list[TenantInvitation]:
        """Get all invitations for a tenant."""
        result = await self._session.execute(
            select(self._model)
            .where(self._model.tenant_id == tenant_id)
            .options(selectinload(self._model.invited_by))
            .order_by(self._model.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_pending_by_tenant(self, tenant_id: UUID) -> list[TenantInvitation]:
        """Get pending invitations for a tenant."""
        result = await self._session.execute(
            select(self._model)
            .where(self._model.tenant_id == tenant_id)
            .where(self._model.status == InvitationStatus.PENDING.value)
            .where(self._model.expires_at > datetime.utcnow())
            .options(selectinload(self._model.invited_by))
            .order_by(self._model.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_email_and_tenant(self, email: str, tenant_id: UUID) -> TenantInvitation | None:
        """Check if an invitation already exists for this email in this tenant."""
        result = await self._session.execute(
            select(self._model)
            .where(self._model.email == email)
            .where(self._model.tenant_id == tenant_id)
            .where(self._model.status == InvitationStatus.PENDING.value)
        )
        return result.scalar_one_or_none()

    async def get_by_token_id(self, token_id: UUID) -> TenantInvitation | None:
        """Find invitation by verification token ID."""
        result = await self._session.execute(
            select(self._model)
            .where(self._model.token_id == token_id)
            .options(selectinload(self._model.tenant), selectinload(self._model.invited_by))
        )
        return result.scalar_one_or_none()

    async def update_status(
        self, invitation_id: UUID, status: str, accepted_at: datetime | None = None
    ) -> TenantInvitation | None:
        """Update invitation status."""
        invitation = await self.get(invitation_id)
        if invitation is None:
            return None

        invitation.status = status
        if accepted_at:
            invitation.accepted_at = accepted_at

        await self._session.commit()
        await self._session.refresh(invitation)
        return invitation

    async def expire_old_invitations(self, tenant_id: UUID | None = None) -> int:
        """Mark expired invitations as EXPIRED."""
        from sqlalchemy import update

        query = (
            update(self._model)
            .where(self._model.status == InvitationStatus.PENDING.value)
            .where(self._model.expires_at <= datetime.utcnow())
            .values(status=InvitationStatus.EXPIRED.value)
        )

        if tenant_id:
            query = query.where(self._model.tenant_id == tenant_id)

        result = await self._session.execute(query)
        await self._session.commit()
        return result.rowcount or 0
