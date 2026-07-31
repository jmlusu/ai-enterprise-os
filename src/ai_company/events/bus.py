"""Core Event Bus implementation.

The EventBus is the central hub that connects publishers, subscribers,
routes, dispatchers, persistence, dead letter queue, replay engine,
metrics, middleware, and history into a unified event-driven messaging
platform for AI Enterprise OS.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List, Optional

from ai_company.events.dead_letter import DeadLetterQueue, DeadLetterRecord
from ai_company.events.dispatcher import Dispatcher
from ai_company.events.history import EventHistory
from ai_company.events.metrics import EventMetrics
from ai_company.events.middleware import (
    MiddlewarePipeline,
    LoggingMiddleware,
    MetricsMiddleware,
    ValidationMiddleware,
)
from ai_company.events.models import (
    DeliveryResult,
    Event,
    EventPriority,
    EventStatus,
    EventType,
    ReplayRequest,
)
from ai_company.events.persistence import EventPersistence
from ai_company.events.priorities import PriorityProcessor
from ai_company.events.publisher import Publisher
from ai_company.events.registry import EventTypeRegistry
from ai_company.events.replay import ReplayEngine, ReplaySession
from ai_company.events.router import Route, Router
from ai_company.events.subscriber import Subscriber

logger = logging.getLogger(__name__)

#: Default replay handler used by EventBus.dispatch_event
ReplayEventHandler = Callable[[Event], None]


class EventBus:
    """Enterprise event bus connecting all AI Company subsystems.

    Usage::

        bus = EventBus()
        bus.start()

        # Publish an event
        bus.publish(some_event)

        # Subscribe directly
        bus.subscribe("my-sub", handler, [EventType.COMPANY_CREATED])

        # Or use routes
        bus.add_route(Route(name="my-route", subscriber=sub, ...))

        bus.stop()

    Features enabled by default:
    - Logging middleware
    - Validation middleware
    - Metrics collection
    - Priority processing
    - Event persistence (JSONL)
    - Event history (audit trail)
    - Dead letter queue
    """

    def __init__(
        self,
        storage_path: str = "events/store.jsonl",
        dead_letter_path: str = "events/dead_letter.jsonl",
        max_history: int = 10000,
        max_workers: int = 4,
        enable_persistence: bool = True,
        enable_middleware: bool = True,
        auto_start: bool = False,
    ) -> None:
        # Core components
        self.registry = EventTypeRegistry()
        self.priority_processor = PriorityProcessor()
        self.router = Router()
        self.dispatcher = Dispatcher(max_workers=max_workers)
        self.metrics = EventMetrics()
        self.history = EventHistory(max_entries=max_history)
        self.event_type_registry = self.registry  # alias for clarity

        # Persistence
        self.persistence: Optional[EventPersistence] = (
            EventPersistence(storage_path) if enable_persistence else None
        )
        self.dead_letter = DeadLetterQueue(dead_letter_path)

        # Replay
        # Persistence is Optional[EventPersistence]; ReplayEngine accepts EventPersistence.
        # This is safe because replay is only invoked when persistence is available.
        self.replay_engine = ReplayEngine(
            persistence=self.persistence,  # type: ignore[arg-type]
        )

        # Middleware pipeline
        self.middleware = MiddlewarePipeline()
        if enable_middleware:
            self.middleware.add(LoggingMiddleware())
            self.middleware.add(ValidationMiddleware())
        self._metrics_middleware = MetricsMiddleware()
        if enable_middleware:
            self.middleware.add(self._metrics_middleware)

        # State
        self._running = False
        self._lock = threading.Lock()
        self._publishers: Dict[str, Publisher] = {}
        self._replay_handler: Optional[ReplayEventHandler] = None

        self.logger = logging.getLogger(self.__class__.__name__)

        # Standard event types are registered in EventTypeRegistry.__init__

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the event bus.

        Enables event processing. Events published before start()
        are queued and processed once started.
        """
        with self._lock:
            self._running = True
            self.logger.info("EventBus started")

    def stop(self) -> None:
        """Stop the event bus gracefully.

        Flushes queued events and shuts down the dispatcher.
        """
        with self._lock:
            self._running = False
            self._flush_queue()
            self.dispatcher.shutdown()
            self.logger.info("EventBus stopped")

    @property
    def is_running(self) -> bool:
        """Check if the event bus is running."""
        return self._running

    # ------------------------------------------------------------------
    # Publisher management
    # ------------------------------------------------------------------

    def create_publisher(
        self,
        source: str,
        description: str = "",
        default_priority: EventPriority = EventPriority.NORMAL,
    ) -> Publisher:
        """Create a publisher for a given source component.

        Args:
            source: Component name (e.g. "orchestrator", "memory_engine")
            description: Human-readable description
            default_priority: Default priority for events from this publisher

        Returns:
            A Publisher instance
        """
        if source in self._publishers:
            raise ValueError(
                f"Publisher for source '{source}' already exists. "
                f"Use get_publisher() instead."
            )
        publisher = Publisher(
            source=source,
            description=description,
            default_priority=default_priority,
        )
        self._publishers[source] = publisher
        self.logger.debug(f"Created publisher: {source}")
        return publisher

    def get_publisher(self, source: str) -> Optional[Publisher]:
        """Get an existing publisher by source name."""
        return self._publishers.get(source)

    def list_publishers(self) -> List[Dict[str, Any]]:
        """List all registered publishers."""
        return [
            {"source": p.source, "description": p.description}
            for p in self._publishers.values()
        ]

    # ------------------------------------------------------------------
    # Subscription & Routing
    # ------------------------------------------------------------------

    def subscribe(
        self,
        name: str,
        handler: Callable[[Event], Any],
        event_types: Optional[List[EventType]] = None,
        description: str = "",
        auto_route: bool = True,
    ) -> Subscriber:
        """Register a subscriber with an optional route.

        Args:
            name: Subscriber name
            handler: Event handler function
            event_types: Event types to handle (None = all)
            description: Subscriber description
            auto_route: If True, automatically create a route for this subscriber

        Returns:
            The created Subscriber
        """
        subscriber = Subscriber(
            subscriber_id=f"sub:{name}",
            name=name,
            handler=handler,
            event_types=event_types or [],
            description=description,
        )

        if auto_route:
            self.router.add_subscriber_route(
                name=f"route:{name}",
                subscriber=subscriber,
                event_types=event_types,
                description=description,
            )

        return subscriber

    def unsubscribe(self, name: str) -> bool:
        """Remove a subscriber and its routes."""
        route_removed = self.router.remove_route(f"route:{name}")
        return route_removed

    def add_route(self, route: Route) -> None:
        """Register a route directly."""
        self.router.add_route(route)

    def add_subscriber_route(
        self,
        name: str,
        subscriber: Subscriber,
        event_types: Optional[List[EventType]] = None,
        priority: int = 100,
        description: str = "",
    ) -> Route:
        """Convenience method to create and register a route."""
        return self.router.add_subscriber_route(
            name=name,
            subscriber=subscriber,
            event_types=event_types,
            priority=priority,
            description=description,
        )

    # ------------------------------------------------------------------
    # Publishing & Dispatch
    # ------------------------------------------------------------------

    def publish(
        self,
        event: Event,
        delivery_mode: str = "AT_LEAST_ONCE",
    ) -> List[DeliveryResult]:
        """Publish an event to the bus.

        The event flows through:
        1. Middleware pipeline (logging, validation, metrics)
        2. Priority queue (for ordering by priority)
        3. Router (to find matching subscribers)
        4. Dispatcher (to deliver to subscribers)
        5. Persistence (store event history)
        6. Dead letter (on repeated failure)

        Args:
            event: The event to publish
            delivery_mode: Delivery guarantee mode

        Returns:
            List of delivery results per subscriber
        """
        if not self._running:
            self.logger.warning(
                f"EventBus not started. Queuing event: "
                f"{event.metadata.event_type.value}"
            )

        # 1. Middleware
        def _deliver(event: Event) -> List[DeliveryResult]:
            # 2. Route to subscribers
            subscribers = self.router.route_event(event)

            if not subscribers:
                self.logger.debug(
                    f"No subscribers for event: "
                    f"{event.metadata.event_type.value} "
                    f"[{event.metadata.event_id}]"
                )
                return []

            # 3. Dispatch to subscribers
            results = self.dispatcher.dispatch(event, subscribers, delivery_mode)

            # 4. Handle failures -> dead letter
            for result in results:
                if result.status == EventStatus.FAILED:
                    self.dead_letter.add(
                        event=event,
                        subscriber_name=result.subscriber_name,
                        error=result.error or "unknown error",
                        retry_count=3,
                    )
                    self.history.record_dead_letter(
                        event, result.subscriber_name, result.error or "unknown"
                    )
                else:
                    self.history.record_delivery(event, result)

            return results

        results = self.middleware.execute(event, _deliver)

        # 5. Persistence
        if self.persistence:
            self.persistence.persist(event)

        # 6. Record metrics + history
        event_type = event.metadata.event_type.value
        self.metrics.record_publish(
            event_type,
            event.metadata.priority.value,
            event.metadata.source,
        )
        self.history.record_publish(event)

        return results or []

    def publish_event(
        self,
        event_type: EventType,
        payload: Optional[Dict[str, Any]] = None,
        source: str = "unknown",
        priority: Optional[EventPriority] = None,
        correlation_id: Optional[str] = None,
        delivery_mode: str = "AT_LEAST_ONCE",
    ) -> List[DeliveryResult]:
        """Convenience method to create and publish an event in one call.

        Args:
            event_type: Type of event
            payload: Event payload data
            source: Source component name
            priority: Event priority (defaults to NORMAL)
            correlation_id: Optional correlation ID for event chains
            delivery_mode: Delivery guarantee

        Returns:
            List of delivery results
        """
        publisher = self.get_publisher(source)
        if not publisher:
            publisher = self.create_publisher(source)

        event = publisher.create_event(
            event_type=event_type,
            payload=payload,
            priority=priority,
            correlation_id=correlation_id,
        )
        return self.publish(event, delivery_mode=delivery_mode)

    def request(
        self,
        event: Event,
        timeout: float = 30.0,
    ) -> Optional[Event]:
        """Publish a request event and wait for a reply.

        Request/reply pattern: publishes an event and waits for
        a response event with a matching correlation_id.

        Args:
            event: The request event
            timeout: Maximum time to wait for reply (seconds)

        Returns:
            The reply event, or None if timeout
        """
        import threading as _threading

        reply_event: Optional[Event] = None
        reply_received = _threading.Event()

        # Register a temporary subscriber for the reply — construct reply event type
        reply_type = EventType(f"{event.metadata.event_type.value}_REPLY")

        def reply_handler(evt: Event) -> None:
            nonlocal reply_event
            if evt.metadata.correlation_id == event.metadata.event_id:
                reply_event = evt
                reply_received.set()

        # Temporarily subscribe for the reply
        temp_sub = self.subscribe(
            name=f"reqrep:{event.metadata.event_id}",
            handler=reply_handler,
            event_types=[reply_type],
            auto_route=True,
        )

        try:
            self.publish(event)
            reply_received.wait(timeout=timeout)
            return reply_event
        finally:
            self.unsubscribe(temp_sub.name)

    # ------------------------------------------------------------------
    # Event Bus Management
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics."""
        stats = self.metrics.get_stats()
        stats.update(
            {
                "is_running": self._running,
                "queue_size": self.priority_processor.size(),
                "route_count": self.router.route_count,
                "dead_letter_count": self.dead_letter.count(),
                "publisher_count": len(self._publishers),
                "history_count": self.history.count(),
            }
        )

        # Add middleware metrics
        mw_stats = self._metrics_middleware.get_stats()
        if mw_stats:
            stats["middleware_processing_times"] = mw_stats

        return stats

    def get_history(
        self,
        limit: int = 100,
        event_type: Optional[str] = None,
        action: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get event history with optional filtering."""
        entries = self.history.get_history(
            limit=limit, event_type=event_type, action=action
        )
        return [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "source": e.source,
                "action": e.action,
                "timestamp": e.timestamp.isoformat(),
                "details": e.details,
            }
            for e in entries
        ]

    def get_dead_letter_queue(self, limit: int = 10) -> List[DeadLetterRecord]:
        """View dead letter queue entries."""
        return self.dead_letter.peek(limit=limit)

    def requeue_dead_letter(self, count: int = 1) -> List[DeliveryResult]:
        """Re-queue dead letter events back onto the bus.

        Args:
            count: Number of events to requeue

        Returns:
            Results from republishing the events
        """
        events = self.dead_letter.requeue_events(count=count)
        results: List[DeliveryResult] = []
        for event in events:
            results.extend(self.publish(event))
        return results

    def clear_dead_letter(self) -> None:
        """Clear all dead letter records."""
        self.dead_letter.clear()

    # ------------------------------------------------------------------
    # Replay
    # ------------------------------------------------------------------

    def set_replay_handler(self, handler: ReplayEventHandler) -> None:
        """Set the default handler for replay operations.

        Args:
            handler: Function to call for each replayed event
        """
        self._replay_handler = handler
        self.replay_engine.handler = handler

    def replay(
        self,
        request: ReplayRequest,
        handler: Optional[ReplayEventHandler] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> ReplaySession:
        """Replay historical events.

        Args:
            request: Replay configuration
            handler: Handler for each event (defaults to republishing)
            progress_callback: Called with (processed, total)

        Returns:
            Replay session tracking progress
        """
        effective_handler: ReplayEventHandler = (
            handler or self._replay_handler or self._publish_as_replay_handler
        )
        return self.replay_engine.replay(request, effective_handler, progress_callback)

    def cancel_replay(self, session_id: str) -> bool:
        """Cancel a running replay session."""
        return self.replay_engine.cancel(session_id)

    def _publish_as_replay_handler(self, event: Event) -> None:
        """Publish an event as a replay handler callback."""
        self.publish(event)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _flush_queue(self) -> None:
        """Process all remaining events in the priority queue."""
        while not self.priority_processor.is_empty():
            event = self.priority_processor.dequeue()
            if event:
                try:
                    self.publish(event)
                except Exception as e:
                    self.logger.error(f"Failed to flush event: {e}")
