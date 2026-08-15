from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.collaboration.feishu.adapter import FeishuChannelAdapter
from server.collaboration.feishu.client import FeishuApiClient
from server.collaboration.feishu.event_processor import process_feishu_event
from server.collaboration.installation_service import CollaborationInstallationService
from server.collaboration.repositories import CollaborationInstallationRepository
from server.db.session import get_async_session
from server.schemas.collaboration import FeishuEventIngestRequest, FeishuInstallationCreate, TestMessageRequest
from server.schemas.standard_response import success_response
from server.services.crypto_service import CryptoService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/collaboration", tags=["collaboration"])


@router.get("/installations")
async def list_installations(
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    rows = await CollaborationInstallationRepository(session).list_by_tenant(auth.tenant_id)
    data = [await CollaborationInstallationService.masked_installation(row) for row in rows]
    return success_response(data=data, message="Collaboration installations retrieved")


@router.get("/installations/feishu")
async def get_feishu_installation(
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    installation = await CollaborationInstallationRepository(session).get_by_tenant_platform(auth.tenant_id, "feishu")
    if not installation:
        return success_response(data=None, message="Feishu not configured")
    return success_response(
        data=await CollaborationInstallationService.masked_installation(installation),
        message="Feishu installation retrieved",
    )


@router.post("/installations/feishu")
async def create_feishu_installation(
    payload: FeishuInstallationCreate,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        installation = await CollaborationInstallationService.create_or_update_feishu(
            session=session,
            tenant_id=auth.tenant_id,
            app_id=payload.app_id.strip(),
            app_secret=payload.app_secret,
            connection_mode=payload.connection_mode,
            default_llm_connection_id=payload.default_llm_connection_id,
            installed_by=auth.user_id,
        )
    except Exception as exc:
        logger.warning(f"Failed to configure Feishu installation: {exc}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Feishu probe failed: {exc}")
    return success_response(
        data=await CollaborationInstallationService.masked_installation(installation),
        message="Feishu installation configured",
    )


@router.delete("/installations/{installation_id}")
async def delete_installation(
    installation_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    installation = await CollaborationInstallationRepository(session).get(installation_id)
    if not installation or installation.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found")
    if installation.platform == "feishu":
        await CollaborationInstallationService.disconnect_feishu(session, installation_id)
    installation.is_active = False
    installation.health_status = "disconnected"
    await session.commit()
    return success_response(message="Collaboration installation disconnected")


@router.post("/installations/{installation_id}/probe")
async def probe_installation(
    installation_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    installation = await CollaborationInstallationRepository(session).get(installation_id)
    if not installation or installation.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found")
    if installation.platform != "feishu":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Probe is only implemented for Feishu")
    try:
        data = await FeishuChannelAdapter(session, installation).probe()
    except Exception as exc:
        installation.health_status = "failed"
        installation.health_error = str(exc)
        await session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Feishu probe failed: {exc}")
    return success_response(data=data, message="Feishu probe succeeded")


@router.post("/installations/{installation_id}/connect")
async def connect_installation(
    installation_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    installation = await CollaborationInstallationRepository(session).get(installation_id)
    if not installation or installation.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found")
    if installation.platform != "feishu":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connect is only implemented for Feishu")
    data = await CollaborationInstallationService.connect_feishu(session, installation_id)
    return success_response(data=data, message="Feishu WebSocket connect requested")


@router.post("/installations/{installation_id}/disconnect")
async def disconnect_installation(
    installation_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    installation = await CollaborationInstallationRepository(session).get(installation_id)
    if not installation or installation.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found")
    data = await CollaborationInstallationService.disconnect_feishu(session, installation_id)
    return success_response(data=data, message="Feishu WebSocket disconnected")


@router.get("/installations/{installation_id}/health")
async def get_installation_health(
    installation_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    installation = await CollaborationInstallationRepository(session).get(installation_id)
    if not installation or installation.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found")
    return success_response(
        data={
            "id": str(installation.id),
            "platform": installation.platform,
            "connection_mode": installation.connection_mode,
            "health_status": installation.health_status,
            "health_error": installation.health_error,
            "last_connected_at": installation.last_connected_at.isoformat() if installation.last_connected_at else None,
            "last_event_at": installation.last_event_at.isoformat() if installation.last_event_at else None,
        },
        message="Collaboration health retrieved",
    )


@router.post("/installations/{installation_id}/test-message")
async def send_test_message(
    installation_id: UUID,
    payload: TestMessageRequest,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    installation = await CollaborationInstallationRepository(session).get(installation_id)
    if not installation or installation.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found")
    if installation.platform != "feishu":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Test message is only implemented for Feishu")
    credentials = await CryptoService.decrypt_config(installation.credentials_encrypted, session)
    client = FeishuApiClient(credentials["app_id"], credentials["app_secret"])
    try:
        result = await client.send_text_message(
            receive_id_type="chat_id",
            receive_id=payload.chat_id,
            text=payload.text,
            root_id=payload.root_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Feishu test message failed: {exc}")
    return success_response(data=result, message="Feishu test message sent")


@router.post("/feishu/events/{installation_public_id}")
async def ingest_feishu_webhook_event(
    installation_public_id: str,
    payload: FeishuEventIngestRequest,
    session: AsyncSession = Depends(get_async_session),
):
    installation = await CollaborationInstallationRepository(session).get_by_public_id(installation_public_id)
    if not installation or installation.platform != "feishu":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found")
    result = await process_feishu_event(session, installation, payload.event)
    return success_response(data=result, message="Feishu event accepted")
