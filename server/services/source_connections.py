from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.source_connections import SourceConnection
from server.models.source_resources import SourceResource
from server.schemas.source_connections import SourceConnectionCreate
from server.services.connector_catalog import get_connector_definition, list_connector_definitions
from server.services.crypto_service import CryptoService
from server.services.source_connectors import (
    ConnectorError,
    FeishuAdminConfigService,
    FeishuConnectorAdapter,
    ResourceListInput,
    SourceConnectorAdapter,
    get_connector_adapter,
    redact_credentials,
)
from server.services.source_redaction import redact_sensitive_text


class SourceConnectionService:
    def list_connector_definitions(self) -> list[dict[str, Any]]:
        return list_connector_definitions()

    async def create_connection(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        user_id: UUID | None,
        payload: SourceConnectionCreate,
        adapter: SourceConnectorAdapter | None = None,
    ) -> SourceConnection:
        definition = get_connector_definition(payload.provider)
        if definition is None or definition.availability != "available":
            raise ValueError(f"Connector {payload.provider} is not available")
        if payload.provider == "feishu" and payload.auth_mode != "oauth":
            raise ValueError("Feishu source connections must be created through OAuth")
        adapter = adapter or get_connector_adapter(payload.provider)
        capabilities = dict(payload.capabilities)
        external_account_id = payload.external_account_id
        if payload.test_connection:
            try:
                test_result = await adapter.test_connection(payload.credentials)
            except ConnectorError as exc:
                raise ConnectorError(
                    redact_sensitive_text(str(exc)) or "Source connection authorization failed",
                    code=exc.code,
                    permanent=exc.permanent,
                ) from exc
            capabilities["test_connection"] = {"status": "passed", **test_result}
            external_account_id = external_account_id or test_result.get("account_id") or test_result.get("external_account_id")
        encrypted = await CryptoService.encrypt_config(payload.credentials, session)
        connection = SourceConnection(
            tenant_id=tenant_id,
            provider=payload.provider,
            auth_mode=payload.auth_mode,
            encrypted_credentials=encrypted,
            external_account_id=external_account_id,
            display_name=payload.display_name,
            status="connected",
            capabilities_json=capabilities,
            token_expires_at=self._parse_expires_at(payload.credentials.get("expires_at")),
            created_by=user_id,
        )
        session.add(connection)
        await session.commit()
        await session.refresh(connection)
        return connection

    async def list_connections(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        provider: str | None = None,
    ) -> list[SourceConnection]:
        stmt = select(SourceConnection).where(SourceConnection.tenant_id == tenant_id)
        if provider:
            stmt = stmt.where(SourceConnection.provider == provider)
        result = await session.execute(stmt.order_by(SourceConnection.updated_at.desc()))
        return list(result.scalars().all())

    async def get_connection(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        connection_id: str | UUID,
    ) -> SourceConnection | None:
        return await session.scalar(
            select(SourceConnection).where(SourceConnection.tenant_id == tenant_id, SourceConnection.id == connection_id)
        )

    async def delete_connection(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        connection_id: str | UUID,
    ) -> tuple[bool, int]:
        connection = await self.get_connection(session=session, tenant_id=tenant_id, connection_id=connection_id)
        if connection is None:
            return False, 0
        resource_count = int(
            await session.scalar(
                select(func.count(SourceResource.id)).where(
                    SourceResource.tenant_id == tenant_id,
                    SourceResource.source_connection_id == connection.id,
                )
            )
            or 0
        )
        connection.status = "disconnected"
        connection.encrypted_credentials = await CryptoService.encrypt_config({"disconnected": True}, session)
        await session.commit()
        return True, resource_count

    async def refresh_connection(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        connection_id: str | UUID,
    ) -> SourceConnection:
        connection = await self.get_connection(session=session, tenant_id=tenant_id, connection_id=connection_id)
        if connection is None:
            raise ValueError("Source connection not found")
        if connection.provider != "feishu":
            return connection
        adapter = FeishuConnectorAdapter()
        await adapter.ensure_access_token(session=session, connection=connection)
        await session.refresh(connection)
        return connection

    async def list_resources(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        connection_id: str | UUID,
        scope: str,
        parent_token: str | None,
        resource_type: str | None,
        query: str | None,
        page_token: str | None,
        page_size: int,
        adapter: SourceConnectorAdapter | None = None,
    ) -> dict[str, Any]:
        connection = await self.get_connection(session=session, tenant_id=tenant_id, connection_id=connection_id)
        if connection is None:
            raise ValueError("Source connection not found")
        if connection.status in {"reauthorization_required", "authorization_required", "disconnected"}:
            return {
                "items": [],
                "next_page_token": None,
                "scope": scope,
                "connection_status": connection.status,
            }
        existing_result = await session.execute(
            select(SourceResource.external_id).where(
                SourceResource.tenant_id == tenant_id,
                SourceResource.source_connection_id == connection.id,
            )
        )
        already_added = frozenset(str(item) for item in existing_result.scalars().all() if item)
        adapter = adapter or get_connector_adapter(connection.provider)
        result = await adapter.list_resources(
            session=session,
            input=ResourceListInput(
                tenant_id=tenant_id,
                connection=connection,
                scope=scope,
                parent_token=parent_token,
                resource_type=resource_type,
                query=query,
                page_token=page_token,
                page_size=page_size,
                already_added_external_ids=already_added,
            ),
        )
        return {
            "items": [item.to_payload() for item in result.items],
            "next_page_token": result.next_page_token,
            "scope": scope,
            "connection_status": connection.status,
        }

    async def locate_resource_from_url(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        connection_id: str | UUID,
        url: str,
        adapter: FeishuConnectorAdapter | None = None,
    ) -> dict[str, Any]:
        connection = await self.get_connection(session=session, tenant_id=tenant_id, connection_id=connection_id)
        if connection is None:
            raise ValueError("Source connection not found")
        if connection.provider != "feishu":
            raise ValueError("Quick link location is only supported for Feishu connections")
        if connection.status in {"reauthorization_required", "authorization_required", "disconnected"}:
            return {
                "item": None,
                "connection_status": connection.status,
            }

        existing_result = await session.execute(
            select(SourceResource.external_id).where(
                SourceResource.tenant_id == tenant_id,
                SourceResource.source_connection_id == connection.id,
            )
        )
        already_added = frozenset(str(item) for item in existing_result.scalars().all() if item)
        adapter = adapter or FeishuConnectorAdapter()
        access_token = await adapter.ensure_access_token(session=session, connection=connection)
        item = await adapter.locate_resource_from_url(access_token=access_token, url=url, already_added=already_added)
        return {
            "item": item.to_payload(),
            "connection_status": connection.status,
        }

    async def feishu_status(self, *, session: AsyncSession, tenant_id: UUID, user_id: UUID) -> dict[str, Any]:
        admin = await FeishuAdminConfigService.status(session=session)
        connection = await session.scalar(
            select(SourceConnection).where(
                SourceConnection.tenant_id == tenant_id,
                SourceConnection.created_by == user_id,
                SourceConnection.provider == "feishu",
            )
        )
        return {
            "admin_config": admin,
            "connection": self.connection_payload(connection) if connection else None,
            "configured": admin.get("configured", False),
            "connected": bool(connection and connection.status == "connected"),
        }

    async def feishu_oauth_start(self, *, session: AsyncSession, tenant_id: UUID, user_id: UUID) -> dict[str, str]:
        adapter = FeishuConnectorAdapter()
        authorization_url, state = await adapter.create_authorization_url(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return {"authorization_url": authorization_url, "state": state}

    async def feishu_oauth_callback(self, *, session: AsyncSession, code: str, state: str) -> SourceConnection:
        adapter = FeishuConnectorAdapter()
        return await adapter.complete_oauth_callback(session=session, code=code, state=state)

    def connection_payload(self, connection: SourceConnection | None) -> dict[str, Any] | None:
        if connection is None:
            return None
        return {
            "id": connection.id,
            "provider": connection.provider,
            "auth_mode": connection.auth_mode,
            "external_account_id": connection.external_account_id,
            "display_name": connection.display_name,
            "status": connection.status,
            "capabilities": connection.capabilities_json,
            "token_expires_at": connection.token_expires_at,
            "created_by": connection.created_by,
            "created_at": connection.created_at,
            "updated_at": connection.updated_at,
        }

    async def decrypted_redacted_credentials(
        self,
        *,
        session: AsyncSession,
        connection: SourceConnection,
    ) -> dict[str, Any]:
        return redact_credentials(await CryptoService.decrypt_config(connection.encrypted_credentials, session))

    def _parse_expires_at(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                return None
        return None


def connector_error_to_value_error(error: ConnectorError) -> ValueError:
    return ValueError(f"{error.code}: {error}")
