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
from server.collaboration.repositories import CollaborationDeliveryTargetRepository, CollaborationInstallationRepository
from server.db.session import get_async_session
from server.schemas.collaboration import FeishuChatSelectRequest, FeishuEventIngestRequest, FeishuInstallationCreate, TestMessageRequest
from server.schemas.standard_response import success_response
from server.services.crypto_service import CryptoService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/collaboration", tags=["collaboration"])


def _require_admin(auth: AuthContext) -> None:
    if not auth.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")


def _delivery_target_payload(target) -> dict:
    config = target.config_json or {}
    return {
        "id": str(target.id),
        "target_type": target.target_type,
        "chat_id": target.external_target_id,
        "root_id": target.external_root_id,
        "display_name": target.display_name,
        "is_verified": target.is_verified,
        "confirm_non_production": bool(config.get("confirm_non_production")),
        "chat_type": config.get("chat_type") or target.target_type,
        "created_at": target.created_at.isoformat() if target.created_at else None,
        "updated_at": target.updated_at.isoformat() if target.updated_at else None,
    }


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
    _require_admin(auth)
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


@router.get("/installations/{installation_id}/feishu/chats")
async def list_feishu_chats(
    installation_id: UUID,
    page_token: str | None = None,
    page_size: int = 50,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    installation = await CollaborationInstallationRepository(session).get(installation_id)
    if not installation or installation.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found")
    if installation.platform != "feishu":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chat selector is only implemented for Feishu")
    credentials = await CryptoService.decrypt_config(installation.credentials_encrypted, session)
    client = FeishuApiClient(credentials["app_id"], credentials["app_secret"])
    try:
        remote = await client.list_chats(page_token=page_token, page_size=page_size)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Feishu chat listing failed: {exc}")
    targets = await CollaborationDeliveryTargetRepository(session).list_by_installation(installation.id)
    selected = {_delivery_target_payload(target)["chat_id"]: _delivery_target_payload(target) for target in targets}
    items = []
    for item in remote.get("items", []):
        chat_id = str(item.get("chat_id") or item.get("open_chat_id") or item.get("id") or "")
        if not chat_id:
            continue
        items.append(
            {
                "chat_id": chat_id,
                "name": item.get("name") or item.get("chat_name") or chat_id,
                "description": item.get("description"),
                "chat_type": item.get("chat_type") or item.get("type") or "group",
                "selected_target": selected.get(chat_id),
            }
        )
    return success_response(
        data={
            "items": items,
            "selected_targets": list(selected.values()),
            "next_page_token": remote.get("next_page_token"),
            "has_more": remote.get("has_more", False),
        },
        message="Feishu chats retrieved",
    )


@router.post("/installations/{installation_id}/feishu/chats")
async def select_feishu_chat(
    installation_id: UUID,
    payload: FeishuChatSelectRequest,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    installation = await CollaborationInstallationRepository(session).get(installation_id)
    if not installation or installation.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found")
    if installation.platform != "feishu":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chat selector is only implemented for Feishu")
    if not payload.confirm_non_production:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select an explicit non-production test group before sending Feishu test messages",
        )
    repo = CollaborationDeliveryTargetRepository(session)
    target = await repo.get_or_create(
        installation_id=installation.id,
        target_type="feishu_chat",
        external_target_id=payload.chat_id.strip(),
        external_root_id=payload.root_id,
        display_name=payload.name or payload.chat_id.strip(),
        is_verified=True,
    )
    target.config_json = {
        **(target.config_json or {}),
        "chat_type": payload.chat_type,
        "confirm_non_production": True,
        "selected_by": str(auth.user_id),
    }
    await session.commit()
    await session.refresh(target)
    return success_response(data=_delivery_target_payload(target), message="Feishu test chat selected")


@router.delete("/installations/{installation_id}")
async def delete_installation(
    installation_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    _require_admin(auth)
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
    _require_admin(auth)
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
    _require_admin(auth)
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
    if not payload.confirm_non_production:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirm a non-production test group before sending Feishu test messages",
        )
    target = None
    target_repo = CollaborationDeliveryTargetRepository(session)
    if payload.target_id:
        target = await target_repo.get(payload.target_id)
        if not target or target.installation_id != installation.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Selected Feishu chat not found")
    elif payload.chat_id:
        targets = await target_repo.list_by_installation(installation.id)
        target = next((item for item in targets if item.external_target_id == payload.chat_id), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a Feishu chat from the selector first")
    if not target.is_verified or not (target.config_json or {}).get("confirm_non_production"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected chat is not confirmed as a test group")
    credentials = await CryptoService.decrypt_config(installation.credentials_encrypted, session)
    client = FeishuApiClient(credentials["app_id"], credentials["app_secret"])
    try:
        result = await client.send_text_message(
            receive_id_type="chat_id",
            receive_id=target.external_target_id,
            text=payload.text,
            root_id=payload.root_id or target.external_root_id,
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
