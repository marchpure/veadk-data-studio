from __future__ import annotations

import asyncio
import random
import socket
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from server.collaboration.feishu.client import feishu_error_requires_reauth, safe_feishu_error_message
from server.collaboration.feishu.event_processor import process_feishu_event
from server.collaboration.repositories import CollaborationInstallationRepository, CollaborationLeaseRepository
from server.db.session import AsyncSessionFactory
from server.services.crypto_service import CryptoService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

LEASE_TTL_SECONDS = 90
HEARTBEAT_INTERVAL_SECONDS = 20
MAX_RECONNECT_SLEEP_SECONDS = 30


class FeishuLeaseLost(RuntimeError):
    pass


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
    def __init__(
        self,
        *,
        owner_id: str | None = None,
        heartbeat_interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS,
        lease_ttl_seconds: int = LEASE_TTL_SECONDS,
    ) -> None:
        self.owner_id = owner_id or f"{socket.gethostname()}:{id(self)}"
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.lease_ttl_seconds = lease_ttl_seconds
        self._consumers: dict[UUID, _Consumer] = {}
        self._connect_locks: dict[UUID, threading.Lock] = {}
        self._guard = threading.Lock()

    def is_running(self, installation_id: UUID) -> bool:
        consumer = self._consumers.get(installation_id)
        return bool(consumer and consumer.thread and consumer.thread.is_alive() and not consumer.stop_event.is_set())

    def health(self, installation_id: UUID) -> FeishuWebSocketHealth | None:
        consumer = self._consumers.get(installation_id)
        return consumer.health if consumer else None

    def _connect_lock(self, installation_id: UUID) -> threading.Lock:
        with self._guard:
            lock = self._connect_locks.get(installation_id)
            if lock is None:
                lock = threading.Lock()
                self._connect_locks[installation_id] = lock
            return lock

    async def connect(self, installation_id: UUID) -> FeishuWebSocketHealth:
        lock = self._connect_lock(installation_id)
        await asyncio.to_thread(lock.acquire)
        try:
            return await self._connect_locked(installation_id)
        finally:
            lock.release()

    async def _connect_locked(self, installation_id: UUID) -> FeishuWebSocketHealth:
        if self.is_running(installation_id):
            health = self._consumers[installation_id].health
            if health:
                return health

        async with AsyncSessionFactory() as session:
            installation = await CollaborationInstallationRepository(session).get(installation_id)
            if not installation:
                raise ValueError(f"Feishu installation not found: {installation_id}")
            if installation.platform != "feishu" or installation.connection_mode != "websocket":
                raise ValueError("Only Feishu WebSocket installations can be connected")

            acquired = await CollaborationLeaseRepository(session).acquire(
                installation_id=installation_id,
                owner_id=self.owner_id,
                ttl_seconds=self.lease_ttl_seconds,
            )
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

            installation.is_active = True
            installation.health_status = "connecting"
            installation.health_error = None
            await session.commit()

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
        with self._guard:
            old_consumer = self._consumers.get(installation_id)
            if old_consumer:
                old_consumer.stop_event.set()
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
            if consumer.thread and consumer.thread.is_alive() and threading.current_thread() is not consumer.thread:
                await asyncio.to_thread(consumer.thread.join, 5)

        await self._release_and_mark_disconnected(installation_id)
        if consumer and consumer.health:
            consumer.health.status = "disconnected"
            consumer.health.last_error = None
            return consumer.health
        return FeishuWebSocketHealth(installation_id=installation_id, status="disconnected", owner_id=self.owner_id)

    async def shutdown(self) -> None:
        for installation_id in list(self._consumers.keys()):
            await self._stop_for_shutdown(installation_id)

    async def resume_active_installations(self) -> dict[str, int]:
        resumed = 0
        leased_elsewhere = 0
        failed = 0
        async with AsyncSessionFactory() as session:
            installations = await CollaborationInstallationRepository(session).list_active_by_platform_mode(
                "feishu", "websocket"
            )
            installation_ids = [installation.id for installation in installations]

        for installation_id in installation_ids:
            try:
                health = await self.connect(installation_id)
                if health.status == "leased_elsewhere":
                    leased_elsewhere += 1
                else:
                    resumed += 1
            except Exception as exc:
                failed += 1
                await self._mark_failed(installation_id, exc)
                logger.warning(
                    "Feishu WebSocket auto-resume failed for installation %s: %s",
                    installation_id,
                    safe_feishu_error_message(exc),
                )
        return {"resumed": resumed, "leased_elsewhere": leased_elsewhere, "failed": failed}

    def _run_consumer_thread(self, consumer: _Consumer) -> None:
        asyncio.run(self._run_consumer(consumer))

    async def _run_consumer(self, consumer: _Consumer) -> None:
        try:
            await self._consumer_loop(consumer)
        finally:
            await self._release_owned_lease(consumer.installation_id)
            with self._guard:
                if self._consumers.get(consumer.installation_id) is consumer:
                    self._consumers.pop(consumer.installation_id, None)

    async def _consumer_loop(self, consumer: _Consumer) -> None:
        while not consumer.stop_event.is_set():
            try:
                async with AsyncSessionFactory() as session:
                    heartbeat_ok = await CollaborationLeaseRepository(session).heartbeat(
                        consumer.installation_id,
                        consumer.owner_id,
                        ttl_seconds=self.lease_ttl_seconds,
                    )
                    if not heartbeat_ok:
                        if consumer.health:
                            consumer.health.status = "leased_elsewhere"
                            consumer.health.last_error = "Lost Feishu WebSocket lease."
                        await self._mark_installation_status(
                            consumer.installation_id,
                            status="leased_elsewhere",
                            error="Lost Feishu WebSocket lease.",
                        )
                        return

                    installation = await CollaborationInstallationRepository(session).get(consumer.installation_id)
                    if not installation or not installation.is_active or installation.connection_mode != "websocket":
                        return
                    installation.health_status = (
                        "connecting"
                        if not consumer.health or not consumer.health.last_connected_at
                        else "reconnecting"
                    )
                    installation.health_error = None
                    await session.commit()
                    credentials = await CryptoService.decrypt_config(installation.credentials_encrypted, session)

                await self._run_sdk_client(
                    app_id=credentials["app_id"],
                    app_secret=credentials["app_secret"],
                    on_event=lambda raw: self._dispatch_event(consumer.installation_id, raw),
                    stop_event=consumer.stop_event,
                    health=consumer.health,
                    on_connected=lambda: self._mark_connected(consumer),
                    on_reconnecting=lambda: self._mark_reconnecting(consumer),
                )
            except Exception as exc:
                if isinstance(exc, FeishuLeaseLost):
                    if consumer.health:
                        consumer.health.status = "leased_elsewhere"
                        consumer.health.last_error = safe_feishu_error_message(exc)
                    await self._mark_installation_status(
                        consumer.installation_id,
                        status="leased_elsewhere",
                        error=safe_feishu_error_message(exc),
                    )
                    return
                if consumer.stop_event.is_set():
                    break
                if feishu_error_requires_reauth(exc):
                    safe_error = safe_feishu_error_message(exc)
                    if consumer.health:
                        consumer.health.status = "needs_reauth"
                        consumer.health.last_error = safe_error
                    await self._mark_installation_status(
                        consumer.installation_id,
                        status="needs_reauth",
                        error=safe_error,
                        is_active=False,
                    )
                    return
                reconnect_count = self._increment_health_error(consumer, exc)
                await self._mark_installation_status(
                    consumer.installation_id,
                    status="reconnecting",
                    error=safe_feishu_error_message(exc),
                    reconnect_count=reconnect_count,
                )
                await self._sleep_before_reconnect(reconnect_count, consumer.stop_event)

    async def _sleep_before_reconnect(self, reconnect_count: int, stop_event: threading.Event) -> None:
        delay = min(MAX_RECONNECT_SLEEP_SECONDS, 2 ** min(reconnect_count, 5))
        delay += random.uniform(0, min(1.0, delay / 4))
        end = asyncio.get_running_loop().time() + delay
        while not stop_event.is_set() and asyncio.get_running_loop().time() < end:
            await asyncio.sleep(min(0.25, end - asyncio.get_running_loop().time()))

    def _increment_health_error(self, consumer: _Consumer, exc: Exception) -> int:
        if not consumer.health:
            return 1
        consumer.health.status = "reconnecting"
        consumer.health.reconnect_count += 1
        consumer.health.last_error = safe_feishu_error_message(exc)
        return consumer.health.reconnect_count

    async def _mark_connected(self, consumer: _Consumer) -> None:
        now = datetime.now()
        if consumer.health:
            consumer.health.status = "connected"
            consumer.health.last_connected_at = now
            consumer.health.last_error = None
        await self._mark_installation_status(
            consumer.installation_id,
            status="connected",
            error=None,
            last_connected_at=now,
            reconnect_count=consumer.health.reconnect_count if consumer.health else None,
        )

    async def _mark_reconnecting(self, consumer: _Consumer) -> None:
        reconnect_count = 0
        if consumer.health:
            consumer.health.status = "reconnecting"
            consumer.health.reconnect_count += 1
            reconnect_count = consumer.health.reconnect_count
        await self._mark_installation_status(
            consumer.installation_id,
            status="reconnecting",
            error=None,
            reconnect_count=reconnect_count,
        )

    async def _dispatch_event(self, installation_id: UUID, raw_event: dict | object) -> None:
        async with AsyncSessionFactory() as session:
            installation = await CollaborationInstallationRepository(session).get(installation_id)
            if not installation:
                return
            now = datetime.now()
            installation.last_event_at = now
            await session.commit()
            health = self.health(installation_id)
            if health:
                health.last_event_at = now
            try:
                await process_feishu_event(session, installation, raw_event)
            except Exception as exc:
                safe_error = safe_feishu_error_message(exc)
                logger.error("Failed to dispatch Feishu WebSocket event for installation %s: %s", installation_id, safe_error)
                installation.health_error = safe_error
                await session.commit()
                if health:
                    health.last_error = safe_error

    async def _mark_installation_status(
        self,
        installation_id: UUID,
        *,
        status: str,
        error: str | None,
        last_connected_at: datetime | None = None,
        reconnect_count: int | None = None,
        is_active: bool | None = None,
    ) -> None:
        async with AsyncSessionFactory() as session:
            installation = await CollaborationInstallationRepository(session).get(installation_id)
            if not installation:
                return
            installation.health_status = status
            installation.health_error = safe_feishu_error_message(error) if error else None
            if is_active is not None:
                installation.is_active = is_active
            if last_connected_at:
                installation.last_connected_at = last_connected_at
            if reconnect_count is not None:
                installation.reconnect_count = reconnect_count
            await session.commit()

    async def _mark_failed(self, installation_id: UUID, exc: Exception) -> None:
        await self._mark_installation_status(
            installation_id,
            status="failed",
            error=safe_feishu_error_message(exc),
        )

    async def _release_and_mark_disconnected(self, installation_id: UUID) -> None:
        async with AsyncSessionFactory() as session:
            await CollaborationLeaseRepository(session).release(installation_id, self.owner_id)
            installation = await CollaborationInstallationRepository(session).get(installation_id)
            if installation:
                installation.is_active = False
                installation.health_status = "disconnected"
                installation.health_error = None
                await session.commit()

    async def _stop_for_shutdown(self, installation_id: UUID) -> FeishuWebSocketHealth:
        consumer = self._consumers.get(installation_id)
        if consumer:
            consumer.stop_event.set()
            if consumer.health:
                consumer.health.stop_requested = True
                consumer.health.status = "configured"
            if consumer.thread and consumer.thread.is_alive() and threading.current_thread() is not consumer.thread:
                await asyncio.to_thread(consumer.thread.join, 5)

        async with AsyncSessionFactory() as session:
            await CollaborationLeaseRepository(session).release(installation_id, self.owner_id)
            installation = await CollaborationInstallationRepository(session).get(installation_id)
            if installation:
                installation.health_status = "configured"
                installation.health_error = None
                await session.commit()

        if consumer and consumer.health:
            consumer.health.status = "configured"
            consumer.health.last_error = None
            return consumer.health
        return FeishuWebSocketHealth(installation_id=installation_id, status="configured", owner_id=self.owner_id)

    async def _release_owned_lease(self, installation_id: UUID) -> None:
        async with AsyncSessionFactory() as session:
            await CollaborationLeaseRepository(session).release(installation_id, self.owner_id)

    async def _run_sdk_client(
        self,
        *,
        app_id: str,
        app_secret: str,
        on_event: Callable[[object], Awaitable[None]],
        stop_event: threading.Event,
        health: FeishuWebSocketHealth | None,
        on_connected: Callable[[], Awaitable[None]],
        on_reconnecting: Callable[[], Awaitable[None]],
    ) -> None:
        manager_loop = asyncio.get_running_loop()
        connected_event = threading.Event()
        start_exception: list[BaseException] = []

        def enqueue_event(raw: object) -> None:
            manager_loop.call_soon_threadsafe(lambda: asyncio.create_task(on_event(raw)))

        def schedule_reconnecting() -> None:
            manager_loop.call_soon_threadsafe(lambda: asyncio.create_task(on_reconnecting()))

        def start_client() -> None:
            sdk_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(sdk_loop)
            try:
                import lark_oapi as lark
                import lark_oapi.ws.client as ws_client
                from lark_oapi.core.enum import LogLevel
                from lark_oapi.event.dispatcher_handler import EventDispatcherHandler

                ws_client.loop = sdk_loop
                handler = EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(enqueue_event).build()
                client = lark.ws.Client(
                    app_id,
                    app_secret,
                    log_level=LogLevel.INFO,
                    event_handler=handler,
                    auto_reconnect=True,
                )
                client.on_reconnecting = schedule_reconnecting
                client.on_reconnected = lambda: manager_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(on_connected())
                )
                sdk_loop.run_until_complete(self._run_sdk_loop(client, stop_event, connected_event))
            except BaseException as exc:
                start_exception.append(exc)
                connected_event.set()
            finally:
                sdk_loop.close()

        thread = threading.Thread(target=start_client, daemon=True, name="feishu-sdk-client")
        thread.start()

        while not connected_event.is_set() and thread.is_alive() and not stop_event.is_set():
            await asyncio.sleep(0.05)
        if start_exception:
            raise start_exception[0]
        if connected_event.is_set() and thread.is_alive() and not stop_event.is_set():
            await on_connected()

        heartbeat_task = asyncio.create_task(self._heartbeat_until_stopped(health.installation_id if health else None, stop_event))
        stop_sdk = False
        try:
            while not stop_event.is_set() and thread.is_alive():
                if start_exception:
                    stop_sdk = True
                    raise start_exception[0]
                if heartbeat_task.done():
                    try:
                        heartbeat_task.result()
                    except Exception as exc:
                        if stop_event.is_set():
                            break
                        stop_sdk = True
                        raise exc
                await asyncio.sleep(0.5)
        finally:
            heartbeat_task.cancel()
            if not heartbeat_task.done():
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            if stop_sdk:
                stop_event.set()
            if thread.is_alive():
                await asyncio.to_thread(thread.join, 5)

    async def _run_sdk_loop(self, client: object, stop_event: threading.Event, connected_event: threading.Event) -> None:
        await client._connect()
        connected_event.set()
        ping_task = asyncio.create_task(client._ping_loop())
        try:
            while not stop_event.is_set():
                await asyncio.sleep(0.5)
        finally:
            ping_task.cancel()
            try:
                client._auto_reconnect = False
                await client._disconnect()
            except Exception:
                pass

    async def _heartbeat_until_stopped(self, installation_id: UUID | None, stop_event: threading.Event) -> None:
        if not installation_id:
            return
        while not stop_event.is_set():
            await asyncio.sleep(self.heartbeat_interval_seconds)
            if stop_event.is_set():
                return
            async with AsyncSessionFactory() as session:
                ok = await CollaborationLeaseRepository(session).heartbeat(
                    installation_id,
                    self.owner_id,
                    ttl_seconds=self.lease_ttl_seconds,
                )
                if not ok:
                    raise FeishuLeaseLost("Lost Feishu WebSocket lease.")


feishu_ws_manager = FeishuWebSocketManager()
