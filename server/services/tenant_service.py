from __future__ import annotations

import asyncio
import hashlib
import secrets
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from server.db.session import AsyncSessionFactory
from server.models.dashboard import Dashboard
from server.models.datasets import Dataset
from server.models.mcp_session import MCPSession
from server.models.notebooks import Notebook
from server.models.queries import Query
from server.models.slack_conversation import SlackConversation
from server.models.slack_workspace import SlackWorkspace
from server.models.tenant_invitation import InvitationStatus, TenantInvitation
from server.models.tenant_member import TenantMember, TenantRole
from server.models.user import User
from server.models.verification_token import VerificationToken
from server.repositories.tenant import TenantRepository
from server.repositories.tenant_invitation import TenantInvitationRepository
from server.repositories.tenant_member import TenantMemberRepository
from server.services.email_service import EmailService, SMTPEmailService
from server.utils.config_loader import get_email_config, get_smtp_config
from server.utils.custom_logger import get_logger
from server.utils.seed_notebook import seed_demo_notebooks_for_user

logger = get_logger(__name__)


def _get_email_service() -> EmailService | SMTPEmailService | None:
    """
    Get email service based on configuration priority:
    1. SMTP (if configured) - for self-hosted deployments
    2. Resend API (if configured) - for deployments using Resend service
    3. None - if neither configured
    """
    smtp_config = get_smtp_config()
    if smtp_config:
        return SMTPEmailService(
            smtp_host=smtp_config["smtp_host"],
            smtp_port=smtp_config["smtp_port"],
            smtp_username=smtp_config["smtp_username"],
            smtp_password=smtp_config["smtp_password"],
            smtp_from_email=smtp_config["smtp_from_email"],
            smtp_from_name=smtp_config["smtp_from_name"],
            smtp_use_tls=smtp_config["smtp_use_tls"],
        )

    email_config = get_email_config()
    if email_config["api_key"]:
        return EmailService(api_key=email_config["api_key"], from_email=email_config["from_email"])

    return None


def generate_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


