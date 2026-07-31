"""Event bus metrics collection."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any


class EventMetrics:
    """Collects and reports event bus metrics.

    Tracks event volumes, processing times, error rates, and
    subscriber performance across all event types and priorities.
    """

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._total_published: int = 0
        self._total_delivered: int = 0
        self._total_failed: int = 0
        self._total_dead_letter: int = 0
        self._total_replayed: int = 0
        self._by_type: Counter[str] = Counter()
        self._by_priority: Counter[str] = Counter()
        self._by_source: Counter[str] = Counter()
        self._by_subscriber: Counter[str] = Counter()
        self._processing_times: dict[str, list[float]] = {}
        self._start_time: datetime = datetime.now(UTC)
        self._errors: Counter[str] = Counter()
        self._subscriber_errors: Counter[str] = Counter()

    def record_publish(self, event_type: str, priority: str, source: str) -> None:
        """Record an event publication."""
        self._total_published += 1
        self._by_type[event_type] += 1
        self._by_priority[priority] += 1
        self._by_source[source] += 1

    def record_delivery(self, event_type: str, processing_time: float) -> None:
        """Record a successful delivery."""
        self._total_delivered += 1
        if event_type not in self._processing_times:
            self._processing_times[event_type] = []
        self._processing_times[event_type].append(processing_time)

    def record_failure(self, event_type: str, error: str) -> None:
        """Record a delivery failure."""
        self._total_failed += 1
        self._errors[error] += 1

    def record_dead_letter(self, event_type: str) -> None:
        """Record a dead letter event."""
        self._total_dead_letter += 1

    def record_replay(self, count: int) -> None:
        """Record a replay operation."""
        self._total_replayed += count

    def record_subscriber_delivery(self, subscriber_name: str) -> None:
        """Record a subscriber delivery."""
        self._by_subscriber[subscriber_name] += 1

    def record_subscriber_error(self, subscriber_name: str) -> None:
        """Record a subscriber error."""
        self._subscriber_errors[subscriber_name] += 1

    def get_stats(self) -> dict[str, Any]:
        """Get all collected metrics."""
        uptime = (datetime.now(UTC) - self._start_time).total_seconds()

        avg_times: dict[str, float] = {}
        for et, times in self._processing_times.items():
            avg_times[et] = (sum(times) / len(times)) * 1000 if times else 0.0

        return {
            "total_published": self._total_published,
            "total_delivered": self._total_delivered,
            "total_failed": self._total_failed,
            "total_dead_letter": self._total_dead_letter,
            "total_replayed": self._total_replayed,
            "by_type": dict(self._by_type.most_common()),
            "by_priority": dict(self._by_priority),
            "by_source": dict(self._by_source),
            "by_subscriber": dict(self._by_subscriber),
            "subscriber_errors": dict(self._subscriber_errors),
            "errors": dict(self._errors.most_common(10)),
            "avg_processing_time_ms": avg_times,
            "uptime_seconds": uptime,
            "error_rate": (
                (self._total_failed / self._total_published * 100)
                if self._total_published > 0
                else 0.0
            ),
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self._reset()
