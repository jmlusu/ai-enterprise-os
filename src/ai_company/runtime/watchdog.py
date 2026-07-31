"""Watchdog — monitors component liveness and enforces deadlines.

The watchdog periodically probes the heartbeat manager for stale
components. When a component exceeds its deadline (or accumulates too many
heartbeat misses), the watchdog notifies the supervisor, which decides
whether to restart or isolate the component.

The watchdog also supports deadline enforcement for tasks (e.g. a workflow
run that exceeds its deadline is reported so the supervisor can abort it).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ai_company.runtime.heartbeat import HeartbeatManager

logger = logging.getLogger(__name__)

WatchdogCallback = Callable[[str, str], None]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Watchdog:
    """Detects stale components and task deadline overruns.

    Args:
        settings: The ``monitoring``/``watchdog`` config section dict.
        heartbeats: The shared HeartbeatManager instance.
        on_failure: Optional callback ``(component, reason)`` invoked for
            stale components / overrun tasks.
    """

    def __init__(
        self,
        settings: dict[str, Any] | None = None,
        heartbeats: HeartbeatManager | None = None,
        on_failure: WatchdogCallback | None = None,
    ) -> None:
        self.settings = settings or {}
        self.enabled = bool(self.settings.get("watchdog_enabled", True))
        self.interval_seconds = float(
            self.settings.get("watchdog_interval_seconds", 5.0)
        )
        self.deadline_seconds = float(self.settings.get("task_deadline_seconds", 300.0))
        self.heartbeats = heartbeats
        self.on_failure = on_failure
        self._tasks: dict[str, datetime] = {}
        self._task_deadlines: dict[str, float] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── Task deadlines ─────────────────────────────────────────────

    def track_task(self, task_id: str, deadline_seconds: float | None = None) -> None:
        """Start tracking a task's deadline."""
        with self._lock:
            self._tasks[task_id] = _utcnow()
            self._task_deadlines[task_id] = deadline_seconds or self.deadline_seconds

    def untrack_task(self, task_id: str) -> None:
        """Stop tracking a task (e.g. after successful completion)."""
        with self._lock:
            self._tasks.pop(task_id, None)
            self._task_deadlines.pop(task_id, None)

    def task_overrun(self, task_id: str, now: datetime | None = None) -> bool:
        """Return whether a tracked task has exceeded its deadline."""
        now = now or _utcnow()
        started = self._tasks.get(task_id)
        if started is None:
            return False
        deadline = self._task_deadlines.get(task_id, self.deadline_seconds)
        return (now - started).total_seconds() > deadline

    # ── Watchdog loop ──────────────────────────────────────────────

    def start(self) -> None:
        """Start the watchdog thread."""
        if not self.enabled:
            logger.info("Watchdog disabled — not starting")
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="runtime-watchdog",
                daemon=True,
            )
            self._thread.start()
            logger.info("Watchdog started (interval=%ss)", self.interval_seconds)

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the watchdog thread."""
        with self._lock:
            if self._thread is None:
                return
            self._stop_event.set()
            self._thread.join(timeout=timeout)
            self._thread = None
            logger.info("Watchdog stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.check()
            except Exception as exc:
                logger.error("Watchdog check failed: %s", exc)
            self._stop_event.wait(self.interval_seconds)

    # ── Checking ───────────────────────────────────────────────────

    def check(self, now: datetime | None = None) -> list[tuple[str, str]]:
        """Run one full check pass.

        Args:
            now: Clock override for deterministic tests.

        Returns:
            List of ``(component, reason)`` failures discovered.
        """
        failures: list[tuple[str, str]] = []
        if self.heartbeats is not None:
            failures.extend(self.heartbeats.check(now=now))
        for task_id in list(self._tasks):
            if self.task_overrun(task_id, now):
                failures.append((task_id, "deadline_exceeded"))
                logger.warning("Task %s exceeded its deadline", task_id)
                self.untrack_task(task_id)
                if self.on_failure is not None:
                    try:
                        self.on_failure(task_id, "deadline_exceeded")
                    except Exception as exc:
                        logger.error("Watchdog handler error: %s", exc)
        return failures

    # ── Inspection ─────────────────────────────────────────────────

    def is_running(self) -> bool:
        return bool(self._thread is not None and self._thread.is_alive())

    def tracked_tasks(self) -> list[str]:
        return list(self._tasks)

    def snapshot(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "running": self.is_running(),
            "tracked_tasks": len(self._tasks),
            "deadline_seconds": self.deadline_seconds,
        }
