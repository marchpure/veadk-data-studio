from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.collaboration.feishu.adapter import FeishuChannelAdapter
from server.collaboration.feishu.client import FeishuApiClient, feishu_error_requires_reauth, safe_feishu_error_message
from server.collaboration.feishu.subscription import feishu_event_subscription_payload
from server.collaboration.feishu.transport import feishu_ws_manager
from server.collaboration.models import ExternalIdentity
from server.collaboration.repositories import CollaborationDeliveryTargetRepository, CollaborationInstallationRepository
from server.models.llm_connections import LLMConnection
from server.services.crypto_service import CryptoService
from server.services.source_connectors import (
    ConnectorError,
    FeishuAdminConfigService,
    FeishuConnectorAdapter,
    FeishuOAuthStateStore,
)


class CollaborationInstallationService:
    @staticmethod
    def admin_state(installation) -> str:
        if not installation:
            return "not_installed"
        if installation.health_status == "needs_reauth":
            return "needs_reauth"
        if installation.health_status in {"connected", "connecting", "reconnecting", "leased_elsewhere", "failed"}:
            return installation.health_status
        if installation.is_active:
            return "installed"
        if installation.health_status == "disconnected":
            return "disconnected"
        if installation.default_llm_connection_id is None:
            return "admin_authorization_pending"
        return "installed"

    @staticmethod
    async def create_or_update_feishu(
        *,
        session: AsyncSession,
        tenant_id: UUID,
        app_id: str | None,
        app_secret: str | None,
        connection_mode: str = "websocket",
        default_llm_connection_id: UUID | None = None,
        installed_by: UUID | None = None,
        verification_token: str | None = None,
        encrypt_key: str | None = None,
    ):
        if connection_mode != "websocket":
            raise ValueError("Feishu Webhook mode is disabled until verification token, signature, encryption, and replay protection are implemented")
        if default_llm_connection_id:
            llm_connection = (
                await session.execute(
                    select(LLMConnection).where(
                        LLMConnection.id == default_llm_connection_id,
                        LLMConnection.tenant_id == tenant_id,
                    )
                )
            ).scalar_one_or_none()
            if not llm_connection:
                raise ValueError("Default LLM connection must belong to the current tenant")

        repo = CollaborationInstallationRepository(session)
        existing = await repo.get_by_tenant_platform(tenant_id, "feishu")
        admin_config = await FeishuAdminConfigService.load_config(session=session)
        resolved_app_id = (app_id or "").strip()
        resolved_app_secret = (app_secret or "").strip() or None

        if not resolved_app_id and admin_config:
            resolved_app_id = str(admin_config.get("app_id") or "").strip()
        if not resolved_app_secret and admin_config and (not existing or not app_secret):
            resolved_app_secret = str(admin_config.get("app_secret") or "").strip() or None

        if not resolved_app_id:
            raise ValueError("Feishu app is not configured. Ask an admin to configure the Byaan managed or BYOC Feishu app.")
        if not resolved_app_secret:
            if not existing:
                raise ValueError("Feishu app secret is not configured. Ask an admin to configure the Byaan managed or BYOC Feishu app.")
            existing_credentials = await CryptoService.decrypt_config(existing.credentials_encrypted, session)
            resolved_app_secret = existing_credentials["app_secret"]
        elif existing:
            existing_credentials = await CryptoService.decrypt_config(existing.credentials_encrypted, session)
        else:
            existing_credentials = {}

        verification_token = (verification_token or "").strip() or existing_credentials.get("verification_token")
        encrypt_key = (encrypt_key or "").strip() or existing_credentials.get("encrypt_key")

        client = FeishuApiClient(app_id=resolved_app_id, app_secret=resolved_app_secret)
        try:
            probe = await client.probe()
        except Exception as exc:
            if existing and feishu_error_requires_reauth(exc):
                existing.health_status = "needs_reauth"
                existing.health_error = safe_feishu_error_message(exc)
                await session.commit()
            raise
        credentials_encrypted = await CryptoService.encrypt_config(
            {
                "app_id": resolved_app_id,
                "app_secret": resolved_app_secret,
                "verification_token": verification_token,
                "encrypt_key": encrypt_key,
            },
            session,
        )
        callback_config = {
            "url_verification": "supported_when_token_and_encrypt_key_configured",
            "event_ingress": "signed_encrypted_only",
            "verification_token_configured": bool(verification_token),
            "encrypt_key_configured": bool(encrypt_key),
        }
        existing_config = dict(existing.config_json or {}) if existing else {}
        event_subscription = feishu_event_subscription_payload(existing_config)
        values = {
            "external_tenant_id": probe.get("external_tenant_id") or resolved_app_id,
            "external_tenant_name": probe.get("external_tenant_name"),
            "app_id": resolved_app_id,
            "credentials_encrypted": credentials_encrypted,
            "connection_mode": connection_mode,
            "default_llm_connection_id": default_llm_connection_id,
            "bot_external_id": probe.get("bot_external_id"),
            "is_active": bool(existing.is_active) if existing else False,
            "health_status": "configured",
            "health_error": None,
            "reconnect_count": existing.reconnect_count if existing else 0,
            "config_json": {
                "mode": connection_mode,
                "probe": {"bot": probe.get("bot", {})},
                "callback": callback_config,
                "event_subscription": event_subscription,
                "tenant_token_expires_at": probe.get("tenant_token_expires_at"),
                "required_scopes": [
                    "im:message",
                    "im:message:send_as_bot",
                    "im:chat",
                ],
                "data_use": "Only selected Feishu chat metadata and message text that explicitly triggers Byaan are processed for the current tenant.",
            },
            "installed_by": installed_by,
        }
        if existing:
            return await repo.update(existing, **values)
        return await repo.create(tenant_id=tenant_id, platform="feishu", **values)

    @staticmethod
    async def complete_feishu_oauth_callback(
        *,
        session: AsyncSession,
        code: str,
        state: str,
    ) -> dict:
        state_payload = FeishuOAuthStateStore.pop(state)
        if state_payload is None or state_payload.get("purpose") != "collaboration_installation":
            FeishuOAuthStateStore.set_result(
                state,
                {"status": "failed", "error": "Invalid or expired Feishu OAuth state"},
            )
            raise ConnectorError("Invalid or expired Feishu OAuth state", code="invalid_state", permanent=True)

        tenant_id = UUID(str(state_payload["tenant_id"]))
        user_id = UUID(str(state_payload["user_id"]))
        metadata = dict(state_payload.get("metadata") or {})
        default_llm_connection_id = (
            UUID(str(metadata["default_llm_connection_id"]))
            if metadata.get("default_llm_connection_id")
            else None
        )
        try:
            config = await FeishuAdminConfigService.load_config(session=session)
            if not config:
                raise ConnectorError("Feishu application is not configured", code="admin_config_required", permanent=True)
            adapter = FeishuConnectorAdapter()
            token = await adapter._exchange_code(config=config, code=code)
            access_token = str(token.get("access_token") or "")
            if not access_token:
                raise ConnectorError("Feishu OAuth response missing access_token", code="oauth_response_invalid")
            user_info = await adapter._get_user_info(access_token)
            external_user_id = (
                user_info.get("open_id")
                or user_info.get("user_id")
                or token.get("open_id")
                or token.get("user_id")
            )
            union_id = user_info.get("union_id") or token.get("union_id")
            installation = await CollaborationInstallationService.create_or_update_feishu(
                session=session,
                tenant_id=tenant_id,
                app_id=None,
                app_secret=None,
                connection_mode="websocket",
                default_llm_connection_id=default_llm_connection_id,
                installed_by=user_id,
            )
            if external_user_id:
                identity_result = await session.execute(
                    select(ExternalIdentity)
                    .where(ExternalIdentity.installation_id == installation.id)
                    .where(ExternalIdentity.external_user_id == external_user_id)
                )
                identity = identity_result.scalar_one_or_none()
                if identity is None:
                    identity = ExternalIdentity(
                        tenant_id=tenant_id,
                        platform="feishu",
                        installation_id=installation.id,
                        external_user_id=external_user_id,
                        union_id=union_id,
                        user_id=user_id,
                        byaan_user_id=user_id,
                        status="linked",
                    )
                    session.add(identity)
                else:
                    identity.union_id = identity.union_id or union_id
                    identity.user_id = user_id
                    identity.byaan_user_id = user_id
                    identity.status = "linked"
                    identity.last_seen_at = datetime.now()
                await session.commit()

            installation_payload = await CollaborationInstallationService.masked_installation(installation)
            external_identity = {
                "external_user_id": external_user_id,
                "union_id": union_id,
                "display_name": user_info.get("name") or user_info.get("en_name") or "Feishu user",
            }
            payload = {
                "status": "success",
                "installation": installation_payload,
                "external_identity": external_identity,
            }
            FeishuOAuthStateStore.set_result(
                state,
                {
                    **payload,
                    "tenant_id": str(tenant_id),
                    "user_id": str(user_id),
                },
            )
            return payload
        except Exception as exc:
            FeishuOAuthStateStore.set_result(
                state,
                {
                    "status": "failed",
                    "tenant_id": str(tenant_id),
                    "user_id": str(user_id),
                    "error": safe_feishu_error_message(exc),
                },
            )
            raise

    @staticmethod
    async def masked_installation(installation) -> dict:
        return {
            "id": str(installation.id),
            "platform": installation.platform,
            "external_tenant_id": installation.external_tenant_id,
            "external_tenant_name": installation.external_tenant_name,
            "app_id": installation.app_id,
            "connection_mode": installation.connection_mode,
            "default_llm_connection_id": str(installation.default_llm_connection_id)
            if installation.default_llm_connection_id
            else None,
            "bot_external_id": installation.bot_external_id,
            "is_active": installation.is_active,
            "health_status": installation.health_status,
            "admin_state": CollaborationInstallationService.admin_state(installation),
            "health_error": safe_feishu_error_message(installation.health_error) if installation.health_error else None,
            "callback": (installation.config_json or {}).get("callback", {}),
            "event_subscription": feishu_event_subscription_payload(installation.config_json),
            "required_scopes": (installation.config_json or {}).get("required_scopes", []),
            "data_use": (installation.config_json or {}).get("data_use"),
            "tenant_token_expires_at": (installation.config_json or {}).get("tenant_token_expires_at"),
            "last_connected_at": installation.last_connected_at.isoformat() if installation.last_connected_at else None,
            "last_event_at": installation.last_event_at.isoformat() if installation.last_event_at else None,
            "reconnect_count": installation.reconnect_count,
            "created_at": installation.created_at.isoformat() if installation.created_at else None,
            "updated_at": installation.updated_at.isoformat() if installation.updated_at else None,
        }

    @staticmethod
    async def probe_feishu(session: AsyncSession, installation_id: UUID) -> dict:
        installation = await CollaborationInstallationRepository(session).get(installation_id)
        if not installation:
            raise ValueError("Installation not found")
        try:
            return await FeishuChannelAdapter(session, installation).probe()
        except Exception as exc:
            if feishu_error_requires_reauth(exc):
                installation.health_status = "needs_reauth"
                installation.health_error = safe_feishu_error_message(exc)
                installation.is_active = False
                await session.commit()
            raise

    @staticmethod
    async def connect_feishu(session: AsyncSession, installation_id: UUID) -> dict:
        installation = await CollaborationInstallationRepository(session).get(installation_id)
        if not installation:
            raise ValueError("Installation not found")
        if installation.platform != "feishu" or installation.connection_mode != "websocket":
            raise ValueError("Only Feishu WebSocket installations can be connected")
        try:
            credentials = await CryptoService.decrypt_config(installation.credentials_encrypted, session)
            probe = await FeishuApiClient(credentials["app_id"], credentials["app_secret"]).probe()
        except Exception as exc:
            installation.health_status = "needs_reauth" if feishu_error_requires_reauth(exc) else "failed"
            installation.health_error = safe_feishu_error_message(exc)
            if feishu_error_requires_reauth(exc):
                installation.is_active = False
            await session.commit()
            raise
        config = dict(installation.config_json or {})
        config["tenant_token_expires_at"] = probe.get("tenant_token_expires_at")
        config["probe"] = {"bot": probe.get("bot", {})}
        installation.config_json = config
        if probe.get("bot_external_id"):
            installation.bot_external_id = probe.get("bot_external_id")
        installation.is_active = True
        installation.health_status = "connecting"
        installation.health_error = None
        await session.commit()
        health = await feishu_ws_manager.connect(installation_id)
        installation.health_status = health.status
        installation.health_error = safe_feishu_error_message(health.last_error) if health.last_error else None
        installation.reconnect_count = health.reconnect_count
        if health.last_connected_at:
            installation.last_connected_at = health.last_connected_at
        await session.commit()
        return health.__dict__

    @staticmethod
    async def disconnect_feishu(session: AsyncSession, installation_id: UUID) -> dict:
        if feishu_ws_manager.is_running(installation_id):
            health = await feishu_ws_manager.disconnect(installation_id)
        else:
            health = {
                "installation_id": installation_id,
                "status": "disconnected",
                "owner_id": feishu_ws_manager.owner_id,
            }
        installation = await CollaborationInstallationRepository(session).get(installation_id)
        if installation:
            await CollaborationInstallationService._revoke_feishu_delivery_targets(session, installation_id)
            config = dict(installation.config_json or {})
            config["disconnect_policy"] = {
                "delivery_targets": "revoked",
                "history": "preserved",
                "notebooks": "preserved",
            }
            installation.config_json = config
            installation.is_active = False
            installation.health_status = "disconnected"
            installation.health_error = None
            await session.commit()
        return health if isinstance(health, dict) else health.__dict__

    @staticmethod
    async def _revoke_feishu_delivery_targets(session: AsyncSession, installation_id: UUID) -> None:
        targets = await CollaborationDeliveryTargetRepository(session).list_for_installation(installation_id, limit=200)
        for target in targets:
            config = dict(target.config_json or {})
            config["is_enabled"] = False
            config["status"] = "revoked_on_disconnect"
            config["disconnected_at"] = datetime.now().isoformat()
            target.config_json = config
            target.is_verified = False

    @staticmethod
    async def list_feishu_chats(session: AsyncSession, installation_id: UUID) -> list[dict]:
        installation = await CollaborationInstallationRepository(session).get(installation_id)
        if not installation:
            raise ValueError("Installation not found")
        credentials = await CryptoService.decrypt_config(installation.credentials_encrypted, session)
        client = FeishuApiClient(credentials["app_id"], credentials["app_secret"])
        return await client.list_chats()
