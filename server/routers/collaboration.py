from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.collaboration.feishu.adapter import FeishuChannelAdapter
from server.collaboration.feishu.callback import (
    FeishuCallbackVerificationError,
    FeishuCallbackVerifier,
    safe_callback_error,
)
from server.collaboration.feishu.client import FeishuApiClient, feishu_error_requires_reauth, safe_feishu_error_message
from server.collaboration.feishu.event_processor import process_feishu_event
from server.collaboration.feishu.normalizer import normalize_feishu_message_event
from server.collaboration.feishu.subscription import feishu_event_subscription_payload
from server.collaboration.feishu.transport import feishu_ws_manager
from server.collaboration.installation_service import CollaborationInstallationService
from server.collaboration.models import (
    CollaborationConversation,
    CollaborationDeliveryTarget,
    CollaborationInstallation,
    CollaborationResponseRef,
    ExternalIdentity,
)
from server.collaboration.repositories import (
    CollaborationDeliveryTargetRepository,
    CollaborationEventRepository,
    CollaborationInstallationRepository,
    CollaborationLeaseRepository,
    CollaborationResponseRefRepository,
    normalize_root_id,
)
from server.db.session import AsyncSessionFactory, get_async_session
from server.models.llm_connections import LLMConnection
from server.models.tenant_member import TenantMember
from server.models.user import User
from server.schemas.collaboration import (
    ExternalIdentityMappingRequest,
    FeishuDeliveryTargetBindRequest,
    FeishuInstallationCreate,
    FeishuOAuthResultRequest,
    FeishuOAuthStartRequest,
    FeishuOutboundMessageRequest,
    TestMessageRequest,
)
from server.schemas.standard_response import success_response
from server.services.crypto_service import CryptoService
from server.services.source_connectors import ConnectorError, FeishuAdminConfigService, FeishuOAuthStateStore
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/collaboration", tags=["collaboration"])

SENSITIVE_OUTBOUND_PATTERNS = (
    re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+\S+"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|tenant[_-]?access[_-]?token)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(?:password|secret|token)\b\s*[:=]\s*\S+"),
    re.compile(r"\b(?:sk-[A-Za-z0-9][A-Za-z0-9_-]{16,}|byaan_[A-Za-z0-9_-]{16,})\b"),
)

TARGET_ACCESS_LOST_MARKERS = (
    "chat not found",
    "bot is not in the chat",
    "not in the chat",
    "chat unavailable",
    "message chat id invalid",
)

FEISHU_DELIVERY_TARGET_TYPES = {"group", "topic_group", "p2p"}
FEISHU_OAUTH_BASE_URL = "https://open.feishu.cn/open-apis/authen/v1/authorize"


def _safe_bad_request(prefix: str, exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{prefix}: {safe_feishu_error_message(exc)}")


def _contains_sensitive_outbound_content(text: str) -> bool:
    return any(pattern.search(text) for pattern in SENSITIVE_OUTBOUND_PATTERNS)


def _delivery_target_access_lost(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in TARGET_ACCESS_LOST_MARKERS)


def _feishu_delivery_target_type_for_chat(selected_chat: dict, root_id: str | None) -> str:
    if selected_chat.get("chat_type") == "p2p":
        return "p2p"
    if root_id:
        return "topic_group"
    return "group"


def _validate_feishu_delivery_target_shape(
    *,
    selected_chat: dict,
    root_id: str | None,
    requested_target_type: str | None,
) -> tuple[str, str | None]:
    requested = (requested_target_type or "").strip() or None
    if requested and requested not in FEISHU_DELIVERY_TARGET_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Feishu delivery target_type. Use group, topic_group, or p2p.",
        )
    expected = _feishu_delivery_target_type_for_chat(selected_chat, root_id)
    if requested and requested != expected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Feishu delivery target_type must be {expected} for the selected chat/root_id.",
        )
    if expected == "p2p" and root_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feishu private-chat delivery targets cannot include root_id.",
        )
    return expected, None if expected == "p2p" else root_id


def _missing_feishu_callback_message_fields(normalized_event) -> list[str]:
    missing = []
    if not normalized_event.message_id:
        missing.append("message_id")
    if not normalized_event.chat_id:
        missing.append("chat_id")
    if not normalized_event.sender_external_id:
        missing.append("sender_external_id")
    return missing


def _feishu_callback_audit_fields(payload: dict) -> tuple[str | None, str | None]:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    chat_id = event.get("chat_id") or message.get("chat_id")
    operator_id = event.get("operator_id") if isinstance(event.get("operator_id"), dict) else {}
    sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
    sender_id = sender.get("sender_id") if isinstance(sender.get("sender_id"), dict) else {}
    external_user_id = (
        operator_id.get("open_id")
        or operator_id.get("user_id")
        or sender_id.get("open_id")
        or sender_id.get("user_id")
        or event.get("open_id")
        or event.get("user_id")
    )
    return (str(chat_id) if chat_id else None, str(external_user_id) if external_user_id else None)


