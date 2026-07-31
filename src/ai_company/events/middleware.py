"""Middleware pipeline for the Event Bus.

Middleware wraps around event handlers to provide cross-cutting concerns
like logging, validation, metrics, retries, and error handling without
modifying the handler itself.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from ai_company.events.models import Event

logger = logging.getLogger(__name__)

# Type alias for next handler in pipeline
NextHandler = Callable[[Event], Any]


class Middleware(ABC):
    """Base class for event middleware.

    Middleware wraps around event handlers to add cross-cutting behavior.
    """

    @abstractmethod
    def handle(self, event: Event, next_handler: NextHandler) -> Any:
        """Process an event with optional side effects.

        Args:
            event: The event being processed
            next_handler: The next middleware or final handler

        Returns:
            Result from the handler chain
        """
        ...


class LoggingMiddleware(Middleware):
    """Log event processing for observability."""

    def handle(self, event: Event, next_handler: NextHandler) -> Any:
        logger.info(
            f"Processing event: {event.metadata.event_type.value} "
            f"[{event.metadata.event_id}] from {event.metadata.source}"
        )
        try:
            result = next_handler(event)
            logger.debug(
                f"Completed event: {event.metadata.event_type.value} "
                f"[{event.metadata.event_id}]"
            )
            return result
        except Exception as e:
            logger.error(
                f"Failed event: {event.metadata.event_type.value} "
                f"[{event.metadata.event_id}]: {e}"
            )
            raise


class MetricsMiddleware(Middleware):
    """Record processing metrics for each event."""

    def __init__(self) -> None:
        self.processing_times: dict[str, list[float]] = {}

    def handle(self, event: Event, next_handler: NextHandler) -> Any:
        start = time.monotonic()
        try:
            result = next_handler(event)
            return result
        finally:
            elapsed = time.monotonic() - start
            event_type = event.metadata.event_type.value
            if event_type not in self.processing_times:
                self.processing_times[event_type] = []
            self.processing_times[event_type].append(elapsed)

    def get_stats(self) -> dict[str, dict[str, float]]:
        """Get processing time statistics."""
        stats: dict[str, dict[str, float]] = {}
        for event_type, times in self.processing_times.items():
            if times:
                stats[event_type] = {
                    "count": len(times),
                    "avg_ms": (sum(times) / len(times)) * 1000,
                    "max_ms": max(times) * 1000,
                    "min_ms": min(times) * 1000,
                }
        return stats


class ValidationMiddleware(Middleware):
    """Validate events before processing."""

    def handle(self, event: Event, next_handler: NextHandler) -> Any:
        if not event.metadata.event_type:
            raise ValueError("Event must have an event_type")
        if not event.metadata.source:
            raise ValueError("Event must have a source")
        return next_handler(event)


class RetryMiddleware(Middleware):
    """Retry event handling on failure."""

    def __init__(self, max_retries: int = 3, base_delay: float = 0.1) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay

    def handle(self, event: Event, next_handler: NextHandler) -> Any:
        import time as _time

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return next_handler(event)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"Retry {attempt}/{self.max_retries} for "
                        f"{event.metadata.event_type.value} "
                        f"after {delay:.2f}s: {e}"
                    )
                    _time.sleep(delay)
        raise last_error  # type: ignore[misc]


class MiddlewarePipeline:
    """Chain of middleware that wraps around an event handler.

    Middleware is executed in the order it was added (first added = first executed).
    """

    def __init__(self, middlewares: list[Middleware] | None = None) -> None:
        self._middlewares = middlewares or []

    def add(self, middleware: Middleware) -> None:
        """Add middleware to the pipeline."""
        self._middlewares.append(middleware)

    def execute(self, event: Event, handler: NextHandler) -> Any:
        """Execute the middleware pipeline for an event.

        Args:
            event: The event to process
            handler: The final handler to invoke

        Returns:
            Result from the handler chain
        """

        def chain(index: int) -> NextHandler:
            def _handle(evt: Event) -> Any:
                if index < len(self._middlewares):
                    return self._middlewares[index].handle(evt, chain(index + 1))
                return handler(evt)

            return _handle

        return chain(0)(event)
