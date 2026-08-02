"""Supervisor — watches component health and coordinates recovery.

The supervisor owns the recovery loop:

1. The HeartbeatManager detects stale components and the HealthMonitor
   detects unhealthy engines; both report failures to the supervisor.
2. The supervisor resolves the component's :class:`RecoveryPolicy` and
   hands it to the RecoveryManager (restart / isolate / escalate).
3. Engine failures are broadcast on the event bus (``runtime.engine_failed``)
   so monitoring and orchestration can react.
4. Components without a recovery path are isolated to prevent cascading
   failures.

A periodic check thread drives the loop at ``check_interval_seconds``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ai_company.runtime.health import HealthMonitor
from ai_company.runtime.heartbeat import HeartbeatManager
from ai_company.runtime.models import (
    HealthStatus,
    RecoveryResult,
    publish_runtime_event,
)
from ai_company.runtime.recovery import RecoveryManager
from ai_company.telemetry.alerts import (
    record_alert_open,
    record_alert_resolved,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Supervisor:
    """Coordinates failure detection and recovery.

    Args:
        config: The ``recovery`` (or ``monitoring``) config section dict.
        heartbeats: HeartbeatManager used to detect stale components.
        health: HealthMonitor used to probe engine health.
        recovery: RecoveryManager that executes recovery policies.
        event_bus: Optional event bus for failure notifications.
        on_engine_failed: Optional callback ``(name, reason, result)``.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        heartbeats: HeartbeatManager | None = None,
        health: HealthMonitor | None = None,
        recovery: RecoveryManager | None = None,
        event_bus: Any | None = None,
        on_engine_failed: Callable[[str, str, RecoveryResult], None] | None = None,
    ) -> None:
        self.config = config or {}
        self.heartbeats = heartbeats
        self.health = health
        self.recovery = recovery
        self.event_bus = event_bus
        self.on_engine_failed = on_engine_failed
        self.check_interval_seconds = float(
            self.config.get("check_interval_seconds", 5.0)
        )
        self._isolated: set[str] = set()
        self._recent_failures: dict[str, datetime] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── Failure handling ───────────────────────────────────────────

    def on_failure(self, component: str, reason: str) -> None:
        """Handle a component failure (heartbeat watchdog / health check)."""
        if self._is_isolated(component):
            logger.warning(
                "Failure for isolated component %s ignored (%s)",
                component,
                reason,
            )
            return
        with self._lock:
            self._recent_failures[component] = _utcnow()
        logger.warning("Component failure detected: %s (%s)", component, reason)
        result = self._recover(component, reason)
        self._notify(component, reason, result)

    def _recover(self, component: str, reason: str) -> RecoveryResult:
        if self.recovery is None:
            return RecoveryResult(
                component=component,
                success=False,
                message="No recovery manager configured",
                recovered_at=_utcnow(),
            )
        result = self.recovery.recover(component, reason)
        if not result.success:
            self.isolate(
                component,
                reason=f"recovery failed: {reason}",
                attempts=result.attempts,
            )
        elif "isolate" in result.actions_taken:
            # Recovery stopped the process via an isolate action — the
            # component is dead, so stop monitoring it as well.
            self.isolate(
                component,
                reason=f"isolated during recovery: {reason}",
                attempts=result.attempts,
            )
        return result

    def _notify(self, component: str, reason: str, result: RecoveryResult) -> None:
        publish_runtime_event(
            getattr(self, "event_bus", None),
            "runtime.component_failed",
            {
                "component": component,
                "reason": reason,
                "actions_taken": result.actions_taken,
                "recovered": result.success,
            },
            source="runtime.supervisor",
        )
        if self.on_engine_failed is not None:
            try:
                self.on_engine_failed(component, reason, result)
            except Exception as exc:
                logger.error("on_engine_failed handler error: %s", exc)

    # ── Isolation ──────────────────────────────────────────────────

    def isolate(
        self,
        component: str,
        reason: str = "manual",
        attempts: int | None = None,
    ) -> None:
        """Stop monitoring a component and prevent recovery loops.

        Publishes ``runtime.engine_isolated`` on the event bus and records an
        open alert so the dashboard surfaces the isolation immediately.
        """
        with self._lock:
            self._isolated.add(component)
        if self.heartbeats is not None:
            self.heartbeats.unregister(component)
        if self.health is not None:
            self.health.unregister(component)
        logger.warning("Component %s isolated (%s)", component, reason)
        publish_runtime_event(
            getattr(self, "event_bus", None),
            "runtime.engine_isolated",
            {
                "component": component,
                "reason": reason,
                "attempts": attempts,
            },
            source="runtime.supervisor",
        )
        record_alert_open(
            component=component,
            reason=reason,
            attempts=attempts,
            source="runtime.supervisor",
        )

    def _is_isolated(self, component: str) -> bool:
        with self._lock:
            return component in self._isolated

    def unisolate(self, component: str) -> None:
        """Re-admit a component to supervision.

        Publishes ``runtime.engine_unisolated`` and resolves any open alert
        for the component (alert resolved on recovery — no-spam contract).
        """
        with self._lock:
            self._isolated.discard(component)
        if self.recovery is not None:
            self.recovery.reset(component)
        logger.info("Component %s un-isolated", component)
        publish_runtime_event(
            getattr(self, "event_bus", None),
            "runtime.engine_unisolated",
            {"component": component},
            source="runtime.supervisor",
        )
        record_alert_resolved(
            component=component,
            reason="unisolated",
            source="runtime.supervisor",
        )

    def isolated(self) -> list[str]:
        with self._lock:
            return sorted(self._isolated)

    # ── Supervision loop ───────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="runtime-supervisor",
                daemon=True,
            )
            self._thread.start()
            logger.info(
                "Supervisor started (check interval=%ss)",
                self.check_interval_seconds,
            )

    def stop(self, timeout: float = 5.0) -> None:
        with self._lock:
            if self._thread is None:
                return
            self._stop_event.set()
            self._thread.join(timeout=timeout)
            self._thread = None
            logger.info("Supervisor stopped")

    def is_running(self) -> bool:
        return bool(self._thread is not None and self._thread.is_alive())

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.check_once()
            except Exception as exc:
                logger.error("Supervisor check failed: %s", exc)
            self._stop_event.wait(self.check_interval_seconds)

    def check_once(self, now: datetime | None = None) -> list[str]:
        """Run one supervision pass. Returns failed component names.

        Args:
            now: Clock override for deterministic tests; forwarded to the
                heartbeat manager's staleness check.
        """
        failures: list[str] = []
        if self.heartbeats is not None:
            for component, reason in self.heartbeats.check(now=now):
                failures.append(component)
                self.on_failure(component, reason)
        if self.health is not None:
            for check in self.health.check_all():
                if check.status in (HealthStatus.UNHEALTHY, HealthStatus.DEGRADED):
                    failures.append(check.component)
                    self.on_failure(check.component, check.status.value)
        return failures

    # ── Inspection ─────────────────────────────────────────────────

    def recent_failures(self) -> dict[str, str]:
        with self._lock:
            return {name: dt.isoformat() for name, dt in self._recent_failures.items()}

    def snapshot(self) -> dict[str, Any]:
        return {
            "running": self.is_running(),
            "isolated": self.isolated(),
            "recent_failures": self.recent_failures(),
            "recovery": self.recovery.snapshot() if self.recovery else {},
        }
