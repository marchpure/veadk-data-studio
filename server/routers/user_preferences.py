from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.prompts.defaults import DEFAULT_STYLE_GUIDELINES, DEFAULT_USER_INSTRUCTIONS
from server.repositories.settings import SettingRepository
from server.schemas.standard_response import success_response
from server.schemas.user_preferences import UserPreferenceUpdate
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

PREFERENCE_TO_SETTING_KEY = {
    "instructions": "workspace_instructions",
    "style_guidelines": "workspace_style_guidelines",
}

PREFERENCE_DEFAULTS = {
    "instructions": DEFAULT_USER_INSTRUCTIONS,
    "style_guidelines": DEFAULT_STYLE_GUIDELINES,
}


@router.get("/preferences/{preference_type}")
async def get_preference(
    preference_type: Literal["instructions", "style_guidelines"],
    auth: AuthContext = Depends(require_scope(Scope.USER_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        setting_key = PREFERENCE_TO_SETTING_KEY[preference_type]
        repo = SettingRepository(session)
        setting = await repo.get_by_key(setting_key)

        if setting:
            return success_response(
                data={
                    "preference_type": preference_type,
                    "content": setting.setting_value,
                    "id": str(setting.id),
                    "created_at": setting.created_at.isoformat() if setting.created_at else None,
                    "updated_at": setting.updated_at.isoformat() if setting.updated_at else None,
                },
                message="Preference retrieved successfully",
            )
        else:
            return success_response(
                data={
                    "preference_type": preference_type,
                    "content": PREFERENCE_DEFAULTS[preference_type],
                    "is_default": True,
                },
                message="Default preference returned (not yet customized)",
            )
    except Exception as e:
        logger.error(f"Error fetching preference {preference_type}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch preference: {str(e)}"
        )


@router.put("/preferences/{preference_type}")
async def update_preference(
    preference_type: Literal["instructions", "style_guidelines"],
    payload: UserPreferenceUpdate,
    auth: AuthContext = Depends(require_scope(Scope.USER_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    if preference_type == "instructions" and len(payload.content.split()) > 2000:
        word_count = len(payload.content.split())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Instructions exceed the 2000 word limit (current: {word_count} words). Please shorten the content.",
        )

    try:
        setting_key = PREFERENCE_TO_SETTING_KEY[preference_type]
        repo = SettingRepository(session)
        setting = await repo.upsert_setting(setting_key, payload.content)

        return success_response(
            data={
                "preference_type": preference_type,
                "content": setting.setting_value,
                "id": str(setting.id),
                "created_at": setting.created_at.isoformat() if setting.created_at else None,
                "updated_at": setting.updated_at.isoformat() if setting.updated_at else None,
            },
            message="Preference updated successfully",
        )
    except Exception as e:
        logger.error(f"Error updating preference {preference_type}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update preference: {str(e)}"
        )


@router.post("/preferences/{preference_type}/reset")
async def reset_preference_to_default(
    preference_type: Literal["instructions", "style_guidelines"],
    auth: AuthContext = Depends(require_scope(Scope.USER_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        setting_key = PREFERENCE_TO_SETTING_KEY[preference_type]
        default_content = PREFERENCE_DEFAULTS[preference_type]

        repo = SettingRepository(session)
        setting = await repo.upsert_setting(setting_key, default_content)

        return success_response(
            data={
                "preference_type": preference_type,
                "content": setting.setting_value,
                "id": str(setting.id),
                "created_at": setting.created_at.isoformat() if setting.created_at else None,
                "updated_at": setting.updated_at.isoformat() if setting.updated_at else None,
            },
            message="Preference reset to default successfully",
        )
    except Exception as e:
        logger.error(f"Error resetting preference {preference_type}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to reset preference: {str(e)}"
        )
