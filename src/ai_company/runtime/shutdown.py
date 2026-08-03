"""Shutdown sequence — orderly runtime teardown.

Shuts the runtime down in dependency-safe order:

1. Notify listeners (publish ``runtime.stopping``).
2. Stop background workers (scheduler, watchdog, supervisor,
   heartbeat sender) **before** engines, so no monitoring thread
   probes a component while it is mid-teardown (fixes a teardown
   race that segfaulted when the supervisor/health monitor probed a
   read-model engine whose SQLite connection had already closed).
3. Stop engines in reverse-topological order (dependents stop before
   their dependencies) using the runtime dependency graph.
4. Stop managed processes.
5. Persist final state (phase STOPPED, stopped_at).
6. Finalize (phase STOPPED, publish ``runtime.stopped``).

Every step is recorded in a :class:`ShutdownSequence`. With ``force=True``
steps are attempted but failures do not abort the sequence.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ai_company.runtime.models import (
    RuntimePhase,
    ShutdownError,
    ShutdownSequence,
    ShutdownStep,
    ShutdownStepStatus,
    publish_runtime_event,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, ShutdownStepStatus, str], None]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ShutdownExecutor:
    """Executes the shutdown sequence.

    Args:
        engine: The RuntimeEngine being stopped (duck-typed: needs
            ``engines``, ``dependency_graph``, ``process_manager``,
            ``scheduler``, ``watchdog``, ``supervisor``, ``state_store``,
            ``event_bus``, ``lifecycle``, ``mark_stopped``).
        config: The ``shutdown`` config section dict.
        reason: Shutdown reason recorded in the sequence.
        force: When True, continue past step failures.
        on_progress: Optional ``(step_name, status, message)`` callback.
    """

    def __init__(
        self,
        engine: Any,
        config: dict[str, Any] | None = None,
        reason: str = "manual",
        force: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self.engine = engine
        self.config = config or {}
        self.reason = reason
        self.force = force
        self.on_progress = on_progress
        self.timeout_seconds = float(self.config.get("timeout_seconds", 60))
        self.sequence = ShutdownSequence(reason=reason, force=force)

    # ── Main entry ─────────────────────────────────────────────────

    def run(self) -> ShutdownSequence:
        """Execute the shutdown steps in order. Returns the sequence."""
        logger.info("Starting runtime shutdown (reason=%s)", self.reason)
        steps = [
            (
                "notify",
                "Notify listeners that shutdown is beginning",
                self._notify_step,
            ),
            ("stop_workers", "Stop background workers", self._stop_workers),
            (
                "stop_engines",
                "Stop engines (reverse dependency order)",
                self._stop_engines,
            ),
            ("stop_processes", "Stop managed processes", self._stop_processes),
            ("save_state", "Persist final runtime state", self._save_state),
            ("finalize", "Mark runtime stopped", self._finalize),
        ]
        for name, description, callable_ in steps:
            step = self._run_step(name, description, callable_)
            self.sequence.steps.append(step)
            if step.status is ShutdownStepStatus.FAILED and not self.force:
                self.sequence.completed_at = _utcnow()
                raise ShutdownError(f"Shutdown failed at step '{name}'")
        self.sequence.completed_at = _utcnow()
        self.sequence.success = all(
            s.status is ShutdownStepStatus.COMPLETED for s in self.sequence.steps
        )
        return self.sequence

    def _run_step(
        self,
        name: str,
        description: str,
        callable_: Callable[[], None],
    ) -> ShutdownStep:
        step = ShutdownStep(
            name=name,
            description=description,
            status=ShutdownStepStatus.RUNNING,
            started_at=_utcnow(),
        )
        started = time.monotonic()
        try:
            callable_()
            step.status = ShutdownStepStatus.COMPLETED
        except Exception as exc:
            step.status = ShutdownStepStatus.FAILED
            step.error = str(exc)
            logger.error("Shutdown step %s failed: %s", name, exc)
        step.completed_at = _utcnow()
        step.duration_ms = round((time.monotonic() - started) * 1000, 2)
        if self.on_progress is not None:
            try:
                self.on_progress(name, step.status, step.error or "ok")
            except Exception:
                pass
        return step

    # ── Steps ──────────────────────────────────────────────────────

    def _notify_step(self) -> None:
        self._publish("runtime.stopping", {"reason": self.reason})

    def _stop_engines(self) -> None:
        graph = getattr(self.engine, "dependency_graph", None)
        names: list[str] = []
        if graph is not None and hasattr(graph, "reverse_order"):
            try:
                names = list(graph.reverse_order())
            except Exception:
                names = []
        registered = getattr(self.engine, "engines", {})
        if not names:
            names = list(registered)
        stopped: list[str] = []
        for name in names:
            instance = registered.get(name) if isinstance(registered, dict) else None
            if instance is None:
                continue
            stop = getattr(instance, "stop", None)
            if callable(stop):
                stop()
            stopped.append(name)
        logger.info("Stopped %d engines: %s", len(stopped), ", ".join(stopped))

    def _stop_processes(self) -> None:
        process_manager = getattr(self.engine, "process_manager", None)
        if process_manager is None or not hasattr(process_manager, "stop_all"):
            return
        stopped = process_manager.stop_all()
        logger.info("Stopped %d processes", len(stopped))

    def _stop_workers(self) -> None:
        for attr in ("heartbeat_sender", "scheduler", "watchdog", "supervisor"):
            worker = getattr(self.engine, attr, None)
            if worker is None:
                continue
            stop = getattr(worker, "stop", None)
            if callable(stop):
                stop()

    def _save_state(self) -> None:
        state_store = getattr(self.engine, "state_store", None)
        if state_store is None:
            return
        set_stopped = getattr(state_store, "set_stopped", None)
        if callable(set_stopped):
            set_stopped()
        elif hasattr(state_store, "save"):
            state_store.save()

    def _finalize(self) -> None:
        mark_stopped = getattr(self.engine, "mark_stopped", None)
        if callable(mark_stopped):
            mark_stopped()
            return
        lifecycle = getattr(self.engine, "lifecycle", None)
        if lifecycle is not None and hasattr(lifecycle, "transition"):
            try:
                lifecycle.transition(RuntimePhase.STOPPED)
            except Exception:
                lifecycle.force(RuntimePhase.STOPPED)

    # ── Helpers ────────────────────────────────────────────────────

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event_bus = getattr(self.engine, "event_bus", None)
        publish_runtime_event(event_bus, event_type, payload, source="runtime.shutdown")
