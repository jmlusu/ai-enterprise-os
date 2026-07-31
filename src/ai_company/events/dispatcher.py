"""Event dispatcher for the Event Bus.

Dispatches events to subscribers with configurable delivery semantics:
at-most-once, at-least-once, and exactly-once delivery guarantees.
Handles fan-out, acknowledgements, and error management.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ai_company.events.metrics import EventMetrics
from ai_company.events.models import (
    DeliveryResult,
    Event,
    EventStatus,
)
from ai_company.events.subscriber import Subscriber

logger = logging.getLogger(__name__)

# Type alias for delivery callback
DeliveryCallback = Callable[[DeliveryResult], None]


class Dispatcher:
    """Dispatches events to subscribers with configurable delivery guarantees.

    Supports three delivery modes:
    - AT_MOST_ONCE: Fire and forget, no retries
    - AT_LEAST_ONCE: Retry on failure until success or max retries
    - EXACTLY_ONCE: At-least-once + idempotency checks
    """

    DELIVERY_MODES = ("AT_MOST_ONCE", "AT_LEAST_ONCE", "EXACTLY_ONCE")

    def __init__(
        self,
        metrics: EventMetrics | None = None,
        max_workers: int = 4,
    ) -> None:
        self.metrics = metrics or EventMetrics()
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._processed_ids: set[str] = set()
        self.logger = logging.getLogger(self.__class__.__name__)

    def dispatch(
        self,
        event: Event,
        subscribers: list[Subscriber],
        delivery_mode: str = "AT_LEAST_ONCE",
        callback: DeliveryCallback | None = None,
    ) -> list[DeliveryResult]:
        """Dispatch an event to multiple subscribers.

        Args:
            event: The event to dispatch
            subscribers: Subscribers to deliver to
            delivery_mode: One of AT_MOST_ONCE, AT_LEAST_ONCE, EXACTLY_ONCE
            callback: Optional callback per delivery result

        Returns:
            List of delivery results, one per subscriber
        """
        if delivery_mode not in self.DELIVERY_MODES:
            raise ValueError(
                f"Unknown delivery mode: {delivery_mode}. "
                f"Must be one of {self.DELIVERY_MODES}"
            )

        results: list[DeliveryResult] = []
        for subscriber in subscribers:
            result = self._deliver_to_subscriber(event, subscriber, delivery_mode)
            if callback:
                callback(result)
            results.append(result)
            self._record_metrics(event, result)
        return results

    def dispatch_async(
        self,
        event: Event,
        subscribers: list[Subscriber],
        delivery_mode: str = "AT_LEAST_ONCE",
        callback: DeliveryCallback | None = None,
    ) -> asyncio.Task[Any]:
        """Dispatch an event asynchronously.

        Args:
            Same as dispatch()

        Returns:
            An asyncio Task wrapping the dispatch
        """

        async def _dispatch() -> Any:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self._executor,
                self.dispatch,
                event,
                subscribers,
                delivery_mode,
                callback,
            )

        return asyncio.ensure_future(_dispatch())

    def broadcast(
        self,
        event: Event,
        subscribers: list[Subscriber],
        delivery_mode: str = "AT_LEAST_ONCE",
    ) -> dict[str, DeliveryResult]:
        """Broadcast an event, delivering to all subscribers in parallel.

        Args:
            event: The event to broadcast
            subscribers: Subscribers to deliver to
            delivery_mode: Delivery guarantee mode

        Returns:
            Dict mapping subscriber names to their delivery results
        """
        import concurrent.futures

        results: dict[str, DeliveryResult] = {}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(len(subscribers), self.max_workers)
        ) as executor:
            future_map = {}
            for subscriber in subscribers:
                future = executor.submit(
                    self._deliver_to_subscriber, event, subscriber, delivery_mode
                )
                future_map[future] = subscriber

            for future in concurrent.futures.as_completed(future_map):
                subscriber = future_map[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = DeliveryResult(
                        event_id=event.metadata.event_id,
                        subscriber_name=subscriber.name,
                        status=EventStatus.FAILED,
                        error=str(e),
                    )
                results[subscriber.name] = result
                self._record_metrics(event, result)

        return results

    def _deliver_to_subscriber(
        self,
        event: Event,
        subscriber: Subscriber,
        delivery_mode: str,
    ) -> DeliveryResult:
        """Deliver a single event to a single subscriber.

        Args:
            event: The event to deliver
            subscriber: Target subscriber
            delivery_mode: Delivery guarantee mode

        Returns:
            Delivery result
        """
        event_id = event.metadata.event_id

        # Exactly-once: skip if already processed
        if delivery_mode == "EXACTLY_ONCE":
            if event_id in self._processed_ids:
                return DeliveryResult(
                    event_id=event_id,
                    subscriber_name=subscriber.name,
                    status=EventStatus.SKIPPED,
                    note="Already processed (exactly-once)",
                )

        if not subscriber.matches(event.metadata.event_type):
            return DeliveryResult(
                event_id=event_id,
                subscriber_name=subscriber.name,
                status=EventStatus.SKIPPED,
                note="Subscriber does not handle this event type",
            )

        start_time = time.monotonic()
        try:
            subscriber.handle(event)
            elapsed = time.monotonic() - start_time

            if delivery_mode == "EXACTLY_ONCE":
                self._processed_ids.add(event_id)

            return DeliveryResult(
                event_id=event_id,
                subscriber_name=subscriber.name,
                status=EventStatus.DELIVERED,
                processing_time_ms=round(elapsed * 1000, 2),
            )
        except Exception as e:
            elapsed = time.monotonic() - start_time
            self.logger.error(
                f"Failed to deliver event {event_id} to {subscriber.name}: {e}"
            )
            return DeliveryResult(
                event_id=event_id,
                subscriber_name=subscriber.name,
                status=EventStatus.FAILED,
                error=str(e),
                processing_time_ms=round(elapsed * 1000, 2),
            )

    def _record_metrics(self, event: Event, result: DeliveryResult) -> None:
        """Record delivery metrics."""
        event_type = event.metadata.event_type.value
        self.metrics.record_subscriber_delivery(result.subscriber_name)

        if result.status == EventStatus.DELIVERED:
            self.metrics.record_delivery(
                event_type,
                result.processing_time_ms / 1000.0 if result.processing_time_ms else 0,
            )
        elif result.status == EventStatus.FAILED:
            self.metrics.record_failure(event_type, result.error or "unknown")
            self.metrics.record_subscriber_error(result.subscriber_name)

    def shutdown(self) -> None:
        """Shutdown the dispatcher and release resources."""
        self._executor.shutdown(wait=True)
