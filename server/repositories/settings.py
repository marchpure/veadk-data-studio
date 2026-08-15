from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select

from server.models.settings import Setting
from server.repositories.base import AsyncCRUDRepository


class SettingRepository(AsyncCRUDRepository[Setting]):
    def __init__(self, session):
        super().__init__(session, Setting)

    async def get_by_key(self, setting_key: str) -> Setting | None:
        """Get a global/tenant setting by key (user_id is NULL)."""
        query = select(self._model).where(
            self._model.setting_key == setting_key,
            self._model.user_id.is_(None),
        )
        query = self._apply_tenant_filter(query)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_app_wide_by_key(self, setting_key: str) -> Setting | None:
        """Get an app-wide setting without tenant filtering.

        Local encryption predates multi-tenant local audit work and is app-wide.
        Multiple historical rows can exist after tenant bootstraps, so use the
        earliest row as the stable key source instead of failing on duplicates.
        """
        query = (
            select(self._model)
            .where(
                self._model.setting_key == setting_key,
                self._model.user_id.is_(None),
            )
            .order_by(self._model.created_at.asc(), self._model.id.asc())
            .limit(1)
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def list_app_wide_by_key(self, setting_key: str) -> list[Setting]:
        """List app-wide settings without tenant filtering, oldest first."""
        query = (
            select(self._model)
            .where(
                self._model.setting_key == setting_key,
                self._model.user_id.is_(None),
            )
            .order_by(self._model.created_at.asc(), self._model.id.asc())
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_by_key_for_user(self, setting_key: str, user_id: UUID) -> Setting | None:
        """Get a user-specific setting by key."""
        query = select(self._model).where(
            self._model.setting_key == setting_key,
            self._model.user_id == user_id,
        )
        query = self._apply_tenant_filter(query)
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def upsert_setting(
        self,
        setting_key: str,
        setting_value: str,
        description: str | None = None,
        is_encrypted: bool = False,
    ) -> Setting:
        """Upsert a global/tenant setting (user_id is NULL)."""
        existing = await self.get_by_key(setting_key)

        if existing:
            updated = await self.update(
                existing.id, {"setting_value": setting_value, "description": description, "is_encrypted": is_encrypted}
            )
            return updated
        else:
            create_data = {
                "setting_key": setting_key,
                "setting_value": setting_value,
                "description": description,
                "is_encrypted": is_encrypted,
                "user_id": None,
            }
            return await self.create(create_data)

    async def upsert_setting_for_user(
        self,
        setting_key: str,
        setting_value: str,
        user_id: UUID,
        description: str | None = None,
        is_encrypted: bool = False,
    ) -> Setting:
        """Upsert a user-specific setting."""
        existing = await self.get_by_key_for_user(setting_key, user_id)

        if existing:
            updated = await self.update(
                existing.id, {"setting_value": setting_value, "description": description, "is_encrypted": is_encrypted}
            )
            return updated
        else:
            create_data = {
                "setting_key": setting_key,
                "setting_value": setting_value,
                "description": description,
                "is_encrypted": is_encrypted,
                "user_id": user_id,
            }
            return await self.create(create_data)

    async def delete_by_key_for_user(self, setting_key: str, user_id: UUID) -> bool:
        """Delete a user-specific setting by key."""
        setting = await self.get_by_key_for_user(setting_key, user_id)
        if setting:
            return await self.delete(setting.id)
        return False

    async def search_by_key_content(
        self,
        setting_key: str,
        query: str,
        context_chars: int = 200,
    ) -> dict | None:
        keywords = [k.strip() for k in query.lower().split() if k.strip()]
        if not keywords:
            return None

        filters = [self._model.setting_value.ilike(f"%{keyword}%") for keyword in keywords]
        q = select(self._model).where(
            self._model.setting_key == setting_key,
            self._model.user_id.is_(None),
            or_(*filters),
        )
        q = self._apply_tenant_filter(q)
        result = await self._session.execute(q)
        setting = result.scalar_one_or_none()

        if not setting or not setting.setting_value:
            return None

        content = setting.setting_value
        content_lower = content.lower()
        seen_ranges: list[tuple[int, int]] = []

        for keyword in keywords:
            start_pos = 0
            while True:
                idx = content_lower.find(keyword, start_pos)
                if idx == -1:
                    break
                snip_start = max(0, idx - context_chars)
                snip_end = min(len(content), idx + len(keyword) + context_chars)

                merged = False
                for i, (s, e) in enumerate(seen_ranges):
                    if snip_start <= e and snip_end >= s:
                        seen_ranges[i] = (min(s, snip_start), max(e, snip_end))
                        merged = True
                        break
                if not merged:
                    seen_ranges.append((snip_start, snip_end))

                start_pos = idx + len(keyword)

        seen_ranges.sort()
        merged_ranges: list[tuple[int, int]] = []
        for s, e in seen_ranges:
            if merged_ranges and s <= merged_ranges[-1][1]:
                merged_ranges[-1] = (merged_ranges[-1][0], max(merged_ranges[-1][1], e))
            else:
                merged_ranges.append((s, e))

        snippets: list[str] = []
        for s, e in merged_ranges:
            snippet = content[s:e].strip()
            prefix = "..." if s > 0 else ""
            suffix = "..." if e < len(content) else ""
            snippets.append(f"{prefix}{snippet}{suffix}")

        return {"content_length": len(content), "snippets": snippets}

    async def list_all(self) -> list[Setting]:
        query = select(self._model)
        query = self._apply_tenant_filter(query)
        result = await self._session.execute(query)
        return list(result.scalars().all())