def _collaboration_oauth_error(error: Exception) -> HTTPException:
    message = safe_feishu_error_message(error)
    if isinstance(error, ConnectorError):
        code = status.HTTP_400_BAD_REQUEST if error.code in {"admin_config_required", "invalid_state"} else status.HTTP_422_UNPROCESSABLE_ENTITY
        return HTTPException(status_code=code, detail=message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


async def _mark_feishu_callback_url_verified(session: AsyncSession, installation: CollaborationInstallation) -> None:
    config = dict(installation.config_json or {})
    callback = dict(config.get("callback") or {})
    callback["url_verification"] = "verified"
    callback["last_url_verification_at"] = datetime.now().isoformat()
    config["callback"] = callback
    installation.config_json = config
    await session.commit()


async def _mark_delivery_target_needs_rebind(
    session: AsyncSession,
    target: CollaborationDeliveryTarget,
    exc: Exception,
) -> None:
    config = dict(target.config_json or {})
    config.update(
        {
            "is_enabled": False,
            "status": "needs_rebind",
            "last_error": safe_feishu_error_message(exc),
            "last_failed_at": datetime.now().isoformat(),
        }
    )
    target.config_json = config
    target.is_verified = False
    await session.commit()


async def _mark_delivery_target_not_visible(
    session: AsyncSession,
    target: CollaborationDeliveryTarget,
    *,
    message: str,
) -> None:
    config = dict(target.config_json or {})
    config.update(
        {
            "is_enabled": False,
            "status": "needs_rebind",
            "last_error": safe_feishu_error_message(message),
            "last_failed_at": datetime.now().isoformat(),
        }
    )
    target.config_json = config
    target.is_verified = False
    await session.commit()


async def _mark_needs_reauth_if_required(
    session: AsyncSession,
    installation: CollaborationInstallation | None,
    exc: Exception,
) -> None:
    if installation and feishu_error_requires_reauth(exc):
        installation.health_status = "needs_reauth"
        installation.health_error = safe_feishu_error_message(exc)
        installation.is_active = False
        await session.commit()


def _external_identity_payload(identity: ExternalIdentity, user: User | None = None) -> dict:
    mapped_user = None
    if user:
        mapped_user = {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
        }
    return {
        "id": str(identity.id),
        "external_user_id": identity.external_user_id,
        "union_id": identity.union_id,
        "status": identity.status,
        "user_id": str(identity.user_id) if identity.user_id else None,
        "byaan_user_id": str(identity.byaan_user_id) if identity.byaan_user_id else None,
        "mapped_user": mapped_user,
        "last_seen_at": identity.last_seen_at.isoformat() if identity.last_seen_at else None,
    }


def _delivery_target_payload(target: CollaborationDeliveryTarget) -> dict:
    config = target.config_json or {}
    return {
        "id": str(target.id),
        "target_type": target.target_type,
        "chat_id": target.external_target_id,
        "root_id": target.external_root_id,
        "display_name": target.display_name,
        "is_verified": target.is_verified,
        "is_enabled": CollaborationDeliveryTargetRepository.is_enabled(target),
        "created_at": target.created_at.isoformat() if target.created_at else None,
        "updated_at": target.updated_at.isoformat() if target.updated_at else None,
        "source": config.get("source"),
        "status": config.get("status") or ("enabled" if CollaborationDeliveryTargetRepository.is_enabled(target) else "unbound"),
        "last_error": safe_feishu_error_message(config.get("last_error")) if config.get("last_error") else None,
        "last_failed_at": config.get("last_failed_at"),
        "authorized_by_target_id": config.get("authorized_by_target_id"),
    }


async def _process_verified_feishu_callback_event(
    installation_id: UUID,
    payload: dict,
    *,
    preaccepted_event_log_id: UUID | None = None,
) -> None:
    async with AsyncSessionFactory() as callback_session:
        installation = await CollaborationInstallationRepository(callback_session).get(installation_id)
        if not installation or not installation.is_active or installation.platform != "feishu":
            if preaccepted_event_log_id:
                repo = CollaborationEventRepository(callback_session)
                event_log = await repo.get(preaccepted_event_log_id)
                if event_log:
                    await repo.mark(
                        event_log,
                        "inactive",
                        error_message="Feishu installation became inactive before background callback dispatch.",
                    )
            return
        try:
            result = await process_feishu_event(
                callback_session,
                installation,
                payload,
                preaccepted_event_log_id=preaccepted_event_log_id,
            )
            logger.info(
                "Processed signed Feishu callback event for installation %s with status %s",
                installation_id,
                result.get("status"),
            )
        except Exception as exc:
            safe_error = safe_feishu_error_message(exc)
            logger.error(
                "Failed signed Feishu callback event for installation %s: %s",
                installation_id,
                safe_error,
            )
            await callback_session.rollback()
            if preaccepted_event_log_id:
                repo = CollaborationEventRepository(callback_session)
                event_log = await repo.get(preaccepted_event_log_id)
                if event_log:
                    if event_log.attempt_count == 0:
                        await repo.mark(event_log, "processing")
                    await repo.mark(event_log, "failed_terminal", error_message=safe_error)


async def _get_feishu_installation_for_tenant(
    session: AsyncSession,
    installation_id: UUID,
    tenant_id: UUID,
):
    installation = await CollaborationInstallationRepository(session).get(installation_id)
    if not installation or installation.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found")
    if installation.platform != "feishu":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Identity mapping is only implemented for Feishu")
    return installation


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feishu not configured")
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
            app_id=payload.app_id.strip() if payload.app_id else None,
            app_secret=payload.app_secret,
            connection_mode=payload.connection_mode,
            default_llm_connection_id=payload.default_llm_connection_id,
            installed_by=auth.user_id,
            verification_token=payload.verification_token,
            encrypt_key=payload.encrypt_key,
        )
    except Exception as exc:
        logger.warning(f"Failed to configure Feishu installation: {safe_feishu_error_message(exc)}")
        raise _safe_bad_request("Feishu probe failed", exc)
    return success_response(
        data=await CollaborationInstallationService.masked_installation(installation),
        message="Feishu installation configured",
    )


