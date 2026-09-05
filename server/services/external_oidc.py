from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import jwt
from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, _get_auth_context_hosted
from server.models.external_oidc import ExternalOIDCLogin, ExternalOIDCSession
from server.models.tenant import Tenant
from server.models.tenant_member import TenantMember, TenantRole
from server.models.user import User
from server.services.crypto_service import CryptoService
from server.services.runtime_secrets import RuntimeSecretError, get_runtime_secret

LOGIN_COOKIE = "dwv1_oidc_session"
LOGIN_TTL_SECONDS = 600
SESSION_TTL_SECONDS = 12 * 60 * 60
STATE_PATTERN = 64


class ExternalOIDCError(RuntimeError):
    pass


def enabled() -> bool:
    return os.getenv("DWV1_EXTERNAL_OIDC_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def _issuer() -> str:
    value = os.getenv("DWV1_OIDC_ISSUER", "").strip().rstrip("/")
    if not value.startswith("https://"):
        raise ExternalOIDCError("OIDC issuer is not configured")
    return value


def callback_uri() -> str:
    origin = os.getenv("DWV1_OIDC_PUBLIC_ORIGIN", "").strip().rstrip("/")
    if not origin.startswith("https://"):
        raise ExternalOIDCError("OIDC public origin must be HTTPS")
    return f"{origin}/api/auth/external/callback"


def _audience() -> str:
    value = os.getenv("DWV1_OIDC_AUDIENCE", "").strip()
    if not value:
        raise ExternalOIDCError("OIDC audience is not configured")
    return value


def _user_pool() -> str:
    value = os.getenv("DWV1_OIDC_USER_POOL", "").strip()
    if not value:
        raise ExternalOIDCError("OIDC UserPool is not configured")
    return value


def _client_id() -> str:
    value = os.getenv("DWV1_OIDC_CLIENT_ID", "").strip()
    if not value:
        raise ExternalOIDCError("OIDC client id is not configured")
    return value


def _groups(claims: dict[str, Any]) -> list[str]:
    configured_claim = os.getenv("DWV1_OIDC_GROUPS_CLAIM", "groups").strip() or "groups"
    claim_names = [configured_claim]
    # VeIdentity UserPool emits group UIDs under this claim. Keep the
    # configured claim first, while accepting the provider's canonical claim
    # when a deployment still has the legacy "groups" setting.
    for claim_name in ("identity_userpool_group_uids", "identity_userpool_groups", "groups"):
        if claim_name not in claim_names:
            claim_names.append(claim_name)
    for claim_name in claim_names:
        value = claims.get(claim_name)
        if isinstance(value, str):
            if value:
                return [value]
            continue
        if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
            if value:
                return list(dict.fromkeys(value))
    return []


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _pkce_verifier() -> str:
    return _b64(secrets.token_bytes(32))


async def _discovery() -> dict[str, Any]:
    issuer = _issuer()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{issuer}/.well-known/openid-configuration")
        response.raise_for_status()
        payload = response.json()
    required = ("authorization_endpoint", "token_endpoint", "jwks_uri")
    if not all(isinstance(payload.get(key), str) and payload[key].startswith("https://") for key in required):
        raise ExternalOIDCError("OIDC discovery metadata is incomplete")
    return payload


async def _client_secret() -> str:
    try:
        return get_runtime_secret(
            "data_studio_oauth_client_secret",
            env_name="DWV1_OIDC_CLIENT_SECRET",
        ) or ""
    except RuntimeSecretError as exc:
        raise ExternalOIDCError("OIDC client secret is unavailable") from exc


async def _verify_jwt(
    token: str,
    discovery: dict[str, Any],
    *,
    audience: str,
    require_client_binding: bool = True,
) -> dict[str, Any]:
    if token.count(".") != 2:
        raise ExternalOIDCError("OIDC token is not a JWT")
    try:
        signing_key = jwt.PyJWKClient(discovery["jwks_uri"]).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=_issuer(),
            audience=audience,
            options={"require": ["exp", "nbf", "iss", "aud", "sub"]},
        )
    except Exception as exc:
        raise ExternalOIDCError("OIDC token verification failed") from exc
    client_claim = claims.get("client_id") or claims.get("azp")
    if require_client_binding and client_claim != _client_id():
        raise ExternalOIDCError("OIDC token client binding failed")
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise ExternalOIDCError("OIDC token subject is missing")
    return claims


