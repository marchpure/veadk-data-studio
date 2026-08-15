"""Authentication utility functions for tenant management."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.tenant import Tenant
from server.models.tenant_member import TenantMember


async def get_user_personal_tenant(user_id: UUID, session: AsyncSession) -> UUID:
    """
    Get user's personal tenant ID.

    Args:
        user_id: The user's UUID
        session: Database session

    Returns:
        The personal tenant's UUID

    Raises:
        HTTPException: If personal tenant is not found (user may not be verified)
    """
    result = await session.execute(
        select(Tenant.id).where(Tenant.owner_id == user_id, Tenant.is_personal == True)  # noqa: E712
    )
    tenant_id = result.scalar_one_or_none()

    if not tenant_id:
        raise HTTPException(
            status_code=400,
            detail="Personal workspace not found. Please verify your email first.",
        )

    return tenant_id


async def get_active_tenant(
    user_id: UUID,
    session: AsyncSession,
    requested_tenant_id: str | None = None,
) -> UUID:
    """
    Get the active tenant for resource creation.

    If requested_tenant_id is provided, validates user has access to that tenant.
    Otherwise, falls back to user's personal tenant.

    Args:
        user_id: The user's UUID
        session: Database session
        requested_tenant_id: Optional tenant ID from X-Tenant-ID header

    Returns:
        The active tenant's UUID

    Raises:
        HTTPException: If tenant not found or user doesn't have access
    """
    # If no specific tenant requested, use personal tenant
    if not requested_tenant_id:
        return await get_user_personal_tenant(user_id, session)

    # Parse the requested tenant ID
    try:
        tenant_uuid = UUID(requested_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid tenant ID format.",
        )

    # Check if tenant exists
    result = await session.execute(select(Tenant.id).where(Tenant.id == tenant_uuid))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=404,
            detail="Tenant not found.",
        )

    # Check if user is a member of the tenant (or owner)
    # First check if user owns the tenant
    owner_result = await session.execute(select(Tenant.id).where(Tenant.id == tenant_uuid, Tenant.owner_id == user_id))
    is_owner = owner_result.scalar_one_or_none() is not None

    if not is_owner:
        # Check if user is a member
        member_result = await session.execute(
            select(TenantMember.id).where(
                TenantMember.tenant_id == tenant_uuid,
                TenantMember.user_id == user_id,
            )
        )
        is_member = member_result.scalar_one_or_none() is not None

        if not is_member:
            raise HTTPException(
                status_code=403,
                detail="You don't have access to this workspace.",
            )

    return tenant_uuid
