"""Unit tests for the DashboardEventBridge (ADR 0002 / ADR 0009).

The bridge lives between the thread-based EventBus and per-client asyncio
queues, so tests run a real asyncio loop on a background thread and drive it
with ``asyncio.run_coroutine_threadsafe`` (no pytest-asyncio dependency).
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ai_company.events import EventBus, EventType
from ai_company.services.dashboard_events import DashboardEventBridge


def _run(
    coro: Coroutine[Any, Any, Any],
    loop: asyncio.AbstractEventLoop,
    timeout: float = 5.0,
) -> Any:
    """Run a coroutine on the background loop thread and return its result."""
    return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=timeout)


@pytest.fixture()
def bus(tmp_path: Path) -> EventBus:
    instance = EventBus(
        storage_path=str(tmp_path / "events.jsonl"),
        dead_letter_path=str(tmp_path / "dead_letter.jsonl"),
    )
    instance.start()
    yield instance
    instance.stop()


@pytest.fixture()
def loop() -> Any:
    instance = asyncio.new_event_loop()
    thread = threading.Thread(target=instance.run_forever, daemon=True)
    thread.start()
    yield instance
    instance.call_soon_threadsafe(instance.stop)
    thread.join(timeout=5)
    instance.close()


def test_live_event_delivery(bus: EventBus, loop: asyncio.AbstractEventLoop) -> None:
    bridge = DashboardEventBridge(bus)
    bridge.attach(loop)
    queue = _run(bridge.subscribe_client("c1"), loop)

    bus.publish_event(
        event_type=EventType.SYSTEM_HEALTH_CHECK,
        payload={"ok": True},
        source="test",
    )

    envelope = _run(queue.get(), loop)
    assert envelope["kind"] == "event"
    assert envelope["event"]["metadata"]["event_type"] == "system.health_check"
    assert envelope["event"]["payload"] == {"ok": True}
    assert bridge.client_count == 1

    bridge.unsubscribe_client("c1")
    _run(bridge.close(), loop)


def test_replay_since_then_live(bus: EventBus, loop: asyncio.AbstractEventLoop) -> None:
    bus.publish_event(EventType.MEMORY_SAVED, payload={"k": 1}, source="test")
    time.sleep(0.01)
    mark = datetime.now(UTC)
    time.sleep(0.01)
    bus.publish_event(EventType.MEMORY_SAVED, payload={"k": 2}, source="test")

    bridge = DashboardEventBridge(bus)
    bridge.attach(loop)
    queue = _run(bridge.subscribe_client("c1", since=mark), loop)

    # Historical event replayed (k=2 only; k=1 predates `mark`).
    replayed = _run(queue.get(), loop)
    assert replayed["event"]["payload"] == {"k": 2}

    # Live events continue to stream after replay.
    bus.publish_event(EventType.MEMORY_SAVED, payload={"k": 3}, source="test")
    live = _run(queue.get(), loop)
    assert live["event"]["payload"] == {"k": 3}

    bridge.unsubscribe_client("c1")
    _run(bridge.close(), loop)


def test_replay_skipped_without_persistence(
    tmp_path: Path, loop: asyncio.AbstractEventLoop
) -> None:
    bus = EventBus(
        storage_path=str(tmp_path / "events.jsonl"),
        dead_letter_path=str(tmp_path / "dead_letter.jsonl"),
        enable_persistence=False,
    )
    bus.start()
    try:
        bridge = DashboardEventBridge(bus)
        bridge.attach(loop)
        queue = _run(bridge.subscribe_client("c1", since=datetime.now(UTC)), loop)

        bus.publish_event(EventType.MEMORY_SAVED, payload={"k": 1}, source="test")
        envelope = _run(queue.get(), loop)
        assert envelope["event"]["payload"] == {"k": 1}
    finally:
        bus.stop()


def test_unsubscribe_missing_client_is_noop(
    bus: EventBus, loop: asyncio.AbstractEventLoop
) -> None:
    bridge = DashboardEventBridge(bus)
    bridge.attach(loop)
    bridge.unsubscribe_client("never-existed")  # must not raise
    _run(bridge.close(), loop)


def test_attach_to_second_loop_raises(
    bus: EventBus, loop: asyncio.AbstractEventLoop
) -> None:
    bridge = DashboardEventBridge(bus)
    bridge.attach(loop)
    other_loop = asyncio.new_event_loop()
    try:
        with pytest.raises(RuntimeError):
            bridge.attach(other_loop)
    finally:
        other_loop.close()