async def begin_login(db: AsyncSession) -> str:
    discovery = await _discovery()
    state = secrets.token_urlsafe(STATE_PATTERN)
    verifier = _pkce_verifier()
    redirect = callback_uri()
    expires = datetime.now(UTC) + timedelta(seconds=LOGIN_TTL_SECONDS)
    encrypted_verifier = await CryptoService.encrypt_config({"code_verifier": verifier}, db)
    db.add(
        ExternalOIDCLogin(
            state_hash=_hash(state),
            encrypted_code_verifier=encrypted_verifier,
            redirect_uri=redirect,
            expires_at=expires,
        )
    )
    await db.commit()
    query = {
        "response_type": "code",
        "client_id": _client_id(),
        "redirect_uri": redirect,
        "scope": os.getenv("DWV1_OIDC_SCOPE", "openid profile email"),
        "state": state,
        "code_challenge": _b64(hashlib.sha256(verifier.encode("ascii")).digest()),
        "code_challenge_method": "S256",
    }
    return f"{discovery['authorization_endpoint']}?{urlencode(query)}"


async def complete_login(code: str, state: str, db: AsyncSession) -> str:
    if not code or not state:
        raise ExternalOIDCError("OIDC callback is incomplete")
    result = await db.execute(
        select(ExternalOIDCLogin)
        .where(ExternalOIDCLogin.state_hash == _hash(state))
        .with_for_update()
    )
    login = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if login is None or login.consumed_at is not None or login.expires_at <= now:
        raise ExternalOIDCError("OIDC state is invalid or expired")
    login.consumed_at = now
    await db.flush()
    # Consume the state in its own transaction so failed token exchange cannot
    # make the authorization response replayable.
    await db.commit()
    verifier_blob = await CryptoService.decrypt_config(login.encrypted_code_verifier, db)
    verifier = verifier_blob.get("code_verifier")
    if not isinstance(verifier, str) or login.redirect_uri != callback_uri():
        raise ExternalOIDCError("OIDC callback binding failed")
    discovery = await _discovery()
    client_secret = await _client_secret()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            discovery["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": login.redirect_uri,
                "client_id": _client_id(),
                "client_secret": client_secret,
                "code_verifier": verifier,
            },
        )
        if response.status_code >= 400:
            raise ExternalOIDCError("OIDC token exchange failed")
        tokens = response.json()
        access_token = tokens.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ExternalOIDCError("OIDC access token is missing")
        id_claims: dict[str, Any] = {}
        if isinstance(tokens.get("id_token"), str):
            id_claims = await _verify_jwt(
                tokens["id_token"],
                discovery,
                audience=_client_id(),
                require_client_binding=False,
            )
        else:
            id_claims = {}
        access_claims = await _verify_jwt(access_token, discovery, audience=_audience())
        userinfo_claims: dict[str, Any] = {}
        userinfo_endpoint = discovery.get("userinfo_endpoint")
        if isinstance(userinfo_endpoint, str):
            userinfo_response = await client.get(
                userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_response.status_code < 400 and isinstance(userinfo_response.json(), dict):
                userinfo_claims = userinfo_response.json()
    claims = {**access_claims, **id_claims, **userinfo_claims}
    subject = claims.get("sub")
    email = claims.get("email")
    if not isinstance(subject, str) or not subject:
        raise ExternalOIDCError("OIDC user claims are incomplete")
    if not isinstance(email, str) or "@" not in email:
        # Some UserPool test and service identities intentionally have no
        # email attribute. The local user table still requires a unique email,
        # so derive a non-routable association key from the verified issuer
        # and subject. This value is never treated as an external claim.
        email = f"oidc-{_hash(f'{_issuer()}:{subject}')[:32]}@external.invalid"
    if id_claims.get("sub") and id_claims["sub"] != access_claims["sub"]:
        raise ExternalOIDCError("OIDC subject mismatch")
    if userinfo_claims.get("sub") and userinfo_claims["sub"] != access_claims["sub"]:
        raise ExternalOIDCError("OIDC userinfo subject mismatch")
    groups = _groups(claims)
    configured_group = os.getenv("DWV1_OIDC_REQUIRED_GROUP", "").strip()
    if configured_group and configured_group not in groups:
        raise ExternalOIDCError("OIDC user is not a member of the required group")
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        from fastapi_users.password import PasswordHelper

        user = User(
            id=uuid4(),
            email=email,
            hashed_password=PasswordHelper().hash(secrets.token_urlsafe(32)),
            is_active=True,
            is_verified=True,
            full_name=claims.get("name") if isinstance(claims.get("name"), str) else None,
        )
        db.add(user)
        await db.flush()
        tenant = Tenant(
            id=uuid4(),
            name=os.getenv("DWV1_DEFAULT_TENANT_NAME", "Data Studio"),
            slug=f"dwv1-{user.id.hex[:12]}",
            owner_id=user.id,
            is_personal=True,
        )
        db.add(tenant)
        await db.flush()
        db.add(TenantMember(user_id=user.id, tenant_id=tenant.id, role=TenantRole.OWNER.value, joined_at=now))
    else:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.owner_id == user.id).order_by(Tenant.created_at).limit(1))
        ).scalar_one_or_none()
        if tenant is None:
            raise ExternalOIDCError("OIDC user has no workspace")
    session_value = secrets.token_urlsafe(48)
    try:
        token_lifetime = int(tokens.get("expires_in", 3600))
    except (TypeError, ValueError) as exc:
        raise ExternalOIDCError("OIDC token lifetime is invalid") from exc
    if token_lifetime <= 0:
        raise ExternalOIDCError("OIDC token is already expired")
    expires_at = now + timedelta(seconds=min(SESSION_TTL_SECONDS, token_lifetime))
    encrypted_tokens = await CryptoService.encrypt_config(
        {
            "access_token": access_token,
            "refresh_token": tokens.get("refresh_token"),
            "id_token": tokens.get("id_token"),
        },
        db,
    )
    db.add(
        ExternalOIDCSession(
            session_hash=_hash(session_value),
            user_id=user.id,
            subject=subject,
            groups=json.dumps(groups),
            encrypted_tokens=encrypted_tokens,
            issuer=_issuer(),
            audience=_audience(),
            user_pool=_user_pool(),
            expires_at=expires_at,
        )
    )
    await db.commit()
    return session_value


