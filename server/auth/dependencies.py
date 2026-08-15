"""
FastAPI dependencies for role-based access control (RBAC).

This module provides reusable dependencies for checking user permissions
based on their role in a tenant.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.config import current_verified_user
from server.auth.scopes import Scope, get_scopes_for_role, has_scope
from server.auth.tenant_context import set_tenant_id
from server.db.session import get_async_session
from server.models.tenant import Tenant
from server.models.tenant_member import TenantMember, TenantRole
from server.models.user import User
from server.services.posthog_service import PostHogService
from server.utils.config_loader import is_self_hosted
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

DEFAULT_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


class AuthContext:
    """
    Container for authenticated user context with role and tenant info.

    This provides all the authorization context needed by route handlers:
    - user: The authenticated User object
    - tenant_id: The active tenant UUID
    - role: The user's role in the tenant (OWNER, ADMIN, MEMBER)
    - scopes: List of permission scopes the user has
    """

    def __init__(self, user: User, tenant_id: UUID, role: TenantRole, scopes: list[str]):
        self.user = user
        self.tenant_id = tenant_id
        self.role = role
        self.scopes = scopes

    def has_scope(self, scope: Scope | str) -> bool:
        """Check if user has a specific scope."""
        return has_scope(self.scopes, scope)

    @property
    def user_id(self) -> UUID:
        """Convenience property for user ID."""
        return self.user.id

    @property
    def is_owner(self) -> bool:
        """Check if user is the tenant owner."""
        return self.role == TenantRole.OWNER

    @property
    def is_admin(self) -> bool:
        """Check if user is an admin (or owner)."""
        return self.role in (TenantRole.OWNER, TenantRole.ADMIN)

    @property
    def is_viewer(self) -> bool:
        """Check if user is a viewer."""
        return self.role == TenantRole.VIEWER


async def _get_auth_context_local(
    session: AsyncSession,
    x_tenant_id: str | None,
    x_local_user_id: str | None = None,
) -> AuthContext:
    """
    Auth context for local mode. Uses tenant_id from header to identify user session.
    The client stores tenant_id in localStorage after onboarding and sends it in x-tenant-id header.
    """
    if not x_tenant_id:
        result = await session.execute(select(Tenant).where(Tenant.slug == "community"))
        tenant = result.scalar_one_or_none()
        if not tenant:
            fallback = await session.execute(
                select(Tenant)
                .where(Tenant.is_personal.is_(True), Tenant.owner_id != DEFAULT_USER_ID)
                .order_by(Tenant.created_at.desc())
                .limit(1)
            )
            tenant = fallback.scalar_one_or_none()
        if not tenant:
            fallback = await session.execute(select(Tenant).order_by(Tenant.created_at.asc()).limit(1))
            tenant = fallback.scalar_one_or_none()
        if tenant:
            x_tenant_id = str(tenant.id)
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No tenant specified. Please login first.",
            )

    try:
        tenant_uuid = UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant ID format",
        )

    # Get tenant by ID
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_uuid))
    tenant = result.scalar_one_or_none()

    if not tenant:
        fallback = await session.execute(
            select(Tenant)
            .where(Tenant.is_personal.is_(True), Tenant.owner_id != DEFAULT_USER_ID)
            .order_by(Tenant.created_at.desc())
            .limit(1)
        )
        tenant = fallback.scalar_one_or_none()
        if not tenant:
            fallback = await session.execute(select(Tenant).order_by(Tenant.created_at.asc()).limit(1))
            tenant = fallback.scalar_one_or_none()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid tenant. Please login again.",
            )
        logger.warning(f"Tenant {tenant_uuid} not found, falling back to {tenant.id}")

    role = TenantRole.OWNER
    if x_local_user_id and os.getenv("BYAAN_LOCAL_AUTH_IMPERSONATION_ENABLED", "").lower() in {"1", "true", "yes"}:
        try:
            local_user_uuid = UUID(x_local_user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid local user ID format",
            )
        user_result = await session.execute(select(User).where(User.id == local_user_uuid))
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Local impersonation user not found.",
            )
        if tenant.owner_id == user.id:
            role = TenantRole.OWNER
        else:
            member_result = await session.execute(
                select(TenantMember).where(TenantMember.tenant_id == tenant.id, TenantMember.user_id == user.id)
            )
            membership = member_result.scalar_one_or_none()
            if not membership:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Local impersonation user is not a member of this tenant.",
                )
            role = TenantRole(membership.role)
    else:
        # Get owner (user) from tenant
        user_result = await session.execute(select(User).where(User.id == tenant.owner_id))
        user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tenant owner not found.",
        )

    # Set tenant context for repositories
    set_tenant_id(tenant.id)

    # Set PostHog user context
    PostHogService.set_current_user_id(str(user.id))
    PostHogService.set_current_user_email(user.email)

    scopes = get_scopes_for_role(role)

    return AuthContext(user, tenant.id, role, scopes)


async def _get_auth_context_hosted(
    user: User,
    session: AsyncSession,
    x_tenant_id: str | None,
) -> AuthContext:
    """
    Auth context for hosted mode. Requires authenticated user.
    """
    # Resolve tenant ID
    if x_tenant_id:
        try:
            tenant_uuid = UUID(x_tenant_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tenant ID format",
            )
    else:
        # Default to personal tenant
        result = await session.execute(
            select(Tenant.id).where(Tenant.owner_id == user.id, Tenant.is_personal == True)  # noqa: E712
        )
        tenant_uuid = result.scalar_one_or_none()

        # If no personal tenant, check if user is a member of any tenant
        if not tenant_uuid:
            member_result = await session.execute(
                select(TenantMember.tenant_id).where(TenantMember.user_id == user.id).limit(1)
            )
            tenant_uuid = member_result.scalar_one_or_none()

        if not tenant_uuid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No workspace found. Please contact your administrator.",
            )

    # Set tenant context for repositories
    set_tenant_id(tenant_uuid)

    # Check if user is owner of the tenant
    owner_result = await session.execute(select(Tenant).where(Tenant.id == tenant_uuid, Tenant.owner_id == user.id))
    if owner_result.scalar_one_or_none():
        role = TenantRole.OWNER
    else:
        # Check if user is a member of the tenant
        member_result = await session.execute(
            select(TenantMember).where(
                TenantMember.tenant_id == tenant_uuid,
                TenantMember.user_id == user.id,
            )
        )
        membership = member_result.scalar_one_or_none()
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this workspace.",
            )
        role = TenantRole(membership.role)

    scopes = get_scopes_for_role(role)

    # Propagate tenant_id to context so repositories can access it
    set_tenant_id(tenant_uuid)

    if is_self_hosted():
        PostHogService.set_current_user_id(str(user.id))
        PostHogService.set_current_user_email(user.email)

    return AuthContext(user, tenant_uuid, role, scopes)


async def get_auth_context(
    session: AsyncSession = Depends(get_async_session),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
    x_local_user_id: str | None = Header(None, alias="X-Local-User-ID"),
) -> AuthContext:
    """
    Core dependency: Returns AuthContext with user, tenant, role, and scopes.

    For self-hosted mode:
    1. Gets the authenticated user (from JWT)
    2. Resolves the active tenant (from X-Tenant-ID header or personal tenant)
    3. Determines the user's role in that tenant
    4. Loads the scopes for that role

    For desktop/community mode:
    1. Uses the default local user and tenant
    2. Grants OWNER role with all scopes

    Raises:
        HTTPException 400: If personal workspace not found
        HTTPException 403: If user has no access to the requested tenant
    """
    # Desktop/community mode: skip JWT auth, use default user/tenant
    if not is_self_hosted():
        return await _get_auth_context_local(session, x_tenant_id, x_local_user_id)

    # Self-hosted mode: this function should not be called directly
    # Use get_auth_context_hosted instead which has the user dependency
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal error: get_auth_context called in self-hosted mode without user",
    )


async def get_auth_context_hosted(
    user: User = Depends(current_verified_user),
    session: AsyncSession = Depends(get_async_session),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
) -> AuthContext:
    """
    Auth context dependency for hosted mode. Requires JWT authentication.
    """
    return await _get_auth_context_hosted(user, session, x_tenant_id)


# Create the appropriate dependency based on mode at import time
# Self-hosted mode = JWT auth, otherwise local auth (no JWT, always OWNER)
if is_self_hosted():
    _auth_context_dependency = get_auth_context_hosted
else:
    _auth_context_dependency = get_auth_context


def get_current_auth_context():
    """
    Returns the appropriate auth context dependency based on deployment mode.
    Use this as: auth: AuthContext = Depends(get_current_auth_context())
    """
    return _auth_context_dependency


def require_scope(required_scope: Scope | str) -> Callable:
    """
    Factory: Creates a dependency that requires a specific scope.

    Usage:
        @router.delete("/notebooks/{id}")
        async def delete_notebook(
            auth: AuthContext = Depends(require_scope(Scope.NOTEBOOK_DELETE)),
            session: AsyncSession = Depends(get_async_session),
        ):
            # Permission already verified!
            ...

    Args:
        required_scope: The scope that is required to access the endpoint

    Returns:
        A dependency function that checks the scope and returns AuthContext
    """

    async def _check_scope(
        auth: AuthContext = Depends(_auth_context_dependency),
    ) -> AuthContext:
        if not auth.has_scope(required_scope):
            scope_str = required_scope.value if isinstance(required_scope, Scope) else required_scope
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Required scope: {scope_str}",
            )
        return auth

    return _check_scope


def require_any_scope(*required_scopes: Scope | str) -> Callable:
    """
    Factory: Creates a dependency that requires ANY of the specified scopes.

    Useful for endpoints that can be accessed by users with different permissions.

    Usage:
        @router.delete("/notebooks/{id}")
        async def delete_notebook(
            auth: AuthContext = Depends(require_any_scope(
                Scope.NOTEBOOK_DELETE,
                Scope.NOTEBOOK_DELETE_OWN
            )),
        ):
            # User has at least one of the required scopes
            ...
    """

    async def _check_any_scope(
        auth: AuthContext = Depends(_auth_context_dependency),
    ) -> AuthContext:
        for scope in required_scopes:
            if auth.has_scope(scope):
                return auth

        scope_strs = [s.value if isinstance(s, Scope) else s for s in required_scopes]
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied. Required one of: {', '.join(scope_strs)}",
        )

    return _check_any_scope


# Convenience type aliases for common patterns
Auth = Annotated[AuthContext, Depends(_auth_context_dependency)]
"""Type alias for injecting AuthContext without specific scope check."""
