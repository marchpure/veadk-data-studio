from __future__ import annotations

from typing import Literal
from uuid import UUID

from sqlalchemy import or_, select

from server.models.user_preferences import UserPreference
from server.repositories.base import AsyncCRUDRepository


class UserPreferenceRepository(AsyncCRUDRepository[UserPreference]):
    def __init__(self, session):
        super().__init__(session, UserPreference)

    async def get_by_type(
        self, preference_type: Literal["instructions", "style_guidelines"], user_id: UUID
    ) -> UserPreference | None:
        """Get preference by type (instructions or style_guidelines) for a specific user"""
        stmt = select(UserPreference).where(
            UserPreference.preference_type == preference_type,
            UserPreference.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def search_content(
        self,
        preference_type: Literal["instructions", "style_guidelines"],
        user_id: UUID,
        query: str,
        context_chars: int = 200,
    ) -> dict | None:
        keywords = [k.strip() for k in query.lower().split() if k.strip()]
        if not keywords:
            return None

        filters = [UserPreference.content.ilike(f"%{keyword}%") for keyword in keywords]
        stmt = select(UserPreference).where(
            UserPreference.preference_type == preference_type,
            UserPreference.user_id == user_id,
            or_(*filters),
        )
        result = await self._session.execute(stmt)
        pref = result.scalar_one_or_none()

        if not pref or not pref.content:
            return None

        content = pref.content
        content_lower = content.lower()
        snippets: list[str] = []
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

        for s, e in merged_ranges:
            snippet = content[s:e].strip()
            prefix = "..." if s > 0 else ""
            suffix = "..." if e < len(content) else ""
            snippets.append(f"{prefix}{snippet}{suffix}")

        return {"content_length": len(content), "snippets": snippets}

    async def upsert(
        self, preference_type: Literal["instructions", "style_guidelines"], content: str, user_id: UUID
    ) -> UserPreference:
        """Create or update preference by type for a specific user"""
        existing = await self.get_by_type(preference_type, user_id)

        if existing:
            existing.content = content
            await self._session.commit()
            await self._session.refresh(existing)
            return existing
        else:
            new_preference = UserPreference(preference_type=preference_type, content=content, user_id=user_id)
            self._session.add(new_preference)
            await self._session.commit()
            await self._session.refresh(new_preference)
            return new_preference