@router.post("/installations/feishu/oauth/start")
async def start_feishu_collaboration_oauth(
    payload: FeishuOAuthStartRequest,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        config = await FeishuAdminConfigService.load_config(session=session)
        if not config:
            raise ConnectorError("Feishu application is not configured", code="admin_config_required", permanent=True)
        redirect_uri = str(config.get("redirect_uri") or FeishuAdminConfigService.generated_redirect_uri() or "").strip()
        if not redirect_uri:
            raise ConnectorError("Feishu OAuth redirect URI is not configured", code="admin_config_required", permanent=True)
        if payload.default_llm_connection_id:
            llm_connection = (
                await session.execute(
                    select(LLMConnection).where(
                        LLMConnection.id == payload.default_llm_connection_id,
                        LLMConnection.tenant_id == auth.tenant_id,
                    )
                )
            ).scalar_one_or_none()
            if not llm_connection:
                raise ValueError("Default LLM connection must belong to the current tenant")
        state = FeishuOAuthStateStore.create(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            redirect_uri=redirect_uri,
            purpose="collaboration_installation",
            metadata={
                "default_llm_connection_id": str(payload.default_llm_connection_id)
                if payload.default_llm_connection_id
                else None
            },
        )
        params = {"app_id": config["app_id"], "redirect_uri": redirect_uri, "state": state}
        authorization_url = f"{FEISHU_OAUTH_BASE_URL}?{urlencode(params)}"
    except Exception as exc:
        logger.warning("Failed to start Feishu collaboration OAuth: %s", safe_feishu_error_message(exc))
        raise _collaboration_oauth_error(exc)
    return success_response(
        data={
            "authorization_url": authorization_url,
            "state": state,
            "redirect_uri": redirect_uri,
            "qr_payload": authorization_url,
            "poll_url": f"/api/collaboration/installations/feishu/oauth/result?state={state}",
        },
        message="Started Feishu collaboration OAuth",
    )


@router.get("/installations/feishu/oauth/result")
async def get_feishu_collaboration_oauth_result(
    state: str,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
):
    result = FeishuOAuthStateStore.get_result(state)
    if not result:
        return success_response(data={"status": "pending"}, message="Feishu collaboration OAuth pending")
    if result.get("tenant_id") != str(auth.tenant_id) or result.get("user_id") != str(auth.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feishu OAuth result not found")
    return success_response(
        data={
            "status": result.get("status"),
            "installation": result.get("installation"),
            "external_identity": result.get("external_identity"),
            "error": safe_feishu_error_message(result.get("error")) if result.get("error") else None,
        },
        message="Feishu collaboration OAuth result retrieved",
    )


@router.post("/installations/feishu/oauth/result")
async def get_feishu_collaboration_oauth_result_post(
    payload: FeishuOAuthResultRequest,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
):
    return await get_feishu_collaboration_oauth_result(state=payload.state, auth=auth)


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
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
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
        installation.health_status = "needs_reauth" if feishu_error_requires_reauth(exc) else "failed"
        installation.health_error = safe_feishu_error_message(exc)
        if feishu_error_requires_reauth(exc):
            installation.is_active = False
        await session.commit()
        raise _safe_bad_request("Feishu probe failed", exc)
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
    try:
        data = await CollaborationInstallationService.connect_feishu(session, installation_id)
    except Exception as exc:
        raise _safe_bad_request("Feishu connect failed", exc)
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
    in_memory_health = feishu_ws_manager.health(installation_id)
    lease = await CollaborationLeaseRepository(session).get(installation_id)
    data = {
        "id": str(installation.id),
        "platform": installation.platform,
        "connection_mode": installation.connection_mode,
        "is_active": installation.is_active,
        "health_status": installation.health_status,
        "admin_state": CollaborationInstallationService.admin_state(installation),
        "health_error": safe_feishu_error_message(installation.health_error) if installation.health_error else None,
        "tenant_token_expires_at": (installation.config_json or {}).get("tenant_token_expires_at"),
        "callback": (installation.config_json or {}).get("callback", {}),
        "event_subscription": feishu_event_subscription_payload(installation.config_json),
        "last_connected_at": installation.last_connected_at.isoformat() if installation.last_connected_at else None,
        "last_event_at": installation.last_event_at.isoformat() if installation.last_event_at else None,
        "reconnect_count": installation.reconnect_count,
        "owner_id": in_memory_health.owner_id if in_memory_health else (lease.owner_id if lease else None),
        "lease_expires_at": lease.expires_at.isoformat() if lease else None,
    }
    return success_response(data=data, message="Collaboration health retrieved")


@router.get("/installations/{installation_id}/events")
async def list_installation_events(
    installation_id: UUID,
    limit: int = 10,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    installation = await CollaborationInstallationRepository(session).get(installation_id)
    if not installation or installation.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found")
    events = await CollaborationEventRepository(session).list_recent_for_installation(installation_id, limit=limit)
    run_ids = {event.run_id for event in events if event.run_id}
    response_refs_by_run_id = {}
    if run_ids:
        refs = (
            await session.execute(
                select(CollaborationResponseRef)
                .where(CollaborationResponseRef.run_id.in_(run_ids))
                .order_by(CollaborationResponseRef.created_at.desc(), CollaborationResponseRef.id.desc())
            )
        ).scalars()
        for ref in refs:
            response_refs_by_run_id.setdefault(ref.run_id, ref)
    return success_response(
        data={
            "items": [
                {
                    "id": str(event.id),
                    "event_id": event.external_event_id,
                    "event_type": event.event_type,
                    "chat_id": event.external_chat_id,
                    "sender_id": event.external_user_id,
                    "conversation_id": str(event.conversation_id) if event.conversation_id else None,
                    "notebook_id": str(event.notebook_id) if event.notebook_id else None,
                    "run_id": event.run_id,
                    "status": event.processing_status,
                    "attempt_count": event.attempt_count,
                    "response_ref": (
                        {
                            "message_id": response_refs_by_run_id[event.run_id].platform_message_id,
                            "status": response_refs_by_run_id[event.run_id].status,
                            "sequence": response_refs_by_run_id[event.run_id].sequence,
                        }
                        if event.run_id and event.run_id in response_refs_by_run_id
                        else None
                    ),
                    "error": safe_feishu_error_message(event.error_message) if event.error_message else None,
                    "created_at": event.created_at.isoformat() if event.created_at else None,
                    "updated_at": event.updated_at.isoformat() if event.updated_at else None,
                }
                for event in events
            ]
        },
        message="Collaboration events retrieved",
    )


@router.get("/installations/{installation_id}/feishu/identities")
async def list_feishu_external_identities(
    installation_id: UUID,
    limit: int = 50,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    await _get_feishu_installation_for_tenant(session, installation_id, auth.tenant_id)
    safe_limit = max(1, min(limit, 100))
    result = await session.execute(
        select(ExternalIdentity)
        .where(ExternalIdentity.installation_id == installation_id)
        .order_by(ExternalIdentity.last_seen_at.desc(), ExternalIdentity.id.desc())
        .limit(safe_limit)
    )
    identities = list(result.scalars().all())
    mapped_user_ids = {identity.byaan_user_id or identity.user_id for identity in identities}
    mapped_user_ids.discard(None)
    users_by_id: dict[UUID, User] = {}
    if mapped_user_ids:
        users = await session.execute(select(User).where(User.id.in_(mapped_user_ids)))
        users_by_id = {user.id: user for user in users.scalars().all()}
    return success_response(
        data={
            "items": [
                _external_identity_payload(identity, users_by_id.get(identity.byaan_user_id or identity.user_id))
                for identity in identities
            ]
        },
        message="Feishu external identities retrieved",
    )


@router.post("/installations/{installation_id}/feishu/identities/{identity_id}/mapping")
async def map_feishu_external_identity(
    installation_id: UUID,
    identity_id: UUID,
    payload: ExternalIdentityMappingRequest,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    await _get_feishu_installation_for_tenant(session, installation_id, auth.tenant_id)
    identity_result = await session.execute(
        select(ExternalIdentity)
        .where(ExternalIdentity.id == identity_id)
        .where(ExternalIdentity.installation_id == installation_id)
    )
    identity = identity_result.scalar_one_or_none()
    if not identity or identity.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External identity not found")

    member_result = await session.execute(
        select(User)
        .join(TenantMember, TenantMember.user_id == User.id)
        .where(User.id == payload.user_id)
        .where(TenantMember.tenant_id == auth.tenant_id)
    )
    mapped_user = member_result.scalar_one_or_none()
    if not mapped_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapped user must be a member of this tenant")

    identity.user_id = mapped_user.id
    identity.byaan_user_id = mapped_user.id
    identity.status = "linked"
    await session.commit()
    await session.refresh(identity)
    return success_response(
        data=_external_identity_payload(identity, mapped_user),
        message="Feishu external identity mapped",
    )


@router.delete("/installations/{installation_id}/feishu/identities/{identity_id}/mapping")
async def unmap_feishu_external_identity(
    installation_id: UUID,
    identity_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    await _get_feishu_installation_for_tenant(session, installation_id, auth.tenant_id)
    identity_result = await session.execute(
        select(ExternalIdentity)
        .where(ExternalIdentity.id == identity_id)
        .where(ExternalIdentity.installation_id == installation_id)
    )
    identity = identity_result.scalar_one_or_none()
    if not identity or identity.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External identity not found")

    identity.user_id = None
    identity.byaan_user_id = None
    identity.status = "seen"
    await session.commit()
    await session.refresh(identity)
    return success_response(
        data=_external_identity_payload(identity),
        message="Feishu external identity unmapped",
    )


@router.get("/installations/{installation_id}/feishu/chats")
async def list_feishu_chats(
    installation_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    installation = await CollaborationInstallationRepository(session).get(installation_id)
    if not installation or installation.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found")
    if installation.platform != "feishu":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chat list is only implemented for Feishu")
    try:
        chats = await CollaborationInstallationService.list_feishu_chats(session, installation_id)
    except Exception as exc:
        await _mark_needs_reauth_if_required(session, installation, exc)
        raise _safe_bad_request("Feishu chat list failed", exc)
    return success_response(data={"items": chats}, message="Feishu chats retrieved")


@router.get("/installations/{installation_id}/feishu/delivery-targets")
async def list_feishu_delivery_targets(
    installation_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    await _get_feishu_installation_for_tenant(session, installation_id, auth.tenant_id)
    targets = await CollaborationDeliveryTargetRepository(session).list_for_installation(installation_id)
    return success_response(
        data={"items": [_delivery_target_payload(target) for target in targets]},
        message="Feishu delivery targets retrieved",
    )


@router.post("/installations/{installation_id}/feishu/delivery-targets")
async def bind_feishu_delivery_target(
    installation_id: UUID,
    payload: FeishuDeliveryTargetBindRequest,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    installation = await _get_feishu_installation_for_tenant(session, installation_id, auth.tenant_id)
    credentials = await CryptoService.decrypt_config(installation.credentials_encrypted, session)
    client = FeishuApiClient(credentials["app_id"], credentials["app_secret"])
    try:
        visible_chats = await client.list_chats()
    except Exception as exc:
        await _mark_needs_reauth_if_required(session, installation, exc)
        raise _safe_bad_request("Feishu chat list failed", exc)
    selected_chat = next((chat for chat in visible_chats if chat.get("chat_id") == payload.chat_id), None)
    if not selected_chat:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected chat is not visible to the Feishu bot. Load the chat list and choose a visible chat.",
        )
    target_type, external_root_id = _validate_feishu_delivery_target_shape(
        selected_chat=selected_chat,
        root_id=payload.root_id,
        requested_target_type=payload.target_type,
    )
    target = await CollaborationDeliveryTargetRepository(session).get_or_create(
        installation_id=installation.id,
        target_type=target_type,
        external_target_id=payload.chat_id,
        external_root_id=external_root_id,
        display_name=payload.display_name or selected_chat.get("name") or "Feishu chat",
        is_verified=True,
    )
    config = dict(target.config_json or {})
    config.update(
        {
            "is_enabled": True,
            "source": "admin_binding",
            "authorized_by": str(auth.user_id),
            "authorized_at": datetime.now().isoformat(),
            "chat_type": selected_chat.get("chat_type"),
        }
    )
    target.config_json = config
    target.is_verified = True
    target.display_name = payload.display_name or selected_chat.get("name") or target.display_name
    await session.commit()
    await session.refresh(target)
    return success_response(data=_delivery_target_payload(target), message="Feishu delivery target bound")


@router.post("/installations/{installation_id}/feishu/delivery-targets/{target_id}/pause")
async def pause_feishu_delivery_target(
    installation_id: UUID,
    target_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    await _get_feishu_installation_for_tenant(session, installation_id, auth.tenant_id)
    target = await CollaborationDeliveryTargetRepository(session).get(target_id)
    if not target or target.installation_id != installation_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery target not found")
    updated = await CollaborationDeliveryTargetRepository(session).pause(target)
    return success_response(data=_delivery_target_payload(updated), message="Feishu delivery target paused")


@router.post("/installations/{installation_id}/feishu/delivery-targets/{target_id}/resume")
async def resume_feishu_delivery_target(
    installation_id: UUID,
    target_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    installation = await _get_feishu_installation_for_tenant(session, installation_id, auth.tenant_id)
    target = await CollaborationDeliveryTargetRepository(session).get(target_id)
    if not target or target.installation_id != installation_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery target not found")
    credentials = await CryptoService.decrypt_config(installation.credentials_encrypted, session)
    client = FeishuApiClient(credentials["app_id"], credentials["app_secret"])
    try:
        visible_chats = await client.list_chats()
    except Exception as exc:
        await _mark_needs_reauth_if_required(session, installation, exc)
        raise _safe_bad_request("Feishu chat list failed", exc)
    selected_chat = next((chat for chat in visible_chats if chat.get("chat_id") == target.external_target_id), None)
    if not selected_chat:
        config = dict(target.config_json or {})
        config["is_enabled"] = False
        config["status"] = "needs_rebind"
        config["last_failed_at"] = datetime.now().isoformat()
        target.config_json = config
        target.is_verified = False
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected chat is not visible to the Feishu bot. Load the chat list and choose a visible chat.",
        )
    updated = await CollaborationDeliveryTargetRepository(session).resume(target)
    return success_response(data=_delivery_target_payload(updated), message="Feishu delivery target resumed")


@router.delete("/installations/{installation_id}/feishu/delivery-targets/{target_id}")
async def unbind_feishu_delivery_target(
    installation_id: UUID,
    target_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    await _get_feishu_installation_for_tenant(session, installation_id, auth.tenant_id)
    target = await CollaborationDeliveryTargetRepository(session).get(target_id)
    if not target or target.installation_id != installation_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery target not found")
    updated = await CollaborationDeliveryTargetRepository(session).unbind(target)
    return success_response(data=_delivery_target_payload(updated), message="Feishu delivery target unbound")


@router.post("/installations/{installation_id}/test-message")
async def send_test_message(
    installation_id: UUID,
    payload: TestMessageRequest,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
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
        visible_chats = await client.list_chats()
    except Exception as exc:
        await _mark_needs_reauth_if_required(session, installation, exc)
        raise _safe_bad_request("Feishu chat list failed", exc)
    selected_chat = next((chat for chat in visible_chats if chat.get("chat_id") == payload.chat_id), None)
    if not selected_chat:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected chat is not visible to the Feishu bot. Load the chat list and choose a visible chat.",
        )
    target_type, external_root_id = _validate_feishu_delivery_target_shape(
        selected_chat=selected_chat,
        root_id=payload.root_id,
        requested_target_type=None,
    )
    try:
        result = await client.send_text_message(
            receive_id_type="chat_id",
            receive_id=payload.chat_id,
            text=payload.text,
            root_id=external_root_id,
        )
        await CollaborationDeliveryTargetRepository(session).get_or_create(
            installation_id=installation.id,
            target_type=target_type,
            external_target_id=payload.chat_id,
            external_root_id=external_root_id,
            display_name=selected_chat.get("name") or "Admin-selected Feishu test chat",
            is_verified=True,
        )
        target = await CollaborationDeliveryTargetRepository(session).find(
            installation_id=installation.id,
            target_type=target_type,
            external_target_id=payload.chat_id,
            external_root_id=external_root_id,
        )
        if target:
            config = dict(target.config_json or {})
            config.update(
                {
                    "is_enabled": True,
                    "source": "test_message",
                    "authorized_by": str(auth.user_id),
                    "authorized_at": datetime.now().isoformat(),
                    "chat_type": selected_chat.get("chat_type"),
                }
            )
            target.config_json = config
            target.is_verified = True
            await session.commit()
    except Exception as exc:
        await _mark_needs_reauth_if_required(session, installation, exc)
        raise _safe_bad_request("Feishu test message failed", exc)
    return success_response(data=result, message="Feishu test message sent")


@router.post("/installations/{installation_id}/feishu/outbound-message")
async def send_feishu_outbound_message(
    installation_id: UUID,
    payload: FeishuOutboundMessageRequest,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    installation = await _get_feishu_installation_for_tenant(session, installation_id, auth.tenant_id)
    if not payload.confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Explicit confirmation is required")
    target = await CollaborationDeliveryTargetRepository(session).get(payload.delivery_target_id)
    if not target or target.installation_id != installation.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery target not found")
    if not CollaborationDeliveryTargetRepository.is_enabled(target):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Delivery target is not enabled")
    if _contains_sensitive_outbound_content(payload.text):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Outbound message contains sensitive content; remove credentials or secrets before sending.",
        )

    installation_db_id = installation.id
    installation_credentials_encrypted = installation.credentials_encrypted
    credentials = await CryptoService.decrypt_config(installation_credentials_encrypted, session)
    client = FeishuApiClient(credentials["app_id"], credentials["app_secret"])
    try:
        visible_chats = await client.list_chats()
    except Exception as exc:
        await _mark_needs_reauth_if_required(session, installation, exc)
        raise _safe_bad_request("Feishu chat list failed", exc)
    selected_chat = next((chat for chat in visible_chats if chat.get("chat_id") == target.external_target_id), None)
    if not selected_chat:
        await _mark_delivery_target_not_visible(
            session,
            target,
            message="Selected chat is not visible to the Feishu bot. Load the chat list and choose a visible chat.",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected chat is not visible to the Feishu bot. Load the chat list and choose a visible chat.",
        )
    expected_type, expected_root_id = _validate_feishu_delivery_target_shape(
        selected_chat=selected_chat,
        root_id=target.external_root_id,
        requested_target_type=target.target_type,
    )
    if expected_type != target.target_type or expected_root_id != target.external_root_id:
        await _mark_delivery_target_not_visible(
            session,
            target,
            message="Feishu delivery target no longer matches the visible chat metadata.",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feishu delivery target no longer matches the visible chat metadata. Rebind the target before sending.",
        )
    target_external_id = target.external_target_id
    target_root_id = target.external_root_id
    target_type = target.target_type
    target_display_name = target.display_name
    auth_user_id = str(auth.user_id)
    idempotency_hash = hashlib.sha256(payload.idempotency_key.encode("utf-8")).hexdigest()
    run_id = f"feishu-outbound:{installation_db_id}:{idempotency_hash}"
    existing = await CollaborationResponseRefRepository(session).get_by_run_id(run_id)
    if existing:
        return success_response(
            data={
                "idempotent": True,
                "message_id": existing.platform_message_id,
                "run_id": existing.run_id,
            },
            message="Feishu outbound message already sent",
        )

    event_log, duplicate = await CollaborationEventRepository(session).record_received(
        installation_id=installation_db_id,
        platform="feishu",
        external_event_id=f"outbound:{idempotency_hash}",
        event_type="delivery",
        external_chat_id=target_external_id,
        external_user_id=auth_user_id,
    )
    if duplicate:
        existing = await CollaborationResponseRefRepository(session).get_by_run_id(run_id)
        if existing:
            return success_response(
                data={
                    "idempotent": True,
                    "message_id": existing.platform_message_id,
                    "run_id": run_id,
                },
                message="Feishu outbound message already accepted",
            )
        if event_log.processing_status != "failed_terminal":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Feishu outbound message with this idempotency key is already accepted but has no delivery reference yet",
            )
        event_log.error_message = None
        event_log.run_id = None
        event_log.conversation_id = None
        event_log.notebook_id = None
        await session.commit()
        await session.refresh(event_log)
    await CollaborationEventRepository(session).mark(event_log, "processing")

    try:
        sent = await client.send_text_message(
            receive_id_type="chat_id",
            receive_id=target_external_id,
            text=payload.text,
            root_id=target_root_id,
            request_uuid=f"feishu-outbound-{idempotency_hash}",
        )
    except Exception as exc:
        await _mark_needs_reauth_if_required(session, installation, exc)
        if _delivery_target_access_lost(exc):
            await _mark_delivery_target_needs_rebind(session, target, exc)
        await CollaborationEventRepository(session).mark(
            event_log,
            "failed_terminal",
            error_message=safe_feishu_error_message(exc),
        )
        raise _safe_bad_request("Feishu outbound message failed", exc)

    message_id = (
        sent.get("message_id")
        or sent.get("message", {}).get("message_id")
        or sent.get("data", {}).get("message_id")
        or ""
    )
    # Outbound sends are audited through response refs without creating a Notebook conversation.
    convo_result = await session.execute(
        select(CollaborationConversation)
        .where(CollaborationConversation.installation_id == installation_db_id)
        .where(CollaborationConversation.external_chat_id == target_external_id)
        .where(CollaborationConversation.normalized_root_id == normalize_root_id(target_root_id))
    )
    convo = convo_result.scalar_one_or_none()
    if convo is None:
        convo = CollaborationConversation(
            installation_id=installation_db_id,
            external_chat_id=target_external_id,
            external_root_id=target_root_id,
            normalized_root_id=normalize_root_id(target_root_id),
            external_user_id=auth_user_id,
            chat_type=target_type,
            title=target_display_name,
            bot_owned=True,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
    response_ref = await CollaborationResponseRefRepository(session).create(
        run_id=run_id,
        conversation_id=convo.id,
        platform_message_id=str(message_id),
        status="completed",
    )
    await CollaborationEventRepository(session).mark(
        event_log,
        "completed",
        conversation_id=convo.id,
        notebook_id=convo.notebook_id,
        run_id=response_ref.run_id,
    )
    return success_response(
        data={"idempotent": False, "message_id": message_id, "run_id": run_id},
        message="Feishu outbound message sent",
    )


@router.post("/feishu/callback/{installation_public_id}")
async def feishu_callback(
    installation_public_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_async_session),
):
    installation = await CollaborationInstallationRepository(session).get_by_public_id(installation_public_id)
    if not installation or installation.platform != "feishu":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Installation not found")
    credentials = await CryptoService.decrypt_config(installation.credentials_encrypted, session)
    raw_body = await request.body()
    verifier = FeishuCallbackVerifier(
        verification_token=credentials.get("verification_token"),
        encrypt_key=credentials.get("encrypt_key"),
    )
    try:
        callback = verifier.verify_and_decode(raw_body=raw_body, headers=request.headers)
    except FeishuCallbackVerificationError as exc:
        logger.warning("Rejected Feishu callback for installation %s: %s", installation.id, safe_callback_error(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Feishu callback")

    if callback.is_url_verification:
        await _mark_feishu_callback_url_verified(session, installation)
        return {"challenge": callback.challenge}
    if callback.event_type != "im.message.receive_v1":
        external_chat_id, external_user_id = _feishu_callback_audit_fields(callback.payload)
        event_log, duplicate = await CollaborationEventRepository(session).record_received(
            installation_id=installation.id,
            platform="feishu",
            external_event_id=callback.event_id or f"callback:{hashlib.sha256(raw_body).hexdigest()}",
            event_type=callback.event_type or "unknown",
            external_chat_id=external_chat_id,
            external_user_id=external_user_id,
        )
        if not duplicate:
            await CollaborationEventRepository(session).mark(
                event_log,
                "ignored_event_type",
                error_message=f"Feishu callback event type {callback.event_type or 'unknown'} is not handled.",
            )
        return {"code": 0}
    normalized_event = normalize_feishu_message_event(
        callback.payload,
        installation_id=installation.id,
        bot_external_id=installation.bot_external_id,
    )
    event_log, duplicate = await CollaborationEventRepository(session).record_received(
        installation_id=installation.id,
        platform="feishu",
        external_event_id=normalized_event.event_id,
        event_type=normalized_event.event_type.value,
        external_chat_id=normalized_event.chat_id,
        external_user_id=normalized_event.sender_external_id,
    )
    if duplicate:
        return {"code": 0}
    if not installation.is_active:
        await CollaborationEventRepository(session).mark(
            event_log,
            "inactive",
            error_message="Feishu installation is inactive; callback event acknowledged without dispatch.",
        )
        return {"code": 0}
    missing_fields = _missing_feishu_callback_message_fields(normalized_event)
    if missing_fields:
        repo = CollaborationEventRepository(session)
        await repo.mark(event_log, "processing")
        await repo.mark(
            event_log,
            "failed_terminal",
            error_message=f"Malformed Feishu message callback: missing {', '.join(missing_fields)}",
        )
        return {"code": 0}
    background_tasks.add_task(
        _process_verified_feishu_callback_event,
        installation.id,
        callback.payload,
        preaccepted_event_log_id=event_log.id,
    )
    return {"code": 0}
