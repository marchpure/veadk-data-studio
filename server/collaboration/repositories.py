from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from server.collaboration.models import (
    NORMALIZED_ROOT_NONE,
    CollaborationConversation,
    CollaborationDeliveryTarget,
    CollaborationEventLog,
    CollaborationInstallation,
    CollaborationLease,
    CollaborationResponseRef,
)


def normalize_root_id(root_id: str | None) -> str:
    root = (root_id or "").strip()
    return root or NORMALIZED_ROOT_NONE


class CollaborationInstallationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, installation_id: UUID) -> CollaborationInstallation | None:
        result = await self._session.execute(
            select(CollaborationInstallation)
            .options(selectinload(CollaborationInstallation.default_llm_connection))
            .where(CollaborationInstallation.id == installation_id)
        )
        return result.scalar_one_or_none()

    async def get_by_public_id(self, public_id: str) -> CollaborationInstallation | None:
        result = await self._session.execute(
            select(CollaborationInstallation).where(CollaborationInstallation.public_id == public_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tenant_platform(self, tenant_id: UUID, platform: str) -> CollaborationInstallation | None:
        result = await self._session.execute(
            select(CollaborationInstallation)
            .options(selectinload(CollaborationInstallation.default_llm_connection))
            .where(CollaborationInstallation.tenant_id == tenant_id)
            .where(CollaborationInstallation.platform == platform)
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(self, tenant_id: UUID) -> list[CollaborationInstallation]:
        result = await self._session.execute(
            select(CollaborationInstallation)
            .where(CollaborationInstallation.tenant_id == tenant_id)
            .order_by(CollaborationInstallation.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_active_by_platform(self, platform: str) -> list[CollaborationInstallation]:
        result = await self._session.execute(
            select(CollaborationInstallation)
            .where(CollaborationInstallation.platform == platform)
            .where(CollaborationInstallation.is_active.is_(True))
        )
        return list(result.scalars().all())

    async def create(self, **values) -> CollaborationInstallation:
        installation = CollaborationInstallation(**values)
        self._session.add(installation)
        await self._session.commit()
        await self._session.refresh(installation)
        return installation

    async def update(self, installation: CollaborationInstallation, **updates) -> CollaborationInstallation:
        for key, value in updates.items():
            if hasattr(installation, key) and key not in {"id", "tenant_id", "created_at", "public_id"}:
                setattr(installation, key, value)
        await self._session.commit()
        await self._session.refresh(installation)
        return installation


class CollaborationConversationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_external_key(
        self,
        installation_id: UUID,
        external_chat_id: str,
        external_root_id: str | None,
    ) -> CollaborationConversation | None:
        result = await self._session.execute(
            select(CollaborationConversation)
            .where(CollaborationConversation.installation_id == installation_id)
            .where(CollaborationConversation.external_chat_id == external_chat_id)
            .where(CollaborationConversation.normalized_root_id == normalize_root_id(external_root_id))
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        *,
        installation_id: UUID,
        external_chat_id: str,
        external_root_id: str | None,
        external_user_id: str | None,
        chat_type: str,
        title: str | None = None,
        bot_owned: bool = False,
    ) -> CollaborationConversation:
        conversation = await self.get_by_external_key(installation_id, external_chat_id, external_root_id)
        if conversation is None:
            conversation = CollaborationConversation(
                installation_id=installation_id,
                external_chat_id=external_chat_id,
                external_root_id=external_root_id,
                normalized_root_id=normalize_root_id(external_root_id),
                external_user_id=external_user_id,
                chat_type=chat_type,
                title=title,
                bot_owned=bot_owned,
            )
            self._session.add(conversation)
            try:
                await self._session.commit()
            except IntegrityError:
                await self._session.rollback()
                existing = await self.get_by_external_key(installation_id, external_chat_id, external_root_id)
                if existing is None:
                    raise
                conversation = existing
            else:
                await self._session.refresh(conversation)
        else:
            if title and not conversation.title:
                conversation.title = title
            if external_user_id and not conversation.external_user_id:
                conversation.external_user_id = external_user_id
            conversation.last_activity_at = datetime.now()
            await self._session.commit()
            await self._session.refresh(conversation)
        return conversation


class CollaborationEventRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def record_received(
        self,
        *,
        installation_id: UUID,
        platform: str,
        external_event_id: str,
        event_type: str,
        external_chat_id: str | None,
        external_user_id: str | None,
    ) -> tuple[CollaborationEventLog, bool]:
        event = CollaborationEventLog(
            installation_id=installation_id,
            platform=platform,
            external_event_id=external_event_id,
            event_type=event_type,
            external_chat_id=external_chat_id,
            external_user_id=external_user_id,
            processing_status="received",
        )
        self._session.add(event)
        try:
            await self._session.commit()
            await self._session.refresh(event)
            return event, False
        except IntegrityError:
            await self._session.rollback()
            result = await self._session.execute(
                select(CollaborationEventLog)
                .where(CollaborationEventLog.installation_id == installation_id)
                .where(CollaborationEventLog.external_event_id == external_event_id)
            )
            existing = result.scalar_one()
            return existing, True

    async def mark(self, event: CollaborationEventLog, status: str, error_message: str | None = None) -> None:
        event.processing_status = status
        event.error_message = error_message
        if status == "processing":
            event.attempt_count += 1
        await self._session.commit()


class CollaborationDeliveryTargetRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_or_create(
        self,
        *,
        installation_id: UUID,
        target_type: str,
        external_target_id: str,
        external_root_id: str | None = None,
        display_name: str | None = None,
        is_verified: bool = False,
    ) -> CollaborationDeliveryTarget:
        normalized_root_id = normalize_root_id(external_root_id)
        result = await self._session.execute(
            select(CollaborationDeliveryTarget)
            .where(CollaborationDeliveryTarget.installation_id == installation_id)
            .where(CollaborationDeliveryTarget.target_type == target_type)
            .where(CollaborationDeliveryTarget.external_target_id == external_target_id)
            .where(CollaborationDeliveryTarget.normalized_root_id == normalized_root_id)
        )
        target = result.scalar_one_or_none()
        if target:
            return target
        target = CollaborationDeliveryTarget(
            installation_id=installation_id,
            target_type=target_type,
            external_target_id=external_target_id,
            external_root_id=external_root_id,
            normalized_root_id=normalized_root_id,
            display_name=display_name,
            is_verified=is_verified,
        )
        self._session.add(target)
        await self._session.commit()
        await self._session.refresh(target)
        return target


class CollaborationResponseRefRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        *,
        run_id: str,
        conversation_id: UUID,
        platform_message_id: str,
        platform_card_id: str | None = None,
        sequence: int = 0,
        status: str = "running",
    ) -> CollaborationResponseRef:
        ref = CollaborationResponseRef(
            run_id=run_id,
            conversation_id=conversation_id,
            platform_message_id=platform_message_id,
            platform_card_id=platform_card_id,
            sequence=sequence,
            status=status,
        )
        self._session.add(ref)
        await self._session.commit()
        await self._session.refresh(ref)
        return ref

    async def update_by_message(
        self,
        *,
        conversation_id: UUID,
        platform_message_id: str,
        run_id: str,
        next_platform_message_id: str | None = None,
        platform_card_id: str | None = None,
        status: str,
        sequence: int | None = None,
    ) -> CollaborationResponseRef | None:
        result = await self._session.execute(
            select(CollaborationResponseRef)
            .where(CollaborationResponseRef.conversation_id == conversation_id)
            .where(CollaborationResponseRef.platform_message_id == platform_message_id)
            .order_by(CollaborationResponseRef.created_at.desc())
        )
        ref = result.scalars().first()
        if not ref:
            return None

        ref.run_id = run_id
        if next_platform_message_id:
            ref.platform_message_id = next_platform_message_id
        if platform_card_id is not None:
            ref.platform_card_id = platform_card_id
        ref.status = status
        if sequence is not None:
            ref.sequence = sequence
        await self._session.commit()
        await self._session.refresh(ref)
        return ref


class CollaborationLeaseRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def acquire(self, installation_id: UUID, owner_id: str, ttl_seconds: int = 60) -> bool:
        now = datetime.now()
        expires_at = now + timedelta(seconds=ttl_seconds)
        result = await self._session.execute(
            select(CollaborationLease).where(CollaborationLease.installation_id == installation_id)
        )
        lease = result.scalar_one_or_none()
        if lease is None:
            self._session.add(
                CollaborationLease(installation_id=installation_id, owner_id=owner_id, expires_at=expires_at)
            )
            try:
                await self._session.commit()
                return True
            except IntegrityError:
                await self._session.rollback()
                return False
        if lease.owner_id == owner_id or lease.expires_at <= now:
            lease.owner_id = owner_id
            lease.expires_at = expires_at
            lease.heartbeat_at = now
            await self._session.commit()
            return True
        return False

    async def heartbeat(self, installation_id: UUID, owner_id: str, ttl_seconds: int = 60) -> bool:
        result = await self._session.execute(
            select(CollaborationLease).where(CollaborationLease.installation_id == installation_id)
        )
        lease = result.scalar_one_or_none()
        if lease is None or lease.owner_id != owner_id:
            return False
        now = datetime.now()
        lease.heartbeat_at = now
        lease.expires_at = now + timedelta(seconds=ttl_seconds)
        await self._session.commit()
        return True

    async def release(self, installation_id: UUID, owner_id: str) -> None:
        await self._session.execute(
            delete(CollaborationLease)
            .where(CollaborationLease.installation_id == installation_id)
            .where(CollaborationLease.owner_id == owner_id)
        )
        await self._session.commit()
