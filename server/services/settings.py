from __future__ import annotations

import base64
import os
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.models.settings import Setting
from server.repositories.settings import SettingRepository
from server.schemas.settings import SettingCreate, SettingUpdate


class SettingsService:
    ENCRYPTION_KEY_SETTING = "app_encryption_key"

    @staticmethod
    async def create_setting(
        session: AsyncSession,
        payload: SettingCreate,
    ) -> Setting:
        repo = SettingRepository(session)
        setting = await repo.create(
            {
                "setting_key": payload.setting_key,
                "setting_value": payload.setting_value,
                "description": payload.description,
                "is_encrypted": payload.is_encrypted,
            }
        )
        return setting

    @staticmethod
    async def get_setting(
        session: AsyncSession,
        setting_id: str,
    ) -> Setting | None:
        repo = SettingRepository(session)
        setting = await repo.get(setting_id)
        return setting

    @staticmethod
    async def get_setting_by_key(
        session: AsyncSession,
        setting_key: str,
    ) -> Setting | None:
        repo = SettingRepository(session)
        setting = await repo.get_by_key(setting_key)
        return setting

    @staticmethod
    async def update_setting(
        session: AsyncSession,
        setting_id: str,
        payload: SettingUpdate,
    ) -> Setting | None:
        repo = SettingRepository(session)
        data = {k: v for k, v in payload.model_dump().items() if v is not None}
        setting = await repo.update(setting_id, data)
        return setting

    @staticmethod
    async def upsert_setting(
        session: AsyncSession,
        setting_key: str,
        setting_value: str,
        description: str | None = None,
        is_encrypted: bool = False,
    ) -> Setting:
        repo = SettingRepository(session)
        setting = await repo.upsert_setting(setting_key, setting_value, description, is_encrypted)
        return setting

    @staticmethod
    async def list_settings(
        session: AsyncSession,
    ) -> list[Setting]:
        repo = SettingRepository(session)
        settings = await repo.list_all()
        return settings

    @staticmethod
    async def delete_setting(
        session: AsyncSession,
        setting_id: str,
    ) -> bool:
        repo = SettingRepository(session)
        return await repo.delete(setting_id)

    @staticmethod
    async def delete_setting_by_key(
        session: AsyncSession,
        setting_key: str,
    ) -> bool:
        """Delete a setting by its key"""
        repo = SettingRepository(session)
        setting = await repo.get_by_key(setting_key)
        if setting:
            return await repo.delete(setting.id)
        return False

    # User-specific settings methods

    @staticmethod
    async def get_setting_by_key_for_user(
        session: AsyncSession,
        setting_key: str,
        user_id: UUID,
    ) -> Setting | None:
        """Get a user-specific setting by key."""
        repo = SettingRepository(session)
        setting = await repo.get_by_key_for_user(setting_key, user_id)
        return setting

    @staticmethod
    async def upsert_setting_for_user(
        session: AsyncSession,
        setting_key: str,
        setting_value: str,
        user_id: UUID,
        description: str | None = None,
        is_encrypted: bool = False,
    ) -> Setting:
        """Upsert a user-specific setting."""
        repo = SettingRepository(session)
        setting = await repo.upsert_setting_for_user(setting_key, setting_value, user_id, description, is_encrypted)
        return setting

    @staticmethod
    async def delete_setting_by_key_for_user(
        session: AsyncSession,
        setting_key: str,
        user_id: UUID,
    ) -> bool:
        """Delete a user-specific setting by key."""
        repo = SettingRepository(session)
        return await repo.delete_by_key_for_user(setting_key, user_id)

    @staticmethod
    async def get_or_create_encryption_key(session: AsyncSession) -> bytes:
        repo = SettingRepository(session)

        existing_setting = await repo.get_by_key(SettingsService.ENCRYPTION_KEY_SETTING)

        if existing_setting:
            return base64.b64decode(existing_setting.setting_value)

        new_key = os.urandom(32)
        key_b64 = base64.b64encode(new_key).decode("utf-8")

        await repo.upsert_setting(
            setting_key=SettingsService.ENCRYPTION_KEY_SETTING,
            setting_value=key_b64,
            description="Tenant application encryption key for sensitive data",
            is_encrypted=False,
        )

        return new_key
