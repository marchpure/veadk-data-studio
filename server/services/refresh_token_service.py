from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.refresh_token import RefreshToken
from server.utils.config_loader import get_token_config


class RefreshTokenService:
    @staticmethod
    def refresh_token_max_age_seconds() -> int:
        token_config = get_token_config()
        return token_config["refresh_token_lifetime_seconds"]

    @staticmethod
    def generate_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    async def create(user_id: UUID, ip_address: str | None, session: AsyncSession) -> str:
        await RefreshTokenService.revoke_all_for_user(user_id, session)

        raw_token = RefreshTokenService.generate_token()
        token_hash = RefreshTokenService.hash_token(raw_token)
        token_config = get_token_config()
        expires_at = datetime.utcnow() + timedelta(seconds=token_config["refresh_token_lifetime_seconds"])

        refresh_token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            ip_address=ip_address,
            expires_at=expires_at,
        )
        session.add(refresh_token)
        await session.commit()

        return raw_token

    @staticmethod
    async def verify(token: str, session: AsyncSession) -> RefreshToken | None:
        token_hash = RefreshTokenService.hash_token(token)
        result = await session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.utcnow(),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def revoke_all_for_user(user_id: UUID, session: AsyncSession) -> None:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.utcnow())
        )

    @staticmethod
    async def revoke_token(token: str, session: AsyncSession) -> bool:
        token_hash = RefreshTokenService.hash_token(token)
        result = await session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.utcnow())
        )
        await session.commit()
        return result.rowcount > 0
