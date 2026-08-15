from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.models.tenant_member import TenantRole
from server.repositories.tenant_invitation import TenantInvitationRepository
from server.schemas.standard_response import success_response
from server.schemas.tenant import (
    AcceptInvitationRequest,
    InvitationCreate,
    InvitationListResponse,
    InvitationRead,
    MemberListResponse,
    MemberRead,
    MemberStatsListResponse,
    MemberStatsRead,
    UpdateMemberRoleRequest,
)
from server.services.tenant_service import TenantService
from server.utils.custom_logger import get_logger
from server.utils.deployment import is_feature_enabled

logger = get_logger(__name__)

router = APIRouter()


def _check_team_enabled():
    if not is_feature_enabled("team_sharing_enabled"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team features are not available in this deployment mode",
        )


# ==================== Member Management ====================


@router.get("/tenants/{tenant_id}/members")
async def list_members(
    tenant_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.TENANT_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """List all active members of a tenant."""
    _check_team_enabled()
    try:
        # Verify user has access to this tenant
        if auth.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this tenant",
            )

        members = await TenantService.list_members_with_users(tenant_id, session)

        # Convert to response schema
        member_reads = [MemberRead.model_validate(member) for member in members]
        response = MemberListResponse(items=member_reads, total=len(member_reads))

        return success_response(
            data=response.model_dump(),
            message=f"Retrieved {len(member_reads)} member(s)",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing members for tenant {tenant_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while listing members",
        )


@router.get("/tenants/{tenant_id}/stats/members")
async def list_member_stats(
    tenant_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.TENANT_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """Aggregate per-member stats (notebooks, dashboards, datasources) for a tenant."""
    _check_team_enabled()
    try:
        if auth.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this tenant",
            )

        if auth.role not in (TenantRole.OWNER, TenantRole.ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only owners and admins can view team stats",
            )

        stats = await TenantService.get_member_stats(tenant_id, session)
        items = [MemberStatsRead.model_validate(s) for s in stats["members"]]
        response = MemberStatsListResponse(items=items, total=len(items), slack=stats["slack"])

        return success_response(
            data=response.model_dump(),
            message=f"Retrieved stats for {len(items)} member(s)",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing member stats for tenant {tenant_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while listing member stats",
        )


@router.put("/tenants/{tenant_id}/members/{member_id}/role")
async def update_member_role(
    tenant_id: UUID,
    member_id: UUID,
    payload: UpdateMemberRoleRequest,
    auth: AuthContext = Depends(require_scope(Scope.TENANT_MANAGE_ROLES)),
    session: AsyncSession = Depends(get_async_session),
):
    """Update a member's role (owner and admin can manage roles with restrictions)."""
    _check_team_enabled()
    try:
        # Verify user has access to this tenant
        if auth.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this tenant",
            )

        updated_member = await TenantService.update_member_role(
            member_id=member_id,
            new_role=payload.role,
            tenant_id=tenant_id,
            current_user_id=auth.user.id,
            current_user_role=auth.role,
            session=session,
        )

        member_read = MemberRead.model_validate(updated_member)

        return success_response(
            data=member_read.model_dump(),
            message=f"Member role updated to {payload.role}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating member role: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating member role",
        )


@router.delete("/tenants/{tenant_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    tenant_id: UUID,
    member_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.TENANT_REMOVE_MEMBER)),
    session: AsyncSession = Depends(get_async_session),
):
    """Remove a member from a tenant."""
    _check_team_enabled()
    try:
        # Verify user has access to this tenant
        if auth.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this tenant",
            )

        await TenantService.remove_member(
            member_id=member_id,
            tenant_id=tenant_id,
            current_user_id=auth.user.id,
            current_user_role=auth.role,
            session=session,
        )

        return None  # 204 No Content
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing member: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while removing member",
        )


# ==================== Invitation Management ====================


