"""Metrics collector for AI Enterprise OS Audit Engine."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any


class MetricsCollector:
    """Collects performance metrics for audit events."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self._timers: dict[str, float] = {}
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._event_counts: dict[str, int] = defaultdict(int)
        self._error_counts: dict[str, int] = defaultdict(int)

    def start_timer(self, name: str) -> None:
        """Start a named timer."""
        self._timers[name] = time.time()

    def stop_timer(self, name: str) -> float:
        """Stop a named timer and return elapsed seconds."""
        if name not in self._timers:
            return 0.0
        elapsed = time.time() - self._timers.pop(name, time.time())
        self._latencies[name].append(elapsed)
        return elapsed

    def increment_counter(self, name: str, value: int = 1) -> None:
        """Increment a named counter."""
        self._counters[name] += value

    def set_gauge(self, name: str, value: float) -> None:
        """Set a named gauge value."""
        self._gauges[name] = value

    def record_event(self, event_type: str, result: str = "success") -> None:
        """Record an event occurrence."""
        self._event_counts[event_type] += 1
        if result == "error":
            self._error_counts[event_type] += 1

    def record_error(self, error_type: str) -> None:
        """Record an error occurrence."""
        self._error_counts[error_type] += 1

    def get_timer(self, name: str) -> float | None:
        """Get current timer value if running."""
        if name in self._timers:
            return time.time() - self._timers[name]
        return None

    def get_counter(self, name: str) -> int:
        """Get counter value."""
        return self._counters.get(name, 0)

    def get_gauge(self, name: str) -> float | None:
        """Get gauge value."""
        return self._gauges.get(name)

    def get_latency_stats(self, name: str) -> dict[str, float]:
        """Get latency statistics for a named timer."""
        latencies = self._latencies.get(name, [])
        if not latencies:
            return {
                "count": 0,
                "min": 0,
                "max": 0,
                "avg": 0,
                "p50": 0,
                "p95": 0,
                "p99": 0,
            }

        sorted_lats = sorted(latencies)
        n = len(sorted_lats)

        return {
            "count": n,
            "min": sorted_lats[0],
            "max": sorted_lats[-1],
            "avg": sum(sorted_lats) / n,
            "p50": sorted_lats[int(n * 0.5)],
            "p95": sorted_lats[int(n * 0.95)],
            "p99": sorted_lats[int(n * 0.99)],
        }

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all collected metrics."""
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "latencies": {
                name: self.get_latency_stats(name) for name in self._latencies
            },
            "event_counts": dict(self._event_counts),
            "error_counts": dict(self._error_counts),
            "active_timers": len(self._timers),
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self._timers.clear()
        self._counters.clear()
        self._gauges.clear()
        self._latencies.clear()
        self._event_counts.clear()
        self._error_counts.clear()
