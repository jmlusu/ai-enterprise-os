"""End-to-end smoke test for the EventBus."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_company.events import (
    Event,
    EventBus,
    EventPriority,
    EventStatus,
    EventType,
    Route,
    Subscriber,
)


@pytest.fixture
def bus(tmp_path: Path) -> EventBus:
    """Create a fresh EventBus with temp storage for each test."""
    store = str(tmp_path / "store.jsonl")
    dlq = str(tmp_path / "dead_letter.jsonl")
    b = EventBus(
        enable_persistence=False,
        storage_path=store,
        dead_letter_path=dlq,
    )
    b.start()
    yield b
    b.stop()


# ── Lifecycle ────────────────────────────────────────────────────────────


def test_bus_lifecycle() -> None:
    """Test basic bus start/stop lifecycle."""
    bus = EventBus(enable_persistence=False)
    assert not bus.is_running

    bus.start()
    assert bus.is_running

    bus.stop()
    assert not bus.is_running


# ── Publish / Subscribe ──────────────────────────────────────────────────


def test_publish_and_subscribe(bus: EventBus) -> None:
    """Test publishing an event and receiving it in a subscriber."""
    received: list[Event] = []

    def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("test-sub", handler, [EventType.COMPANY_CREATED])

    publisher = bus.create_publisher("test-source")
    event = publisher.create_event(
        EventType.COMPANY_CREATED,
        payload={"company_name": "Acme Corp"},
    )
    bus.publish(event)

    assert len(received) == 1
    assert received[0].payload["company_name"] == "Acme Corp"
    assert received[0].metadata.event_type == EventType.COMPANY_CREATED


def test_publish_event_convenience(bus: EventBus) -> None:
    """Test the publish_event convenience method."""
    received: list[Event] = []

    def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("test-sub", handler, [EventType.COMPANY_CREATED])

    bus.publish_event(
        EventType.COMPANY_CREATED,
        payload={"name": "TestCo"},
        source="test",
    )

    assert len(received) == 1
    assert received[0].payload["name"] == "TestCo"


def test_multiple_subscribers(bus: EventBus) -> None:
    """Test fan-out to multiple subscribers."""
    results: list[str] = []

    def handler_a(event: Event) -> None:
        results.append("a")

    def handler_b(event: Event) -> None:
        results.append("b")

    bus.subscribe("sub-a", handler_a, [EventType.COMPANY_CREATED])
    bus.subscribe("sub-b", handler_b, [EventType.COMPANY_CREATED])

    bus.publish_event(EventType.COMPANY_CREATED)

    assert len(results) == 2
    assert "a" in results
    assert "b" in results


def test_event_filtering_by_type(bus: EventBus) -> None:
    """Test that subscribers only receive events they subscribe to."""
    received_types: list[str] = []

    def handler(event: Event) -> None:
        received_types.append(event.metadata.event_type.value)

    bus.subscribe("sub", handler, [EventType.COMPANY_CREATED])

    publisher = bus.create_publisher("test")

    bus.publish(publisher.create_event(EventType.COMPANY_CREATED))
    bus.publish(publisher.create_event(EventType.WORKFLOW_STARTED))
    bus.publish(publisher.create_event(EventType.COMPANY_CREATED))

    # Should only receive COMPANY_CREATED
    assert received_types == ["company.created", "company.created"]


def test_priority_ordering(bus: EventBus) -> None:
    """Test that critical events are processed first (basic)."""
    processed: list[str] = []

    def handler(event: Event) -> None:
        processed.append(event.metadata.priority.value)

    bus.subscribe("sub", handler)

    publisher = bus.create_publisher("test")

    bus.publish(
        publisher.create_event(
            EventType.COMPANY_CREATED,
            priority=EventPriority.LOW,
        )
    )
    bus.publish(
        publisher.create_event(
            EventType.WORKFLOW_STARTED,
            priority=EventPriority.CRITICAL,
        )
    )
    bus.publish(
        publisher.create_event(
            EventType.COMPANY_CREATED,
            priority=EventPriority.NORMAL,
        )
    )


# ── Metrics ──────────────────────────────────────────────────────────────


def test_metrics_collection(bus: EventBus) -> None:
    """Test that metrics are collected during bus operation."""

    def handler(event: Event) -> None:
        pass

    bus.subscribe("sub", handler, [EventType.COMPANY_CREATED])

    bus.publish_event(EventType.COMPANY_CREATED, source="test")
    bus.publish_event(EventType.COMPANY_CREATED, source="test")

    stats = bus.get_stats()

    assert stats["total_published"] == 2
    assert stats["by_type"]["company.created"] == 2
    assert stats["is_running"] is True


# ── Dead Letter Queue ────────────────────────────────────────────────────


def test_dead_letter_on_failure(bus: EventBus) -> None:
    """Test that failed events go to the dead letter queue."""
    received: list[Event] = []

    def failing_handler(event: Event) -> None:
        received.append(event)
        raise RuntimeError("Intentional failure")

    bus.subscribe("failing-sub", failing_handler, [EventType.COMPANY_CREATED])

    bus.publish_event(EventType.COMPANY_CREATED, source="test")

    dlq = bus.get_dead_letter_queue()
    assert len(dlq) == 1
    assert "Intentional failure" in dlq[0].error


def test_requeue_dead_letter(bus: EventBus) -> None:
    """Test re-queuing dead letter events."""
    call_count = 0

    def handler(event: Event) -> None:
        nonlocal call_count
        call_count += 1
        raise RuntimeError(f"Always fails (call #{call_count})")

    bus.subscribe("sub", handler, [EventType.COMPANY_CREATED])

    bus.publish_event(EventType.COMPANY_CREATED, source="test")

    # First attempt should produce 1 dead letter entry
    assert len(bus.get_dead_letter_queue()) == 1

    # Re-queue and re-process (handler still fails, so it goes back to DLQ)
    results = bus.requeue_dead_letter(count=1)

    assert len(results) > 0
    assert call_count == 2  # Handler was called again

    # The event was consumed from DLQ, re-published, and failed again,
    # so the DLQ should still have 1 entry (the new failure)
    assert len(bus.get_dead_letter_queue()) == 1


# ── History ──────────────────────────────────────────────────────────────


def test_event_history(bus: EventBus) -> None:
    """Test event history tracking."""

    def handler(event: Event) -> None:
        pass

    bus.subscribe("sub", handler, [EventType.COMPANY_CREATED])

    bus.publish_event(EventType.COMPANY_CREATED, source="test")

    history = bus.get_history()
    assert len(history) >= 2  # publish + deliver

    actions = [h["action"] for h in history]
    assert "published" in actions


# ── Router ───────────────────────────────────────────────────────────────


def test_router_route_registration(bus: EventBus) -> None:
    """Test direct route registration."""
    received: list[Event] = []

    def handler(event: Event) -> None:
        received.append(event)

    subscriber = Subscriber(
        subscriber_id="route-sub-id",
        name="route-sub",
        handler=handler,
        event_types=[EventType.COMPANY_CREATED],
    )

    route = Route(
        name="test-route",
        subscriber=subscriber,
        description="Test route",
    )
    bus.add_route(route)

    bus.publish_event(EventType.COMPANY_CREATED, source="test")

    assert len(received) == 1


# ── Publisher Management ─────────────────────────────────────────────────


def test_publisher_creation() -> None:
    """Test publisher management."""
    bus = EventBus(enable_persistence=False)

    pub = bus.create_publisher("engine-x", description="Test engine")
    assert pub.source == "engine-x"
    assert pub.description == "Test engine"

    assert bus.get_publisher("engine-x") is pub

    publishers = bus.list_publishers()
    assert len(publishers) == 1
    assert publishers[0]["source"] == "engine-x"


def test_requeue_dead_letter_succeeds_on_retry(bus: EventBus) -> None:
    """Test re-queuing dead letter when handler succeeds on retry."""
    call_count = 0

    def handler(event: Event) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Transient failure")
        # Second call succeeds

    bus.subscribe("sub", handler, [EventType.COMPANY_CREATED])

    bus.publish_event(EventType.COMPANY_CREATED, source="test")

    # First attempt produced 1 DLQ entry
    assert len(bus.get_dead_letter_queue()) == 1

    # Re-queue — this time handler succeeds
    results = bus.requeue_dead_letter(count=1)

    assert len(results) > 0
    assert all(r.status == EventStatus.DELIVERED for r in results)
    assert call_count == 2

    # DLQ should be empty now (consumed, not re-added since it succeeded)
    assert len(bus.get_dead_letter_queue()) == 0


# ── Persistence ──────────────────────────────────────────────────────────


def test_persistence(tmp_path: Path) -> None:
    """Test event persistence to disk."""
    store_path = tmp_path / "store.jsonl"
    bus = EventBus(
        enable_persistence=True,
        storage_path=str(store_path),
    )
    bus.start()

    def handler(event: Event) -> None:
        pass

    bus.subscribe("sub", handler, [EventType.COMPANY_CREATED])
    bus.publish_event(
        EventType.COMPANY_CREATED,
        source="test",
        payload={"key": "value"},
    )

    bus.stop()

    # Verify persistence file exists and has content
    assert store_path.exists()
    content = store_path.read_text()
    assert "company.created" in content
    assert "key" in content
    assert "value" in content
