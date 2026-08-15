"""
Waitlist Router - API endpoints for one-shot registration + credentials.
"""

import logging
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.session import get_async_session
from server.schemas.standard_response import success_response
from server.schemas.waitlist import JoinWaitlistRequest
from server.services.waitlist_service import waitlist_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/waitlist/join")
async def join_waitlist(request: JoinWaitlistRequest, session: AsyncSession = Depends(get_async_session)):
    """
    One-shot register: saves email, creates User+Tenant, returns full credentials.
    """
    try:
        result = await waitlist_service.join_waitlist(request.email, session, request.name)
        return success_response(data=result, message="Registered successfully")
    except httpx.HTTPStatusError as e:
        error_data = e.response.json() if e.response else {}
        error_msg = error_data.get("error", str(e))
        logger.exception(f"Failed to register: {error_msg}")
        raise HTTPException(status_code=e.response.status_code if e.response else 500, detail=error_msg)
    except Exception as e:
        logger.exception(f"Error registering: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/credentials/get")
async def get_stored_credentials(
    session: AsyncSession = Depends(get_async_session),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
):
    """
    Get stored credentials from local database.
    Requires X-Tenant-ID header to identify the user session.
    Returns: {email, apiKey, hasCredits, tenantId, tenantName} or null if not found
    """
    try:
        tenant_id = None
        if x_tenant_id:
            try:
                tenant_id = UUID(x_tenant_id)
            except ValueError:
                pass

        credentials = await waitlist_service.get_stored_credentials(tenant_id, session)

        if not credentials:
            return success_response(data=None, message="No credentials found")

        return success_response(data=credentials, message="Credentials retrieved")
    except Exception as e:
        logger.exception(f"Error getting credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logout")
async def logout():
    """
    Logout the current user (local mode only).
    In the new flow, client just clears localStorage. This endpoint is a no-op
    but kept for backwards compatibility.
    """
    return success_response(data=None, message="Logged out successfully")
