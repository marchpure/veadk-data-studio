from __future__ import annotations

import asyncio
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from server.collaboration.feishu.event_processor import process_feishu_event
from server.collaboration.repositories import CollaborationInstallationRepository, CollaborationLeaseRepository
from server.db.session import AsyncSessionFactory
from server.services.crypto_service import CryptoService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


@dataclass
class FeishuWebSocketHealth:
    installation_id: UUID
    status: str = "disconnected"
    owner_id: str | None = None
    started_at: datetime | None = None
    last_connected_at: datetime | None = None
    last_event_at: datetime | None = None
    reconnect_count: int = 0
    last_error: str | None = None
    stop_requested: bool = False


@dataclass
class _Consumer:
    installation_id: UUID
    owner_id: str
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    health: FeishuWebSocketHealth | None = None


class FeishuWebSocketManager:
    def __init__(self, *, owner_id: str | None = None) -> None:
        self.owner_id = owner_id or f"{socket.gethostname()}:{id(self)}"
        self._consumers: dict[UUID, _Consumer] = {}

    def is_running(self, installation_id: UUID) -> bool:
        consumer = self._consumers.get(installation_id)
        return bool(consumer and consumer.thread and consumer.thread.is_alive())

    def health(self, installation_id: UUID) -> FeishuWebSocketHealth | None:
        consumer = self._consumers.get(installation_id)
        return consumer.health if consumer else None

    async def connect(self, installation_id: UUID) -> FeishuWebSocketHealth:
        if self.is_running(installation_id):
            return self._consumers[installation_id].health or FeishuWebSocketHealth(
                installation_id=installation_id, status="connected", owner_id=self.owner_id
            )

        async with AsyncSessionFactory() as session:
            acquired = await CollaborationLeaseRepository(session).acquire(
                installation_id=installation_id,
                owner_id=self.owner_id,
                ttl_seconds=90,
            )
            installation = await CollaborationInstallationRepository(session).get(installation_id)
            if not installation:
                raise ValueError(f"Feishu installation not found: {installation_id}")
            if not acquired:
                health = FeishuWebSocketHealth(
                    installation_id=installation_id,
                    status="leased_elsewhere",
                    owner_id=self.owner_id,
                    last_error="Another instance owns the Feishu WebSocket lease.",
                )
                installation.health_status = "leased_elsewhere"
                installation.health_error = health.last_error
                await session.commit()
                return health

        consumer = _Consumer(installation_id=installation_id, owner_id=self.owner_id)
        consumer.health = FeishuWebSocketHealth(
            installation_id=installation_id,
            status="connecting",
            owner_id=self.owner_id,
            started_at=datetime.now(),
        )
        thread = threading.Thread(
            target=self._run_consumer_thread,
            args=(consumer,),
            name=f"feishu-ws-{str(installation_id)[:8]}",
            daemon=True,
        )
        consumer.thread = thread
        self._consumers[installation_id] = consumer
        thread.start()
        return consumer.health

    async def disconnect(self, installation_id: UUID) -> FeishuWebSocketHealth:
        consumer = self._consumers.get(installation_id)
        if consumer:
            consumer.stop_event.set()
            if consumer.health:
                consumer.health.stop_requested = True
                consumer.health.status = "disconnecting"
        async with AsyncSessionFactory() as session:
            await CollaborationLeaseRepository(session).release(installation_id, self.owner_id)
            installation = await CollaborationInstallationRepository(session).get(installation_id)
            if installation:
                installation.health_status = "disconnected"
                installation.health_error = None
                await session.commit()
        if consumer and consumer.health:
            consumer.health.status = "disconnected"
            return consumer.health
        return FeishuWebSocketHealth(installation_id=installation_id, status="disconnected", owner_id=self.owner_id)

    async def shutdown(self) -> None:
        for installation_id in list(self._consumers.keys()):
            await self.disconnect(installation_id)

    def _run_consumer_thread(self, consumer: _Consumer) -> None:
        asyncio.run(self._run_consumer(consumer))

    async def _run_consumer(self, consumer: _Consumer) -> None:
        while not consumer.stop_event.is_set():
            try:
                async with AsyncSessionFactory() as session:
                    heartbeat_ok = await CollaborationLeaseRepository(session).heartbeat(
                        consumer.installation_id,
                        consumer.owner_id,
                        ttl_seconds=90,
                    )
                    if not heartbeat_ok:
                        if consumer.health:
                            consumer.health.status = "lease_lost"
                            consumer.health.last_error = "Lost Feishu WebSocket lease."
                        return
                    installation = await CollaborationInstallationRepository(session).get(consumer.installation_id)
                    if not installation or not installation.is_active:
                        return
                    installation.health_status = "connecting"
                    await session.commit()
                    credentials = await CryptoService.decrypt_config(installation.credentials_encrypted, session)
                    installation.health_status = "connected"
                    installation.health_error = None
                    installation.last_connected_at = datetime.now()
                    await session.commit()

                async def schedule_event(raw: object) -> None:
                    asyncio.create_task(self._dispatch_event(consumer.installation_id, raw))

                await self._run_sdk_client(
                    app_id=credentials["app_id"],
                    app_secret=credentials["app_secret"],
                    on_event=schedule_event,
                    stop_event=consumer.stop_event,
                    health=consumer.health,
                )
            except Exception as exc:
                if consumer.health:
                    consumer.health.status = "reconnecting"
                    consumer.health.reconnect_count += 1
                    consumer.health.last_error = str(exc)
                async with AsyncSessionFactory() as session:
                    installation = await CollaborationInstallationRepository(session).get(consumer.installation_id)
                    if installation:
                        installation.health_status = "reconnecting"
                        installation.health_error = str(exc)
                        await session.commit()
                await asyncio.sleep(min(30, 2 ** min(consumer.health.reconnect_count if consumer.health else 1, 5)))

        await self.disconnect(consumer.installation_id)

    async def _dispatch_event(self, installation_id: UUID, raw_event: dict | object) -> None:
        async with AsyncSessionFactory() as session:
            installation = await CollaborationInstallationRepository(session).get(installation_id)
            if not installation:
                return
            await process_feishu_event(session, installation, raw_event)

    async def _run_sdk_client(
        self,
        *,
        app_id: str,
        app_secret: str,
        on_event: Callable[[object], object],
        stop_event: threading.Event,
        health: FeishuWebSocketHealth | None,
    ) -> None:
        """Run Feishu official SDK in a worker thread.

        The SDK client owns its own blocking event loop. We keep this method behind a
        narrow boundary so contract tests can replace it without importing the full SDK.
        """
        import lark_oapi as lark
        from lark_oapi.event.dispatcher_handler import EventDispatcherHandler

        loop = asyncio.get_running_loop()

        def enqueue_event(raw: object) -> None:
            loop.call_soon_threadsafe(lambda: asyncio.create_task(on_event(raw)))

        handler = EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(enqueue_event).build()
        client = lark.ws.Client(app_id, app_secret, event_handler=handler, auto_reconnect=True)

        if health:
            health.status = "connected"
            health.last_connected_at = datetime.now()

        def start_client() -> None:
            client.start()

        thread = threading.Thread(target=start_client, daemon=True)
        thread.start()
        while not stop_event.is_set() and thread.is_alive():
            await asyncio.sleep(1)
        if stop_event.is_set() and hasattr(client, "_disconnect"):
            try:
                await client._disconnect()
            except Exception:
                pass
        thread.join(timeout=5)


feishu_ws_manager = FeishuWebSocketManager()
