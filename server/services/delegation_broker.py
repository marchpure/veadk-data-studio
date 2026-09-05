"""I4-A server-side delegation broker.

Opaque references are the only value crossing the W7/W5 boundary. Access
tokens are encrypted in the BFF database and are returned only after the
service-authenticated W5 resolve request passes every scope check.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext
from server.models.delegation import Delegation
from server.services.crypto_service import CryptoService
from server.services.runtime_secrets import RuntimeSecretError, get_runtime_secret

MAX_TTL_SECONDS = 300
DEFAULT_AUDIENCE = "dwv1-skill-agent"
OPAQUE_REF_PATTERN = r"^dlg_[A-Za-z0-9_-]{32,64}$"


class DelegationBrokerError(RuntimeError):
    def __init__(self, code: str, message: str = "delegation unavailable") -> None:
        super().__init__(message)
        self.code = code


def _ref_hash(ref: str) -> str:
    return hashlib.sha256(ref.encode("ascii")).hexdigest()


def _configured(value: str | None) -> str:
    return (value or "").strip()


def _ref_is_opaque(value: str) -> bool:
    return bool(re.fullmatch(OPAQUE_REF_PATTERN, value or ""))


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _service_credential() -> str:
    """Resolve the broker service credential through the runtime IAM/KMS chain."""
    try:
        value = get_runtime_secret(
            "broker_service_credential",
            env_name="I4A_BROKER_SERVICE_CREDENTIAL",
            required=True,
        )
    except RuntimeSecretError as exc:
        raise DelegationBrokerError("BLOCKED_CONFIG") from exc
    if not isinstance(value, str) or not value:
        raise DelegationBrokerError("BLOCKED_CONFIG")
    return value


def _constant_time_bearer(request: Request, credential: str) -> bool:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return False
    presented = header[7:].strip()
    return bool(presented) and hmac.compare_digest(presented, credential)


async def issue_from_auth(auth: AuthContext, session: AsyncSession) -> str:
    """Issue a delegation only from an externally verified identity subject."""
    subject = _configured(getattr(auth, "external_subject", None))
    access_token = _configured(getattr(auth, "access_token", None))
    verified_issuer = _configured(getattr(auth, "external_issuer", None))
    verified_audience = _configured(getattr(auth, "external_audience", None))
    verified_user_pool = _configured(getattr(auth, "external_user_pool", None))
    tenant_id = auth.tenant_id
    audience = _configured(os.getenv("I4A_DELEGATION_AUDIENCE")) or DEFAULT_AUDIENCE
    issuer = _configured(os.getenv("I4A_DELEGATION_ISSUER"))
    user_pool = _configured(os.getenv("I4A_DELEGATION_USER_POOL"))
    required_group = _configured(os.getenv("I4A_DELEGATION_GROUP_UID"))
    groups = list(getattr(auth, "external_groups", ()) or ())
    if not subject or not access_token or not verified_issuer or not verified_audience or not verified_user_pool:
        raise DelegationBrokerError("BLOCKED_AUTH")
    if not issuer or not user_pool or not required_group:
        raise DelegationBrokerError("BLOCKED_CONFIG")
    if (
        verified_issuer != issuer
        or verified_audience != audience
        or verified_user_pool != user_pool
        or required_group not in groups
    ):
        raise DelegationBrokerError("BLOCKED_AUTH")
    now = datetime.now(UTC)
    expires = now + timedelta(seconds=MAX_TTL_SECONDS)
    ref = f"dlg_{secrets.token_urlsafe(32)}"
    encrypted = await CryptoService.encrypt_config({"access_token": access_token}, session)
    session.add(
        Delegation(
            ref_hash=_ref_hash(ref),
            tenant_id=tenant_id,
            subject=subject,
            groups=groups,
            audience=audience,
            issuer=issuer,
            user_pool=user_pool,
            encrypted_access_token=encrypted,
            expires_at=expires,
            max_uses=1,
            uses=0,
        )
    )
    await session.flush()
    return ref


async def revoke(opaque_ref: str | None, tenant_id: UUID, session: AsyncSession) -> None:
    """Revoke a delegation without revealing whether the reference existed."""
    if not opaque_ref or not _ref_is_opaque(opaque_ref):
        return
    result = await session.execute(
        select(Delegation).where(
            Delegation.ref_hash == _ref_hash(opaque_ref),
            Delegation.tenant_id == tenant_id,
        )
    )
    record = result.scalar_one_or_none()
    if record is not None and record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        await session.flush()


async def resolve(
    request: Request,
    opaque_ref: str,
    body: dict[str, Any],
    session: AsyncSession,
) -> dict[str, Any]:
    """Resolve one bounded-use delegation for an authenticated W5 service."""
    if request.headers.get("origin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="internal endpoint")
    try:
        credential = await _service_credential()
    except DelegationBrokerError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="delegation unavailable")
    if not _constant_time_bearer(request, credential):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    if not _ref_is_opaque(opaque_ref):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="delegation unavailable")
    intended_audience = body.get("intended_audience")
    tenant_raw = body.get("tenant_id")
    request_id = body.get("request_id")
    if (
        not isinstance(intended_audience, str)
        or not intended_audience
        or not isinstance(tenant_raw, str)
        or not isinstance(request_id, str)
        or not request_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="delegation unavailable")
    try:
        tenant_id = UUID(tenant_raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="delegation unavailable") from exc
    result = await session.execute(
        select(Delegation)
        .where(Delegation.ref_hash == _ref_hash(opaque_ref), Delegation.tenant_id == tenant_id)
        .with_for_update()
    )
    record = result.scalar_one_or_none()
    now = datetime.now(UTC)
    configured_audience = _configured(os.getenv("I4A_DELEGATION_AUDIENCE")) or DEFAULT_AUDIENCE
    configured_issuer = _configured(os.getenv("I4A_DELEGATION_ISSUER"))
    configured_user_pool = _configured(os.getenv("I4A_DELEGATION_USER_POOL"))
    if (
        record is None
        or record.revoked_at is not None
        or _as_utc(record.expires_at) <= now
        or record.uses >= record.max_uses
        or intended_audience != configured_audience
        or record.audience != intended_audience
        or not configured_issuer
        or record.issuer != configured_issuer
        or not configured_user_pool
        or record.user_pool != configured_user_pool
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="delegation unavailable")
    record.uses += 1
    await session.commit()
    try:
        decrypted = await CryptoService.decrypt_config(record.encrypted_access_token, session)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="delegation unavailable") from exc
    token = decrypted.get("access_token") if isinstance(decrypted, dict) else None
    if not isinstance(token, str) or not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="delegation unavailable")
    return {
        "subject": record.subject,
        "tenant": str(record.tenant_id),
        "groups": list(record.groups or []),
        "audience": record.audience,
        "issuer": record.issuer,
        "user_pool": record.user_pool,
        "expires_at": _as_utc(record.expires_at).timestamp(),
        "access_token": token,
    }
