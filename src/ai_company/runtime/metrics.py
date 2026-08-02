"""Runtime metrics — lightweight counters, gauges, and timers.

The metrics registry backs :class:`RuntimeMetrics` with a simple dict
store, supporting increment/decrement counters, set/track gauges, and
elapsed-time timers (via :class:`Timer` context manager). Snapshotting
produces a plain dict for serialization and the CLI.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from ai_company.runtime.models import RuntimeMetrics

logger = logging.getLogger(__name__)

# Recovery-outcome metric names (T4 — self-healing success rate).
RECOVERY_ATTEMPTS = "recovery_attempts"
RECOVERY_SUCCESSES = "recovery_successes"
RECOVERY_FAILURES = "recovery_failures"
RECOVERY_SUCCESS_RATE = "recovery_success_rate"


class MetricsRegistry:
    """Thread-safe runtime metrics registry."""

    def __init__(self) -> None:
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, Any] = {}
        self._timers: dict[str, float] = {}
        self._lock = threading.Lock()
        self._started_at = time.monotonic()

    # ── Counters ───────────────────────────────────────────────────

    def increment(self, name: str, amount: float = 1.0) -> float:
        with self._lock:
            value = self._counters.get(name, 0.0) + amount
            self._counters[name] = value
            return value

    def decrement(self, name: str, amount: float = 1.0) -> float:
        return self.increment(name, -amount)

    def counter(self, name: str) -> float:
        return self._counters.get(name, 0.0)

    def counters(self) -> dict[str, float]:
        with self._lock:
            return dict(self._counters)

    # ── Gauges ─────────────────────────────────────────────────────

    def set_gauge(self, name: str, value: Any) -> None:
        """Set a gauge; dicts are stored as-is (e.g. queue sizes)."""
        with self._lock:
            if isinstance(value, dict):
                self._gauges[name] = dict(value)
            else:
                self._gauges[name] = float(value)

    def gauge(self, name: str) -> Any:
        return self._gauges.get(name, 0.0)

    def gauges(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._gauges)

    # ── Timers ─────────────────────────────────────────────────────

    def record_timer(self, name: str, seconds: float) -> float:
        with self._lock:
            total = self._timers.get(name, 0.0) + float(seconds)
            self._timers[name] = total
            return total

    def timer(self, name: str) -> float:
        return self._timers.get(name, 0.0)

    def timers(self) -> dict[str, float]:
        with self._lock:
            return dict(self._timers)

    @contextmanager
    def timed(self, name: str) -> Iterator[None]:
        """Time a block and add the elapsed seconds to a timer metric."""
        start = time.monotonic()
        try:
            yield
        finally:
            self.record_timer(name, time.monotonic() - start)

    # ── Snapshots ──────────────────────────────────────────────────

    def uptime_seconds(self) -> float:
        return time.monotonic() - self._started_at

    def snapshot(self) -> dict[str, Any]:
        """Return a merged snapshot dict for RuntimeMetrics."""
        return {
            "counters": self.counters(),
            "gauges": self.gauges(),
            "timers": self.timers(),
            "uptime_seconds": round(self.uptime_seconds(), 3),
        }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._timers.clear()
            self._started_at = time.monotonic()

    def to_metrics(self, **overrides: Any) -> RuntimeMetrics:
        """Build a RuntimeMetrics model from current registry values."""
        gauges = self.gauges()
        counters = self.counters()
        return RuntimeMetrics(
            uptime_seconds=round(self.uptime_seconds(), 3),
            cpu_percent=gauges.get("cpu_percent"),
            memory_percent=gauges.get("memory_percent"),
            active_engines=int(gauges.get("active_engines", 0)),
            active_workflows=int(gauges.get("active_workflows", 0)),
            active_decisions=int(gauges.get("active_decisions", 0)),
            active_pipelines=int(gauges.get("active_pipelines", 0)),
            active_meetings=int(gauges.get("active_meetings", 0)),
            active_projects=int(gauges.get("active_projects", 0)),
            active_agents=int(gauges.get("active_agents", 0)),
            queue_sizes=gauges.get("queue_sizes", {}),
            engine_healthy=int(gauges.get("engine_healthy", 0)),
            engine_degraded=int(gauges.get("engine_degraded", 0)),
            engine_failed=int(gauges.get("engine_failed", 0)),
            heartbeat_misses=int(gauges.get("heartbeat_misses", 0)),
            failed_events=int(counters.get("failed_events", 0)),
            error_rate=counters.get("error_rate", 0.0),
            jobs_executed=int(counters.get("jobs_executed", 0)),
            jobs_failed=int(counters.get("jobs_failed", 0)),
            restarts=int(counters.get("restarts", 0)),
            recovery_attempts=int(counters.get(RECOVERY_ATTEMPTS, 0)),
            recovery_successes=int(counters.get(RECOVERY_SUCCESSES, 0)),
            recovery_failures=int(counters.get(RECOVERY_FAILURES, 0)),
            recovery_success_rate=round(
                float(gauges.get(RECOVERY_SUCCESS_RATE, 0.0)), 1
            ),
            counters=counters,
            timers=self.timers(),
        )


def metrics_trend(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Derive the dashboard trend dict from one persisted metrics snapshot.

    Tolerates both persisted shapes (T1/T4): registry-shaped records with
    ``gauges`` and ``counters`` dicts (the telemetry log fixture shape), and
    flattened ``RuntimeMetrics`` model dumps where gauge-like fields sit at
    the top level (the facade ``metrics_persist`` write path). Reads fall
    back so a field survives either shape — required so the recovery
    success-rate gauge and CPU/engine gauges render on the KPI panel.
    """
    raw_gauges = snapshot.get("gauges")
    gauges = raw_gauges if isinstance(raw_gauges, dict) else {}
    raw_counters = snapshot.get("counters")
    counters = raw_counters if isinstance(raw_counters, dict) else {}

    def gauge(name: str, default: Any = 0.0) -> Any:
        return gauges.get(name, snapshot.get(name, default))

    def counter(name: str, default: int = 0) -> int:
        return int(counters.get(name, snapshot.get(name, default)))

    return {
        "cpu_percent": gauge("cpu_percent", None),
        "memory_percent": gauge("memory_percent", None),
        "engine_healthy": int(gauge("engine_healthy")),
        "engine_degraded": int(gauge("engine_degraded")),
        "engine_failed": int(gauge("engine_failed")),
        "jobs_executed": counter("jobs_executed"),
        "jobs_failed": counter("jobs_failed"),
        "failed_events": counter("failed_events"),
        "restarts": counter("restarts"),
        "recovery_attempts": counter(RECOVERY_ATTEMPTS),
        "recovery_successes": counter(RECOVERY_SUCCESSES),
        "recovery_failures": counter(RECOVERY_FAILURES),
        "recovery_success_rate": round(float(gauge(RECOVERY_SUCCESS_RATE)), 1),
        "uptime_seconds": snapshot.get("uptime_seconds"),
    }