@router.get("/tenants/{tenant_id}/invitations")
async def list_invitations(
    tenant_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.TENANT_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """List pending invitations for a tenant."""
    _check_team_enabled()
    try:
        # Verify user has access to this tenant
        if auth.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this tenant",
            )

        invitation_repo = TenantInvitationRepository(session)
        invitations = await invitation_repo.list_pending_by_tenant(tenant_id)

        # Convert to response schema
        invitation_reads = [InvitationRead.model_validate(inv) for inv in invitations]
        response = InvitationListResponse(items=invitation_reads, total=len(invitation_reads))

        return success_response(
            data=response.model_dump(),
            message=f"Retrieved {len(invitation_reads)} invitation(s)",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing invitations for tenant {tenant_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while listing invitations",
        )


@router.post("/tenants/{tenant_id}/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    tenant_id: UUID,
    payload: InvitationCreate,
    request: Request,
    auth: AuthContext = Depends(require_scope(Scope.TENANT_INVITE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Send an invitation to join a tenant."""
    _check_team_enabled()
    try:
        # Verify user has access to this tenant
        if auth.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this tenant",
            )

        # Get base URL from request origin header or construct from request
        origin = request.headers.get("origin")
        if not origin:
            scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
            host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
            origin = f"{scheme}://{host}" if host else None

        invitation, invitation_link, email_sent = await TenantService.send_invitation(
            tenant_id=tenant_id,
            email=payload.email,
            role=payload.role,
            invited_by_id=auth.user.id,
            session=session,
            message=payload.message,
            base_url=origin,
        )

        invitation_read = InvitationRead.model_validate(invitation)
        invitation_read.invitation_link = invitation_link
        invitation_read.email_sent = email_sent

        message = (
            f"Invitation sent to {payload.email}"
            if email_sent
            else f"Invitation created for {payload.email}. Email is not configured — share the link manually."
        )
        return success_response(
            data=invitation_read.model_dump(),
            message=message,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating invitation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating invitation",
        )


@router.post("/invitations/{invitation_id}/resend")
async def resend_invitation(
    invitation_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope(Scope.TENANT_INVITE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Resend an invitation email."""
    _check_team_enabled()
    try:
        # Get base URL from request origin header or construct from request
        origin = request.headers.get("origin")
        if not origin:
            scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
            host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
            origin = f"{scheme}://{host}" if host else None

        invitation, invitation_link, email_sent = await TenantService.resend_invitation(
            invitation_id, session, base_url=origin
        )

        # Verify user has access to this tenant
        if auth.tenant_id != invitation.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this tenant",
            )

        invitation_read = InvitationRead.model_validate(invitation)
        invitation_read.invitation_link = invitation_link
        invitation_read.email_sent = email_sent

        message = (
            f"Invitation resent to {invitation.email}"
            if email_sent
            else f"New link generated for {invitation.email}. Email is not configured — share the link manually."
        )
        return success_response(
            data=invitation_read.model_dump(),
            message=message,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resending invitation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resending invitation",
        )


@router.post("/invitations/{invitation_id}/link")
async def get_invitation_link(
    invitation_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope(Scope.TENANT_INVITE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Regenerate and return an invitation link without sending email."""
    _check_team_enabled()
    try:
        origin = request.headers.get("origin")
        if not origin:
            scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
            host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
            origin = f"{scheme}://{host}" if host else None

        invitation, invitation_link, email_sent = await TenantService.get_invitation_link(
            invitation_id, session, base_url=origin
        )

        if auth.tenant_id != invitation.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this tenant",
            )

        invitation_read = InvitationRead.model_validate(invitation)
        invitation_read.invitation_link = invitation_link
        invitation_read.email_sent = email_sent

        return success_response(
            data=invitation_read.model_dump(),
            message="Invitation link generated",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating invitation link: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating invitation link",
        )


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_invitation(
    invitation_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.TENANT_INVITE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Cancel a pending invitation."""
    _check_team_enabled()
    try:
        invitation_repo = TenantInvitationRepository(session)
        invitation = await invitation_repo.get(invitation_id)

        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found",
            )

        # Verify user has access to this tenant
        if auth.tenant_id != invitation.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this tenant",
            )

        await TenantService.revoke_invitation(invitation_id, session)

        return None  # 204 No Content
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error canceling invitation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while canceling invitation",
        )


@router.get("/invitations/verify")
async def verify_invitation(
    token: str,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Verify an invitation token and return basic info (public endpoint - no auth required).
    This allows checking if invitation is valid and if user needs to login or register.
    """
    _check_team_enabled()
    try:
        result = await TenantService.verify_invitation_token(token, session)

        return success_response(
            data=result,
            message="Invitation verified successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying invitation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while verifying invitation",
        )


@router.post("/invitations/accept")
async def accept_invitation(
    payload: AcceptInvitationRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Accept an invitation (public endpoint - no auth required).

    Note: User must be logged in for their user ID to be resolved.
    """
    _check_team_enabled()
    try:
        result = await TenantService.accept_invitation(payload.token, session)

        return success_response(
            data=result,
            message="Invitation accepted successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting invitation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while accepting invitation",
        )
