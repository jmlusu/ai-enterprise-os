"""Dashboard event bridge — EventBus fan-out to per-client asyncio queues.

ADR 0002 / ADR 0009: the dashboard's WebSocket endpoint is a subscriber of
the runtime EventBus. The bridge converts each published event into a JSON
envelope and pushes it onto an :class:`asyncio.Queue` owned by the connected
client. Reconnects use ``EventBus.replay()`` with ``?since=<iso8601>`` — there
is no custom message bus.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from ai_company.events import Event, EventBus, ReplayRequest

logger = logging.getLogger(__name__)

__all__ = ["DashboardEventBridge"]

_SUBSCRIBER_NAME = "dashboard-bridge"

#: How many live events the replay engine delivers to a reconnecting client.
_REPLAY_LIMIT = 1000


def _envelope(event: Event) -> dict[str, Any]:
    """JSON envelope sent over the wire for one runtime event."""
    return {"kind": "event", "event": event.model_dump(mode="json")}


def _safe_put(queue: asyncio.Queue[dict[str, Any]], envelope: dict[str, Any]) -> None:
    """Push an envelope to a client queue, dropping the oldest item when full."""
    try:
        queue.put_nowait(envelope)
    except asyncio.QueueFull:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            queue.put_nowait(envelope)
        except asyncio.QueueFull:  # pragma: no cover - defensive only
            pass


class DashboardEventBridge:
    """Fan-out of EventBus events to per-client asyncio queues.

    The bridge must be attached to the running event loop
    (``attach(loop)``) before clients subscribe; events are pushed
    thread-safely with ``loop.call_soon_threadsafe`` because the EventBus
    dispatches subscriber callbacks from worker threads.

    All client-queue mutations happen on the attached loop thread, so no
    additional locking is needed around the client registry.
    """

    def __init__(self, bus: EventBus, max_queue: int = 1000) -> None:
        self._bus = bus
        self._max_queue = max_queue
        self._clients: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscriber: Any | None = None

    @property
    def client_count(self) -> int:
        """Number of currently connected clients."""
        return len(self._clients)

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind the bridge to the event loop that owns the client queues."""
        if self._loop is not None and self._loop is not loop:
            raise RuntimeError(
                "DashboardEventBridge is already attached to another event loop"
            )
        self._loop = loop

    async def subscribe_client(
        self,
        client_id: str,
        since: datetime | None = None,
    ) -> asyncio.Queue[dict[str, Any]]:
        """Register a client and return its event queue.

        When ``since`` is given and the bus has persistence, matching
        historical events are replayed into the queue before live events
        flow. Clients deduplicate by ``event_id`` across the boundary: an
        event published while replay is running may arrive both replayed
        (it is persisted) and live.
        """
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._max_queue)
        self._clients[client_id] = queue
        self._ensure_subscriber()
        if since is not None:
            await self._replay_into(queue, since)
        return queue

    def unsubscribe_client(self, client_id: str) -> None:
        """Drop a client; its queue stops receiving new events."""

        def _remove() -> None:
            self._clients.pop(client_id, None)

        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(_remove)
            except RuntimeError:  # loop already closed during shutdown
                _remove()
        else:
            _remove()

    async def close(self) -> None:
        """Unsubscribe from the bus and drop all clients."""
        self._clients.clear()
        if self._subscriber is not None:
            try:
                self._bus.unsubscribe(self._subscriber.name)
            except Exception as exc:  # bridge teardown must never raise
                logger.debug("Event bridge unsubscribe failed: %s", exc)
            self._subscriber = None

    def _ensure_subscriber(self) -> None:
        """Register the bridge's live subscriber on the bus (once)."""
        if self._subscriber is None:
            self._subscriber = self._bus.subscribe(
                _SUBSCRIBER_NAME,
                self._on_event,
                description="Dashboard WebSocket live event feed",
            )

    def _on_event(self, event: Event) -> None:
        """EventBus subscriber callback (runs on a dispatcher thread)."""
        if self._loop is None:
            return
        envelope = _envelope(event)
        try:
            self._loop.call_soon_threadsafe(self._fanout, envelope)
        except RuntimeError:  # loop closed during shutdown
            pass

    def _fanout(self, envelope: dict[str, Any]) -> None:
        """Deliver one envelope to every connected client (loop thread)."""
        for queue in list(self._clients.values()):
            _safe_put(queue, envelope)

    async def _replay_into(
        self,
        queue: asyncio.Queue[dict[str, Any]],
        since: datetime,
    ) -> None:
        """Replay persisted events newer than ``since`` into a client queue."""
        if getattr(self._bus, "persistence", None) is None:
            return
        request = ReplayRequest(since=since, limit=_REPLAY_LIMIT)

        def _handler(event: Event) -> None:
            if self._loop is None:
                return
            try:
                self._loop.call_soon_threadsafe(_safe_put, queue, _envelope(event))
            except RuntimeError:
                pass

        # EventBus.replay is synchronous (blocks on the persistence read), so
        # run it off the event loop; the handler re-enters the loop thread.
        await asyncio.to_thread(self._bus.replay, request, _handler)