class TenantService:
    """Service for managing tenant invitations and members."""

    @staticmethod
    async def send_invitation(
        tenant_id: UUID,
        email: str,
        role: str,
        invited_by_id: UUID,
        session: AsyncSession,
        message: str | None = None,
        base_url: str | None = None,
    ) -> tuple[TenantInvitation, str, bool]:
        """
        Send an invitation to join a tenant.

        If no email service is configured (or email send fails), the invitation is still
        created and the link is returned so the admin can share it manually.

        Returns:
            Tuple of (invitation, invitation_link, email_sent).
            email_sent is False when SMTP/Resend is not configured or delivery failed.
        """
        # Validate role
        if role not in ["admin", "member", "viewer"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role. Can only invite as 'admin', 'member', or 'viewer'.",
            )

        # Get repositories
        tenant_repo = TenantRepository(session)
        invitation_repo = TenantInvitationRepository(session)
        member_repo = TenantMemberRepository(session)

        # Check tenant exists
        tenant = await tenant_repo.get(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )

        # Check if user is already a member
        result = await session.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            existing_membership = await member_repo.get_membership(str(existing_user.id), str(tenant_id))
            if existing_membership:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This user is already a member of the organization",
                )

        # Check if pending invitation already exists
        existing_invitation = await invitation_repo.get_by_email_and_tenant(email, tenant_id)
        if existing_invitation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This user already has a pending invitation",
            )

        # Generate token
        token = generate_token()
        token_hash_value = hash_token(token)

        # Create verification token
        verification_token = VerificationToken(
            user_id=invited_by_id,  # Associate with inviter for now
            token_hash=token_hash_value,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        session.add(verification_token)
        await session.flush()  # Get ID without committing

        # Create invitation
        invitation = TenantInvitation(
            tenant_id=tenant_id,
            email=email,
            role=role,
            invited_by_id=invited_by_id,
            token_id=verification_token.id,
            status=InvitationStatus.PENDING.value,
            plain_token=token,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        session.add(invitation)
        await session.commit()
        await session.refresh(invitation)

        # Load relationships
        await session.refresh(invitation, ["tenant", "invited_by"])

        config = get_email_config()
        frontend_url = base_url or config["frontend_url"]
        invitation_link = f"{frontend_url}/accept-invitation?token={token}"

        email_sent = False
        email_service = _get_email_service()
        if email_service:
            inviter_name = invitation.invited_by.full_name or invitation.invited_by.email
            try:
                result = await email_service.send_invitation_email(
                    to_email=email,
                    invitation_link=invitation_link,
                    tenant_name=tenant.name,
                    inviter_name=inviter_name,
                    role=role,
                )
                if result.get("success"):
                    email_sent = True
                    logger.info(f"Invitation email sent successfully to {email} for tenant {tenant.name}")
                else:
                    logger.warning(
                        f"Email send failed for {email}: {result.get('error', 'Unknown error')}. "
                        "Link must be shared manually."
                    )
            except Exception as e:
                logger.warning(
                    f"Email send raised for {email}: {str(e)}. Link must be shared manually.",
                    exc_info=True,
                )
        else:
            logger.info(f"No email service configured. Invitation created for {email}; admin must share link manually.")

        return invitation, invitation_link, email_sent

    @staticmethod
    async def verify_invitation_token(token: str, session: AsyncSession) -> dict:
        """
        Verify an invitation token and return basic info without accepting it.

        Args:
            token: The invitation token
            session: Database session

        Returns:
            Dict with invitation email, tenant name, and whether user exists

        Raises:
            HTTPException: If token is invalid or expired
        """
        token_hash_value = hash_token(token)

        # Find verification token
        result = await session.execute(
            select(VerificationToken).where(VerificationToken.token_hash == token_hash_value)
        )
        verification_token = result.scalar_one_or_none()

        if not verification_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid invitation link",
            )

        if verification_token.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation link has expired",
            )

        if verification_token.verified_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation link has already been used",
            )

        # Find invitation
        invitation_repo = TenantInvitationRepository(session)
        invitation = await invitation_repo.get_by_token_id(verification_token.id)

        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation not found",
            )

        if invitation.status != InvitationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invitation is {invitation.status}",
            )

        # Check if user exists
        result = await session.execute(select(User).where(User.email == invitation.email))
        user = result.scalar_one_or_none()

        # Load tenant info
        await session.refresh(invitation, ["tenant"])

        return {
            "email": invitation.email,
            "tenant_name": invitation.tenant.name,
            "tenant_id": str(invitation.tenant_id),
            "role": invitation.role,
            "user_exists": user is not None,
            "user_verified": user.is_verified if user else False,
        }

    @staticmethod
    async def accept_invitation(token: str, session: AsyncSession) -> dict:
        """
        Accept an invitation and create tenant membership.

        Args:
            token: The invitation token
            session: Database session

        Returns:
            Dict with success status and member info

        Raises:
            HTTPException: If token is invalid or expired
        """
        token_hash_value = hash_token(token)

        # Find verification token
        result = await session.execute(
            select(VerificationToken).where(VerificationToken.token_hash == token_hash_value)
        )
        verification_token = result.scalar_one_or_none()

        if not verification_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid invitation link",
            )

        if verification_token.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation link has expired",
            )

        # Find invitation up front so idempotent paths can return its tenant info.
        invitation_repo = TenantInvitationRepository(session)
        invitation = await invitation_repo.get_by_token_id(verification_token.id)

        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation not found",
            )

        # Idempotent path: invitation already accepted (e.g. auto-accepted during Google login).
        # If the matching user is already a member, return success instead of 400 so the client
        # can navigate into the workspace.
        member_repo = TenantMemberRepository(session)
        if verification_token.verified_at or invitation.status == InvitationStatus.ACCEPTED.value:
            user_result = await session.execute(select(User).where(User.email == invitation.email))
            existing_user = user_result.scalar_one_or_none()
            if existing_user:
                membership = await member_repo.get_membership(str(existing_user.id), str(invitation.tenant_id))
                if membership:
                    return {
                        "success": True,
                        "member_id": str(membership.id),
                        "tenant_id": str(membership.tenant_id),
                        "role": membership.role,
                        "already_accepted": True,
                    }
            # Token was used but no membership exists — treat as truly consumed.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation link has already been used",
            )

        if invitation.status != InvitationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invitation is {invitation.status}",
            )

        # Check if user exists
        result = await session.execute(select(User).where(User.email == invitation.email))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User account not found. Please register first.",
            )

        # Check if already a member (race condition protection) — return success idempotently.
        existing_membership = await member_repo.get_membership(str(user.id), str(invitation.tenant_id))
        if existing_membership:
            return {
                "success": True,
                "member_id": str(existing_membership.id),
                "tenant_id": str(existing_membership.tenant_id),
                "role": existing_membership.role,
                "already_accepted": True,
            }

        # Create tenant membership
        member = TenantMember(
            user_id=user.id,
            tenant_id=invitation.tenant_id,
            role=invitation.role,
            invited_at=invitation.created_at,
            joined_at=datetime.utcnow(),
        )
        session.add(member)

        # Mark invitation as accepted
        invitation.status = InvitationStatus.ACCEPTED.value
        invitation.accepted_at = datetime.utcnow()

        # Mark token as verified
        verification_token.verified_at = datetime.utcnow()

        await session.commit()
        await session.refresh(member)

        logger.info(f"User {user.email} accepted invitation to tenant {invitation.tenant_id}")

        # Seed demo notebooks in background for the accepting user
        tenant_id_copy = invitation.tenant_id
        accepting_user_id = user.id

        async def seed_in_background():
            try:
                async with AsyncSessionFactory() as seed_session:
                    await seed_demo_notebooks_for_user(seed_session, accepting_user_id, tenant_id_copy)
            except Exception as e:
                logger.error(f"Failed to seed demo notebooks for user {accepting_user_id}: {e}")

        asyncio.create_task(seed_in_background())

        return {
            "success": True,
            "member_id": str(member.id),
            "tenant_id": str(member.tenant_id),
            "role": member.role,
        }

    @staticmethod
    async def resend_invitation(
        invitation_id: UUID, session: AsyncSession, base_url: str | None = None
    ) -> tuple[TenantInvitation, str, bool]:
        """
        Regenerate the invitation token and resend the email.

        If no email service is configured (or send fails), the new link is still
        returned so the admin can share it manually.

        Returns:
            Tuple of (invitation, invitation_link, email_sent).
        """
        invitation_repo = TenantInvitationRepository(session)
        invitation = await invitation_repo.get(invitation_id)

        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found",
            )

        if invitation.status != InvitationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot resend invitation with status: {invitation.status}",
            )

        # Generate new token
        token = generate_token()
        token_hash_value = hash_token(token)

        # Update verification token
        result = await session.execute(select(VerificationToken).where(VerificationToken.id == invitation.token_id))
        verification_token = result.scalar_one_or_none()

        if verification_token:
            verification_token.token_hash = token_hash_value
            verification_token.expires_at = datetime.utcnow() + timedelta(days=7)
        else:
            # Create new verification token if missing
            verification_token = VerificationToken(
                user_id=invitation.invited_by_id,
                token_hash=token_hash_value,
                expires_at=datetime.utcnow() + timedelta(days=7),
            )
            session.add(verification_token)
            await session.flush()
            invitation.token_id = verification_token.id

        # Update invitation expiration and store plain token
        invitation.expires_at = datetime.utcnow() + timedelta(days=7)
        invitation.plain_token = token

        await session.commit()
        await session.refresh(invitation)

        # Load relationships
        await session.refresh(invitation, ["tenant", "invited_by"])

        config = get_email_config()
        frontend_url = base_url or config["frontend_url"]
        invitation_link = f"{frontend_url}/accept-invitation?token={token}"

        email_sent = False
        email_service = _get_email_service()
        if email_service:
            inviter_name = invitation.invited_by.full_name or invitation.invited_by.email
            try:
                result = await email_service.send_invitation_email(
                    to_email=invitation.email,
                    invitation_link=invitation_link,
                    tenant_name=invitation.tenant.name,
                    inviter_name=inviter_name,
                    role=invitation.role,
                )
                if result.get("success"):
                    email_sent = True
                    logger.info(f"Invitation email resent successfully to {invitation.email}")
                else:
                    logger.warning(
                        f"Resend failed for {invitation.email}: {result.get('error', 'Unknown error')}. "
                        "Link must be shared manually."
                    )
            except Exception as e:
                logger.warning(
                    f"Resend raised for {invitation.email}: {str(e)}. Link must be shared manually.",
                    exc_info=True,
                )
        else:
            logger.info(
                f"No email service configured. Token regenerated for {invitation.email}; "
                "admin must share link manually."
            )

        return invitation, invitation_link, email_sent

    @staticmethod
    async def get_invitation_link(
        invitation_id: UUID, session: AsyncSession, base_url: str | None = None
    ) -> tuple[TenantInvitation, str, bool]:
        """
        Return the existing invitation link if the token is still valid,
        otherwise regenerate the token, optionally send a new email, and return the new link.

        Returns:
            Tuple of (invitation, invitation_link, email_sent).
            email_sent is False when the existing token is still valid (no email sent),
            when no email service is configured, or when delivery failed.
        """
        invitation_repo = TenantInvitationRepository(session)
        invitation = await invitation_repo.get(invitation_id)

        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found",
            )

        if invitation.status != InvitationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot get link for invitation with status: {invitation.status}",
            )

        config = get_email_config()
        frontend_url = base_url or config["frontend_url"]

        if invitation.plain_token and invitation.expires_at > datetime.utcnow():
            invitation_link = f"{frontend_url}/accept-invitation?token={invitation.plain_token}"
            return invitation, invitation_link, False

        token = generate_token()
        token_hash_value = hash_token(token)

        result = await session.execute(select(VerificationToken).where(VerificationToken.id == invitation.token_id))
        verification_token = result.scalar_one_or_none()

        if verification_token:
            verification_token.token_hash = token_hash_value
            verification_token.expires_at = datetime.utcnow() + timedelta(days=7)
        else:
            verification_token = VerificationToken(
                user_id=invitation.invited_by_id,
                token_hash=token_hash_value,
                expires_at=datetime.utcnow() + timedelta(days=7),
            )
            session.add(verification_token)
            await session.flush()
            invitation.token_id = verification_token.id

        invitation.expires_at = datetime.utcnow() + timedelta(days=7)
        invitation.plain_token = token

        await session.commit()
        await session.refresh(invitation)
        await session.refresh(invitation, ["tenant", "invited_by"])

        invitation_link = f"{frontend_url}/accept-invitation?token={token}"

        email_sent = False
        email_service = _get_email_service()
        if email_service:
            inviter_name = invitation.invited_by.full_name or invitation.invited_by.email
            try:
                result = await email_service.send_invitation_email(
                    to_email=invitation.email,
                    invitation_link=invitation_link,
                    tenant_name=invitation.tenant.name,
                    inviter_name=inviter_name,
                    role=invitation.role,
                )
                if isinstance(result, dict) and result.get("success"):
                    email_sent = True
                logger.info(f"Regenerated token and resent invitation email to {invitation.email}")
            except Exception as e:
                logger.error(f"Failed to send email after token regeneration: {str(e)}")

        return invitation, invitation_link, email_sent

    @staticmethod
    async def revoke_invitation(invitation_id: UUID, session: AsyncSession) -> TenantInvitation:
        """
        Revoke a pending invitation.

        Args:
            invitation_id: The invitation ID
            session: Database session

        Returns:
            The updated invitation

        Raises:
            HTTPException: If invitation not found or not pending
        """
        invitation_repo = TenantInvitationRepository(session)
        invitation = await invitation_repo.get(invitation_id)

        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found",
            )

        if invitation.status != InvitationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot revoke invitation with status: {invitation.status}",
            )

        invitation.status = InvitationStatus.REVOKED.value
        await session.commit()
        await session.refresh(invitation)

        logger.info(f"Invitation {invitation_id} revoked")

        return invitation

    @staticmethod
    async def list_members_with_users(tenant_id: UUID, session: AsyncSession) -> list[TenantMember]:
        """
        List all members of a tenant with user details.

        Args:
            tenant_id: The tenant ID
            session: Database session

        Returns:
            List of tenant members with user relationships loaded
        """
        result = await session.execute(
            select(TenantMember)
            .where(TenantMember.tenant_id == tenant_id)
            .options(selectinload(TenantMember.user))
            .order_by(TenantMember.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_member_stats(tenant_id: UUID, session: AsyncSession) -> dict:
        """
        Aggregate per-member stats and tenant-level Slack stats.

        Returns a dict with:
        - members: list of per-member dicts (notebooks, dashboards, queries, datasources)
        - slack: tenant-level slack stats (notebooks, dashboards, queries)

        Dashboards are attributed to the creator of their parent notebook (members only).
        Slack notebooks have no Byaan creator, so shown only at tenant level.
        """
        members = await TenantService.list_members_with_users(tenant_id, session)

        mcp_notebook_subq = select(MCPSession.notebook_id).where(MCPSession.notebook_id.is_not(None))

        notebook_counts_result = await session.execute(
            select(Notebook.created_by, func.count(Notebook.id))
            .where(
                Notebook.tenant_id == tenant_id,
                Notebook.created_by.is_not(None),
                Notebook.id.notin_(mcp_notebook_subq),
            )
            .group_by(Notebook.created_by)
        )
        notebook_counts = {row[0]: row[1] for row in notebook_counts_result.all()}

        dashboard_counts_result = await session.execute(
            select(Notebook.created_by, func.count(func.distinct(Dashboard.notebook_id)))
            .join(Dashboard, Dashboard.notebook_id == Notebook.id)
            .where(
                Notebook.tenant_id == tenant_id,
                Notebook.created_by.is_not(None),
                Notebook.id.notin_(mcp_notebook_subq),
                Dashboard.version_num > 1,
            )
            .group_by(Notebook.created_by)
        )
        dashboard_counts = {row[0]: row[1] for row in dashboard_counts_result.all()}

        query_counts_result = await session.execute(
            select(Query.created_by, func.count(Query.id))
            .where(Query.tenant_id == tenant_id, Query.created_by.is_not(None))
            .group_by(Query.created_by)
        )
        query_counts = {row[0]: row[1] for row in query_counts_result.all()}

        connection_ds_result = await session.execute(
            select(Dataset.created_by, func.count(func.distinct(Dataset.connection_id)))
            .where(
                Dataset.tenant_id == tenant_id,
                Dataset.created_by.is_not(None),
                Dataset.type == "connection",
                Dataset.connection_id.is_not(None),
            )
            .group_by(Dataset.created_by)
        )
        file_ds_result = await session.execute(
            select(Dataset.created_by, func.count(Dataset.id))
            .where(
                Dataset.tenant_id == tenant_id,
                Dataset.created_by.is_not(None),
                Dataset.type == "file",
            )
            .group_by(Dataset.created_by)
        )
        datasource_counts: dict = {}
        for row in connection_ds_result.all():
            datasource_counts[row[0]] = datasource_counts.get(row[0], 0) + row[1]
        for row in file_ds_result.all():
            datasource_counts[row[0]] = datasource_counts.get(row[0], 0) + row[1]

        stats = []
        for member in members:
            uid = member.user_id
            stats.append(
                {
                    "user_id": uid,
                    "member_id": member.id,
                    "full_name": member.user.full_name if member.user else None,
                    "email": member.user.email if member.user else None,
                    "role": member.role,
                    "joined_at": member.joined_at or member.created_at,
                    "notebooks_count": notebook_counts.get(uid, 0),
                    "dashboards_count": dashboard_counts.get(uid, 0),
                    "queries_count": query_counts.get(uid, 0),
                    "datasources_count": datasource_counts.get(uid, 0),
                }
            )

        slack_notebook_subq = (
            select(SlackConversation.notebook_id)
            .join(SlackWorkspace, SlackWorkspace.id == SlackConversation.slack_workspace_id)
            .where(
                SlackWorkspace.tenant_id == tenant_id,
                SlackConversation.notebook_id.is_not(None),
            )
        )

        slack_notebooks_count = await session.scalar(
            select(func.count(Notebook.id)).where(
                Notebook.tenant_id == tenant_id,
                Notebook.id.in_(slack_notebook_subq),
            )
        )
        slack_dashboards_count = await session.scalar(
            select(func.count(func.distinct(Dashboard.notebook_id)))
            .join(Notebook, Notebook.id == Dashboard.notebook_id)
            .where(
                Notebook.tenant_id == tenant_id,
                Notebook.id.in_(slack_notebook_subq),
                Dashboard.version_num > 1,
            )
        )
        slack_queries_count = await session.scalar(
            select(func.count(Query.id)).where(
                Query.tenant_id == tenant_id,
                Query.notebook_id.in_(slack_notebook_subq),
            )
        )

        return {
            "members": stats,
            "slack": {
                "notebooks_count": slack_notebooks_count or 0,
                "dashboards_count": slack_dashboards_count or 0,
                "queries_count": slack_queries_count or 0,
            },
        }

    @staticmethod
    async def update_member_role(
        member_id: UUID,
        new_role: str,
        tenant_id: UUID,
        current_user_id: UUID,
        current_user_role: TenantRole,
        session: AsyncSession,
    ) -> TenantMember:
        """
        Update a member's role.

        Args:
            member_id: The member ID
            new_role: The new role (admin or member)
            tenant_id: The tenant ID (for verification)
            current_user_id: The ID of the user making the change
            current_user_role: The role of the user making the change
            session: Database session

        Returns:
            The updated member with user relationship loaded

        Raises:
            HTTPException: If member not found, role invalid, or permission denied
        """
        # Validate role
        if new_role not in [TenantRole.ADMIN.value, TenantRole.MEMBER.value, TenantRole.VIEWER.value]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role. Can only assign 'admin', 'member', or 'viewer'.",
            )

        member_repo = TenantMemberRepository(session)
        member = await member_repo.get(member_id)

        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found",
            )

        if member.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Member does not belong to this tenant",
            )

        # Owner's role cannot be changed by anyone
        if member.role == TenantRole.OWNER.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Owner's role cannot be changed",
            )

        # Admins cannot change their own role
        if current_user_role == TenantRole.ADMIN and member.user_id == current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admins cannot change their own role",
            )

        member.role = new_role
        await session.commit()
        await session.refresh(member)

        logger.info(f"Member {member_id} role updated to {new_role}")

        # Eagerly load the user relationship to avoid lazy-loading issues
        result = await session.execute(
            select(TenantMember).where(TenantMember.id == member_id).options(joinedload(TenantMember.user))
        )
        member_with_user = result.scalar_one()

        return member_with_user

    @staticmethod
    async def remove_member(
        member_id: UUID, tenant_id: UUID, current_user_id: UUID, current_user_role: TenantRole, session: AsyncSession
    ) -> None:
        """
        Remove a member from a tenant.

        Role-based restrictions:
        - Owner: Can remove admins and members (but not themselves)
        - Admin: Can remove other admins and members (but not themselves)

        Args:
            member_id: The member ID
            tenant_id: The tenant ID (for verification)
            current_user_id: The ID of the user performing the removal
            current_user_role: Role of the user performing the removal
            session: Database session

        Raises:
            HTTPException: If member not found or removal not allowed
        """
        member_repo = TenantMemberRepository(session)
        member = await member_repo.get(member_id)

        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found",
            )

        if member.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Member does not belong to this tenant",
            )

        member_role = TenantRole(member.role)

        # Rule 1: Owner cannot be removed by anyone
        if member_role == TenantRole.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Owner cannot be removed from the tenant",
            )

        # Rule 2: Users cannot remove themselves (including admins)
        if member.user_id == current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot remove yourself from the tenant",
            )

        # All checks passed, proceed with removal
        await member_repo.delete(member_id)
        logger.info(f"Member {member_id} removed from tenant {tenant_id}")