async def auth_context_from_cookie(
    request: Request,
    db: AsyncSession,
    x_tenant_id: str | None,
) -> AuthContext:
    session_value = request.cookies.get(LOGIN_COOKIE)
    if not session_value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC login required")
    result = await db.execute(
        select(ExternalOIDCSession, User)
        .join(User, User.id == ExternalOIDCSession.user_id)
        .where(ExternalOIDCSession.session_hash == _hash(session_value))
    )
    row = result.one_or_none()
    now = datetime.now(UTC)
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC session unavailable")
    external, user = row
    if external.revoked_at is not None or external.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC session expired")
    try:
        configured_identity = (_issuer(), _audience(), _user_pool())
    except ExternalOIDCError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OIDC unavailable") from exc
    if (external.issuer, external.audience, external.user_pool) != configured_identity:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC session configuration changed")
    auth = await _get_auth_context_hosted(user, db, x_tenant_id)
    try:
        groups = json.loads(external.groups)
    except (TypeError, json.JSONDecodeError):
        groups = []
    if not isinstance(groups, list) or not all(isinstance(item, str) for item in groups):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="OIDC groups unavailable")
    auth.external_subject = external.subject
    auth.external_groups = tuple(groups)
    auth.external_issuer = external.issuer
    auth.external_audience = external.audience
    auth.external_user_pool = external.user_pool
    tokens = await CryptoService.decrypt_config(external.encrypted_tokens, db)
    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC access token unavailable")
    auth.access_token = access_token
    return auth


async def revoke_cookie(request: Request, response: Response, db: AsyncSession) -> None:
    value = request.cookies.get(LOGIN_COOKIE)
    if value:
        result = await db.execute(
            select(ExternalOIDCSession).where(ExternalOIDCSession.session_hash == _hash(value))
        )
        session = result.scalar_one_or_none()
        if session:
            session.revoked_at = datetime.now(UTC)
            await db.commit()
    response.delete_cookie(LOGIN_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
