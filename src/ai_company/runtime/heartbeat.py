"""Heartbeat monitoring for runtime components.

Every registered engine/process is expected to beat within
``interval_seconds``. A component whose last heartbeat is older than
``timeout_seconds`` is stale; after ``missed_beats_before_failure``
consecutive misses the failure callback fires (wired to the watchdog/
supervisor).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ai_company.runtime.models import HealthStatus, Heartbeat

logger = logging.getLogger(__name__)

FailureCallback = Callable[[str, str], None]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class HeartbeatManager:
    """Tracks heartbeats and reports stale components.

    Args:
        settings: The ``heartbeat`` config section dict.
        on_failure: Optional callback ``(component, reason)`` invoked when
            a component is declared failed.
    """

    def __init__(
        self,
        settings: dict[str, Any] | None = None,
        on_failure: FailureCallback | None = None,
    ) -> None:
        self.settings = settings or {}
        self.enabled = bool(self.settings.get("enabled", True))
        self.interval_seconds = float(self.settings.get("interval_seconds", 5.0))
        self.timeout_seconds = float(self.settings.get("timeout_seconds", 15.0))
        self.missed_threshold = int(self.settings.get("missed_beats_before_failure", 3))
        self.on_failure = on_failure
        self._heartbeats: dict[str, Heartbeat] = {}
        self._consecutive_misses: dict[str, int] = {}
        # RLock: beat() holds the lock and calls register() which re-acquires it.
        self._lock = threading.RLock()

    # ── Registration ───────────────────────────────────────────────

    def register(
        self,
        component: str,
        interval_seconds: float | None = None,
    ) -> Heartbeat:
        """Register a component to be monitored."""
        interval = interval_seconds or self.interval_seconds
        with self._lock:
            existing = self._heartbeats.get(component)
            if existing is not None:
                existing.interval_seconds = interval
                return existing
            heartbeat = Heartbeat(
                component=component,
                interval_seconds=interval,
                sent_at=_utcnow(),
                received_at=_utcnow(),
            )
            self._heartbeats[component] = heartbeat
            self._consecutive_misses[component] = 0
            logger.info("Heartbeat monitor registered for %s", component)
            return heartbeat

    def unregister(self, component: str) -> bool:
        """Stop monitoring a component."""
        with self._lock:
            existed = component in self._heartbeats
            self._heartbeats.pop(component, None)
            self._consecutive_misses.pop(component, None)
            return existed

    # ── Beats ──────────────────────────────────────────────────────

    def beat(
        self,
        component: str,
        status: HealthStatus = HealthStatus.HEALTHY,
        payload: dict[str, Any] | None = None,
    ) -> Heartbeat:
        """Record a heartbeat from a component."""
        now = _utcnow()
        with self._lock:
            previous = self._heartbeats.get(component)
            if previous is None:
                previous = self.register(component)
            seq = previous.seq + 1
            heartbeat = Heartbeat(
                component=component,
                sent_at=now,
                received_at=now,
                seq=seq,
                interval_seconds=previous.interval_seconds,
                status=status,
                payload=payload or {},
            )
            self._heartbeats[component] = heartbeat
            self._consecutive_misses[component] = 0
            return heartbeat

    # ── Inspection ─────────────────────────────────────────────────

    def get(self, component: str) -> Heartbeat | None:
        """Return the latest heartbeat for a component."""
        return self._heartbeats.get(component)

    def list_heartbeats(self) -> list[Heartbeat]:
        """Return all recorded heartbeats (newest first)."""
        return sorted(
            self._heartbeats.values(),
            key=lambda h: h.received_at,
            reverse=True,
        )

    def components(self) -> list[str]:
        """Return monitored component names."""
        return list(self._heartbeats)

    def seconds_since(self, component: str, now: datetime | None = None) -> float:
        """Seconds since a component's last heartbeat (inf when unknown)."""
        now = now or _utcnow()
        heartbeat = self._heartbeats.get(component)
        if heartbeat is None:
            return float("inf")
        return max(0.0, (now - heartbeat.received_at).total_seconds())

    def is_stale(self, component: str, now: datetime | None = None) -> bool:
        """Return whether a component has exceeded the silence timeout."""
        return self.seconds_since(component, now) > self.timeout_seconds

    def consecutive_misses(self, component: str) -> int:
        """Return the current consecutive-miss count for a component."""
        return self._consecutive_misses.get(component, 0)

    # ── Checking ───────────────────────────────────────────────────

    def check(self, now: datetime | None = None) -> list[tuple[str, str]]:
        """Check every component and declare failures.

        Returns:
            List of ``(component, reason)`` failures discovered this pass.
        """
        now = now or _utcnow()
        failures: list[tuple[str, str]] = []
        with self._lock:
            for component in self.components():
                if not self.is_stale(component, now):
                    self._consecutive_misses[component] = 0
                    continue
                misses = self._consecutive_misses.get(component, 0) + 1
                self._consecutive_misses[component] = misses
                if misses >= self.missed_threshold:
                    reason = "heartbeat_timeout"
                    failures.append((component, reason))
                    logger.warning(
                        "Heartbeat failure for %s (%d consecutive misses)",
                        component,
                        misses,
                    )
                    if self.on_failure is not None:
                        try:
                            self.on_failure(component, reason)
                        except Exception as exc:
                            logger.error("Heartbeat failure handler error: %s", exc)
                    self._consecutive_misses[component] = 0
        return failures

    def heartbeat_miss_count(self) -> int:
        """Total number of components currently stale."""
        return sum(1 for component in self.components() if self.is_stale(component))

    def reset(self) -> None:
        """Clear all heartbeat records."""
        with self._lock:
            self._heartbeats.clear()
            self._consecutive_misses.clear()

    def snapshot(self) -> dict[str, Any]:
        """Return a compact snapshot for diagnostics."""
        return {
            "enabled": self.enabled,
            "monitored": len(self._heartbeats),
            "stale": self.heartbeat_miss_count(),
            "components": {
                component: {
                    "seq": h.seq,
                    "seconds_since": self.seconds_since(component),
                    "status": h.status.value,
                }
                for component, h in self._heartbeats.items()
            },
        }
