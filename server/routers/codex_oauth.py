from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.session import get_async_session
from server.repositories.llm_connections import LLMConnectionRepository
from server.schemas.standard_response import error_response, success_response
from server.services.codex_oauth_service import (
    get_valid_codex_token,
    poll_device_code_auth,
    start_device_code_auth,
)
from server.services.crypto_service import CryptoService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/codex-oauth", tags=["codex-oauth"])


@router.post("/start")
async def start_oauth():
    try:
        result = await start_device_code_auth()
        logger.info("[CODEX OAUTH API] Started device code auth flow")
        return success_response(result, "Device code generated. Enter the code at the verification URL.")
    except Exception as e:
        logger.error(f"[CODEX OAUTH API] Failed to start device code auth: {e}")
        return error_response(str(e), "Failed to start authentication flow")


@router.get("/poll/{session_id}")
async def poll_result(session_id: str):
    try:
        token_config = await poll_device_code_auth(session_id)
        return success_response(
            {"authenticated": True, "tokens": token_config},
            "Successfully authenticated with OpenAI Codex",
        )
    except ValueError as e:
        logger.error(f"[CODEX OAUTH API] Poll failed: {e}")
        return error_response(str(e), "Authentication failed")
    except Exception as e:
        logger.error(f"[CODEX OAUTH API] Unexpected poll error: {e}")
        return error_response(str(e), "Failed to check authentication result")


@router.get("/status/{connection_id}")
async def check_auth_status(
    connection_id: str,
    session: AsyncSession = Depends(get_async_session),
):
    try:
        repo = LLMConnectionRepository(session)
        connection = await repo.get(connection_id)

        if not connection or not connection.config:
            return success_response(
                {"authenticated": False},
                "Connection not found or not configured",
            )

        cfg = await CryptoService.decrypt_config(connection.config, session)
        has_token = bool(cfg.get("access_token"))

        return success_response(
            {"authenticated": has_token, "has_refresh_token": bool(cfg.get("refresh_token"))},
            "Authenticated" if has_token else "Not authenticated",
        )
    except Exception as e:
        logger.error(f"[CODEX OAUTH API] Status check failed: {e}")
        return error_response(str(e), "Failed to check authentication status")


@router.post("/refresh/{connection_id}")
async def refresh_access_token(
    connection_id: str,
    session: AsyncSession = Depends(get_async_session),
):
    try:
        token = await get_valid_codex_token(connection_id, session)
        if token:
            return success_response({"refreshed": True}, "Token refreshed successfully")
        else:
            return error_response("Token refresh failed", "Token refresh failed")
    except Exception as e:
        logger.error(f"[CODEX OAUTH API] Refresh failed: {e}")
        return error_response(str(e), "Failed to refresh token")
