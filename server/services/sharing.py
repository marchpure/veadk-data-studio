from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.dashboard import Dashboard, DashboardAsset
from server.models.sharing import SharingAuditEvent, SharingGrant, SharingSecret, SharingViewerSession
from server.services.viewer_session_service import ViewerSessionService
from server.utils.error_sanitizer import sanitize_error_payload

_SECRET_ALGORITHM = "pbkdf2_sha256:210000"


class SharingService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_dashboard_public_link(
        self,
        *,
        tenant_id: str | UUID,
        actor_id: str | UUID,
        asset_id: str | UUID,
        version_id: str | UUID,
        password: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SharingGrant:
        tenant_uuid = _coerce_uuid(tenant_id)
        actor_uuid = _coerce_uuid(actor_id)
        asset_uuid = _coerce_uuid(asset_id)
        version_uuid = _coerce_uuid(version_id)
        asset, version = await self._require_dashboard_version(
            tenant_id=tenant_uuid,
            asset_id=asset_uuid,
            version_id=version_uuid,
        )
        grant = SharingGrant(
            tenant_id=tenant_uuid,
            object_type="dashboard",
            object_id=asset.id,
            object_version_id=version.id,
            object_version_digest=version.content_hash or asset.etag or "",
            mode="immutable_version",
            channel="public_link",
            audience="link_holder",
            status="active",
            created_by=actor_uuid,
            metadata_json=sanitize_error_payload(metadata or {}),
        )
        self._session.add(grant)
        await self._session.flush()
        if password:
            self._session.add(
                self._build_secret(
                    tenant_id=tenant_uuid,
                    grant_id=grant.id,
                    actor_id=actor_uuid,
                    secret=password,
                )
            )
        self._session.add(
            self._audit_event(
                tenant_id=tenant_uuid,
                grant=grant,
                actor_id=str(actor_uuid),
                action="sharing.grant.create",
                outcome="active",
                details={"metadata": metadata or {}, "has_password": bool(password)},
            )
        )
        await self._session.commit()
        await self._session.refresh(grant)
        return grant

    async def verify_grant_secret(self, *, grant_id: str | UUID, secret: str) -> bool:
        grant_uuid = _coerce_uuid(grant_id)
        result = await self._session.execute(
            select(SharingSecret).where(
                SharingSecret.grant_id == grant_uuid,
                SharingSecret.secret_type == "password",
                SharingSecret.status == "active",
            )
        )
        saved = result.scalars().first()
        if saved is None:
            return False
        return hmac.compare_digest(saved.verifier_hash, _hash_secret(secret=secret, salt=saved.salt))

    async def issue_viewer_session(
        self,
        *,
        tenant_id: str | UUID,
        grant_id: str | UUID,
        viewer_user_id: str | UUID | None = None,
        principal: dict[str, Any] | None = None,
    ) -> tuple[str, SharingViewerSession]:
        tenant_uuid = _coerce_uuid(tenant_id)
        grant_uuid = _coerce_uuid(grant_id)
        grant = await self._require_active_grant(tenant_id=tenant_uuid, grant_id=grant_uuid)
        viewer_uuid = _coerce_uuid(viewer_user_id) if viewer_user_id is not None else None
        token = ViewerSessionService.generate_token(
            user_id=viewer_uuid or grant.created_by or tenant_uuid,
            tenant_id=tenant_uuid,
            grant_id=grant.id,
            asset_id=grant.object_id,
            version_id=grant.object_version_id,
        )
        payload = ViewerSessionService.verify(token)
        if payload is None:
            raise ValueError("viewer session token could not be verified")
        now = self._now()
        expires_at = datetime.fromtimestamp(int(payload["exp"]), UTC)
        viewer_session = SharingViewerSession(
            tenant_id=tenant_uuid,
            grant_id=grant.id,
            object_type=grant.object_type,
            object_id=grant.object_id,
            object_version_id=grant.object_version_id,
            token_id=str(payload["jti"]),
            token_digest=_digest_text(token),
            viewer_user_id=viewer_uuid,
            viewer_principal_json=sanitize_error_payload(principal or {}),
            issued_at=now,
            expires_at=expires_at,
        )
        self._session.add(viewer_session)
        await self._session.flush()
        self._session.add(
            self._audit_event(
                tenant_id=tenant_uuid,
                grant=grant,
                viewer_session_id=viewer_session.id,
                actor_id=str(viewer_uuid or "anonymous"),
                action="sharing.viewer_session.issue",
                outcome="issued",
                details={"principal": principal or {}},
            )
        )
        await self._session.commit()
        await self._session.refresh(viewer_session)
        return token, viewer_session

    async def require_viewer_session(
        self,
        *,
        token: str,
        grant_id: str | UUID,
        object_id: str | UUID,
        object_version_id: str | UUID | None = None,
    ) -> SharingViewerSession | None:
        payload = ViewerSessionService.verify(token)
        if payload is None:
            return None
        grant_uuid = _coerce_uuid(grant_id)
        object_uuid = _coerce_uuid(object_id)
        version_uuid = _coerce_uuid(object_version_id) if object_version_id is not None else None
        if payload.get("grant_id") != str(grant_uuid):
            return None
        if payload.get("asset_id") != str(object_uuid):
            return None
        if version_uuid is not None and payload.get("version_id") != str(version_uuid):
            return None
        result = await self._session.execute(
            select(SharingViewerSession, SharingGrant)
            .join(SharingGrant, SharingGrant.id == SharingViewerSession.grant_id)
            .where(
                SharingViewerSession.token_digest == _digest_text(token),
                SharingViewerSession.grant_id == grant_uuid,
                SharingViewerSession.object_id == object_uuid,
                SharingViewerSession.object_version_id == version_uuid,
                SharingViewerSession.revoked_at.is_(None),
                SharingViewerSession.expires_at > self._now(),
                SharingGrant.status == "active",
                SharingGrant.revoked_at.is_(None),
            )
        )
        row = result.first()
        return row[0] if row else None

    async def revoke_grant(
        self,
        *,
        tenant_id: str | UUID,
        grant_id: str | UUID,
        actor_id: str | UUID,
        reason: str,
    ) -> SharingGrant:
        tenant_uuid = _coerce_uuid(tenant_id)
        actor_uuid = _coerce_uuid(actor_id)
        grant = await self._require_active_grant(tenant_id=tenant_uuid, grant_id=_coerce_uuid(grant_id))
        now = self._now()
        grant.status = "revoked"
        grant.revoked_at = now
        grant.revoked_by = actor_uuid
        grant.revocation_reason = reason
        result = await self._session.execute(
            select(SharingViewerSession).where(
                SharingViewerSession.grant_id == grant.id,
                SharingViewerSession.revoked_at.is_(None),
            )
        )
        for viewer_session in result.scalars():
            viewer_session.revoked_at = now
        self._session.add(
            self._audit_event(
                tenant_id=tenant_uuid,
                grant=grant,
                actor_id=str(actor_uuid),
                action="sharing.grant.revoke",
                outcome="revoked",
                details={"reason": reason},
            )
        )
        await self._session.commit()
        await self._session.refresh(grant)
        return grant

    async def _require_dashboard_version(
        self,
        *,
        tenant_id: UUID,
        asset_id: UUID,
        version_id: UUID,
    ) -> tuple[DashboardAsset, Dashboard]:
        result = await self._session.execute(
            select(DashboardAsset, Dashboard)
            .join(Dashboard, Dashboard.asset_id == DashboardAsset.id)
            .where(
                DashboardAsset.tenant_id == tenant_id,
                DashboardAsset.id == asset_id,
                Dashboard.tenant_id == tenant_id,
                Dashboard.id == version_id,
            )
        )
        row = result.first()
        if row is None:
            raise ValueError("dashboard asset version not found")
        asset, version = row
        if version.status != "published" or not version.is_published_immutable:
            raise ValueError("canonical sharing requires an immutable published dashboard version")
        return asset, version

    async def _require_active_grant(self, *, tenant_id: UUID, grant_id: UUID) -> SharingGrant:
        result = await self._session.execute(
            select(SharingGrant).where(
                SharingGrant.tenant_id == tenant_id,
                SharingGrant.id == grant_id,
                SharingGrant.status == "active",
                SharingGrant.revoked_at.is_(None),
            )
        )
        grant = result.scalars().first()
        if grant is None:
            raise ValueError("active sharing grant not found")
        return grant

    def _build_secret(self, *, tenant_id: UUID, grant_id: UUID, actor_id: UUID, secret: str) -> SharingSecret:
        salt = secrets.token_urlsafe(32)
        return SharingSecret(
            tenant_id=tenant_id,
            grant_id=grant_id,
            secret_type="password",
            algorithm=_SECRET_ALGORITHM,
            salt=salt,
            verifier_hash=_hash_secret(secret=secret, salt=salt),
            status="active",
            created_by=actor_id,
        )

    def _audit_event(
        self,
        *,
        tenant_id: UUID,
        grant: SharingGrant,
        actor_id: str,
        action: str,
        outcome: str,
        details: dict[str, Any],
        viewer_session_id: UUID | None = None,
    ) -> SharingAuditEvent:
        return SharingAuditEvent(
            tenant_id=tenant_id,
            grant_id=grant.id,
            viewer_session_id=viewer_session_id,
            object_type=grant.object_type,
            object_id=grant.object_id,
            object_version_id=grant.object_version_id,
            actor_type="human",
            actor_id=actor_id,
            action=action,
            outcome=outcome,
            details_json=sanitize_error_payload(details),
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)


def _coerce_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _hash_secret(*, secret: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(), 210000)
    return "sha256:" + digest.hex()


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()
