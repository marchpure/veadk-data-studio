from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.tenant_context import get_tenant_id
from server.db.session import AsyncSessionFactory
from server.services.settings import SettingsService

_cached_encryption_keys: dict[str, bytes] = {}


async def get_app_encryption_key(session: AsyncSession | None = None) -> bytes:
    """
    Get the application encryption key, using cached value if available.

    In hosted mode:
    - Uses legacy ENCRYPTION_KEY env var if set (backward compatibility)
    - Otherwise derives 32-byte key from APP_SECRET using SHA-256
    In local mode: Uses encryption key from database settings table (per-tenant, auto-generated)
    """
    from server.utils.config_loader import get_app_secret, is_self_hosted

    if is_self_hosted():
        # Check for legacy ENCRYPTION_KEY first (backward compatibility)
        env_key = os.getenv("ENCRYPTION_KEY")
        cache_key = "hosted:env" if env_key else "hosted:app_secret"
        if cache_key in _cached_encryption_keys:
            return _cached_encryption_keys[cache_key]
        if env_key:
            _cached_encryption_keys[cache_key] = bytes.fromhex(env_key)
            return _cached_encryption_keys[cache_key]

        # Derive from APP_SECRET using SHA-256 (produces exactly 32 bytes for AES-256)
        app_secret = get_app_secret()
        if app_secret == "change-me-in-production-use-strong-secret":
            raise ValueError("APP_SECRET environment variable must be set in hosted mode")
        _cached_encryption_keys[cache_key] = hashlib.sha256(app_secret.encode()).digest()
        return _cached_encryption_keys[cache_key]

    tenant_id = get_tenant_id()
    cache_key = f"tenant:{tenant_id}" if tenant_id else "tenant:unset"
    if cache_key in _cached_encryption_keys:
        return _cached_encryption_keys[cache_key]

    # Local mode: use database setting scoped by the active tenant context.
    if session:
        key = await SettingsService.get_or_create_encryption_key(session)
        _cached_encryption_keys[cache_key] = key
        return key
    else:
        async with AsyncSessionFactory() as new_session:
            key = await SettingsService.get_or_create_encryption_key(new_session)
            _cached_encryption_keys[cache_key] = key
            return key


def set_encryption_key(key: bytes) -> None:
    """Set the cached encryption key."""
    tenant_id = get_tenant_id()
    cache_key = f"tenant:{tenant_id}" if tenant_id else "manual"
    _cached_encryption_keys[cache_key] = key


def clear_encryption_key_cache() -> None:
    """Clear the cached encryption key."""
    _cached_encryption_keys.clear()


class CryptoService:
    """Unified encryption service for all configuration data across the application."""

    @staticmethod
    async def encrypt_config(config_dict: dict[str, Any], session=None) -> str:
        """
        Encrypt a configuration dictionary using AES-GCM.

        Args:
            config_dict: Dictionary to encrypt
            session: Optional database session for key retrieval

        Returns:
            Base64-encoded encrypted data with embedded nonce
        """
        key = await get_app_encryption_key(session)
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        plaintext = json.dumps(config_dict).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        return base64.b64encode(nonce + ciphertext).decode("utf-8")

    @staticmethod
    async def decrypt_config(b64_blob: str, session=None) -> dict[str, Any]:
        """
        Decrypt a base64-encoded configuration blob using AES-GCM.

        Args:
            b64_blob: Base64-encoded encrypted data with embedded nonce
            session: Optional database session for key retrieval

        Returns:
            Decrypted configuration dictionary
        """
        data = base64.b64decode(b64_blob)
        nonce, ciphertext = data[:12], data[12:]
        key = await get_app_encryption_key(session)
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return json.loads(plaintext.decode("utf-8"))

    @staticmethod
    async def decrypt_config_with_local_legacy_keys(b64_blob: str, session) -> dict[str, Any]:
        """Local-only migration helper for historical single-user encrypted rows."""
        from server.utils.config_loader import is_self_hosted

        if is_self_hosted():
            raise InvalidTag("legacy local key fallback is disabled in hosted/self-hosted mode")

        data = base64.b64decode(b64_blob)
        nonce, ciphertext = data[:12], data[12:]
        attempted_keys: list[bytes] = []
        from server.repositories.settings import SettingRepository
        from server.services.settings import SettingsService

        repo = SettingRepository(session)
        for setting in await repo.list_app_wide_by_key(SettingsService.ENCRYPTION_KEY_SETTING):
            try:
                key = base64.b64decode(setting.setting_value)
            except Exception:
                continue
            if key in attempted_keys:
                continue
            attempted_keys.append(key)
            try:
                aesgcm = AESGCM(key)
                plaintext = aesgcm.decrypt(nonce, ciphertext, None)
                return json.loads(plaintext.decode("utf-8"))
            except InvalidTag:
                continue
        raise InvalidTag("legacy local keys could not decrypt configuration")
