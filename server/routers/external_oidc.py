from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.session import get_async_session
from server.services import external_oidc

router = APIRouter(prefix="/auth/external", tags=["external-oidc"])


@router.get("/start")
async def start(request: Request, db: AsyncSession = Depends(get_async_session)):
    if not external_oidc.enabled():
        raise HTTPException(status_code=404, detail="External OIDC is disabled")
    try:
        return RedirectResponse(await external_oidc.begin_login(db), status_code=302)
    except external_oidc.ExternalOIDCError as exc:
        raise HTTPException(status_code=503, detail={"code": "BLOCKED_CONFIG", "message": str(exc)}) from exc


@router.get("/callback")
async def callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_async_session),
):
    if error or not code or not state:
        raise HTTPException(status_code=400, detail="OIDC authorization was not completed")
    try:
        session_value = await external_oidc.complete_login(code, state, db)
    except external_oidc.ExternalOIDCError as exc:
        raise HTTPException(status_code=401, detail={"code": "BLOCKED_AUTH", "message": str(exc)}) from exc
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        external_oidc.LOGIN_COOKIE,
        session_value,
        max_age=external_oidc.SESSION_TTL_SECONDS,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )
    return response


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_async_session),
):
    await external_oidc.revoke_cookie(request, response, db)


@router.get("/me")
async def me(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
):
    if not external_oidc.enabled():
        raise HTTPException(status_code=404, detail="External OIDC is disabled")
    auth = await external_oidc.auth_context_from_cookie(request, db, None)
    return {
        "id": str(auth.user.id),
        "email": auth.user.email,
        "full_name": auth.user.full_name,
        "avatar_url": auth.user.avatar_url,
        "is_verified": auth.user.is_verified,
        "is_active": auth.user.is_active,
        "is_superuser": auth.user.is_superuser,
        "external_subject": auth.external_subject,
        "external_groups": list(auth.external_groups),
    }
