from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.collaboration.feishu.adapter import FeishuChannelAdapter
from server.collaboration.feishu.client import FeishuApiClient
from server.collaboration.feishu.transport import feishu_ws_manager
from server.collaboration.repositories import CollaborationInstallationRepository
from server.services.crypto_service import CryptoService


class CollaborationInstallationService:
    @staticmethod
    async def create_or_update_feishu(
        *,
        session: AsyncSession,
        tenant_id: UUID,
        app_id: str,
        app_secret: str | None,
        connection_mode: str = "websocket",
        default_llm_connection_id: UUID | None = None,
        installed_by: UUID | None = None,
    ):
        repo = CollaborationInstallationRepository(session)
        existing = await repo.get_by_tenant_platform(tenant_id, "feishu")
        if not app_secret:
            if not existing:
                raise ValueError("App Secret is required for first-time Feishu configuration")
            existing_credentials = await CryptoService.decrypt_config(existing.credentials_encrypted, session)
            app_secret = existing_credentials["app_secret"]

        client = FeishuApiClient(app_id=app_id, app_secret=app_secret)
        probe = await client.probe()
        credentials_encrypted = await CryptoService.encrypt_config(
            {"app_id": app_id, "app_secret": app_secret},
            session,
        )
        values = {
            "external_tenant_id": probe.get("external_tenant_id") or app_id,
            "external_tenant_name": probe.get("external_tenant_name"),
            "app_id": app_id,
            "credentials_encrypted": credentials_encrypted,
            "connection_mode": connection_mode,
            "default_llm_connection_id": default_llm_connection_id,
            "bot_external_id": probe.get("bot_external_id"),
            "is_active": True,
            "health_status": "configured",
            "health_error": None,
            "config_json": {"mode": connection_mode, "probe": {"bot": probe.get("bot", {})}},
            "installed_by": installed_by,
        }
        if existing:
            return await repo.update(existing, **values)
        return await repo.create(tenant_id=tenant_id, platform="feishu", **values)

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
            "health_error": installation.health_error,
            "last_connected_at": installation.last_connected_at.isoformat() if installation.last_connected_at else None,
            "last_event_at": installation.last_event_at.isoformat() if installation.last_event_at else None,
            "created_at": installation.created_at.isoformat() if installation.created_at else None,
            "updated_at": installation.updated_at.isoformat() if installation.updated_at else None,
        }

    @staticmethod
    async def probe_feishu(session: AsyncSession, installation_id: UUID) -> dict:
        installation = await CollaborationInstallationRepository(session).get(installation_id)
        if not installation:
            raise ValueError("Installation not found")
        return await FeishuChannelAdapter(session, installation).probe()

    @staticmethod
    async def connect_feishu(session: AsyncSession, installation_id: UUID) -> dict:
        installation = await CollaborationInstallationRepository(session).get(installation_id)
        if not installation:
            raise ValueError("Installation not found")
        health = await feishu_ws_manager.connect(installation_id)
        installation.health_status = health.status
        installation.health_error = health.last_error
        if health.status in {"connected", "connecting"}:
            installation.last_connected_at = datetime.now()
        await session.commit()
        return health.__dict__

    @staticmethod
    async def disconnect_feishu(session: AsyncSession, installation_id: UUID) -> dict:
        health = await feishu_ws_manager.disconnect(installation_id)
        installation = await CollaborationInstallationRepository(session).get(installation_id)
        if installation:
            installation.health_status = "disconnected"
            installation.health_error = None
            await session.commit()
        return health.__dict__
