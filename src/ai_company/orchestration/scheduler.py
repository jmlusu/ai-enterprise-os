"""Scheduler for orchestration plans.

Supports four schedule modes:

- ``immediate`` — run as soon as possible.
- ``scheduled`` — run at an absolute timestamp.
- ``recurring`` — run every ``interval_seconds`` up to ``max_runs``.
- ``dependency`` — run after the plans listed in ``depends_on`` complete.

The scheduler keeps a plan registry, computes due plans, and optionally
runs a background worker thread that invokes a due-plan callback.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from ai_company.orchestration.models import OrchestrationPlan, ScheduleMode

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class OrchestrationScheduler:
    """Registers plans and computes which are due for execution.

    Args:
        settings: Scheduler settings (the ``scheduler`` section of
            config/orchestration/scheduler.yaml).
    """

    def __init__(
        self,
        settings: dict[str, Any] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings or {}
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._plans: dict[str, OrchestrationPlan] = {}
        self._last_run: dict[str, datetime] = {}
        self._completed: set[str] = set()
        self._scheduled_at: dict[str, datetime] = {}
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.on_due: Callable[[OrchestrationPlan], None] | None = None

    # ── Registration ──────────────────────────────────────────────

    def register(self, plan: OrchestrationPlan) -> None:
        """Register a plan; computes its trigger time."""
        self._plans[plan.id] = plan
        now = _utcnow()
        mode = plan.schedule_mode
        if mode == ScheduleMode.SCHEDULED:
            self._scheduled_at[plan.id] = plan.scheduled_at or now
        elif mode == ScheduleMode.IMMEDIATE:
            self._scheduled_at[plan.id] = now
        elif mode == ScheduleMode.RECURRING:
            self._scheduled_at[plan.id] = now
        else:  # dependency mode waits for upstream plans
            self._scheduled_at.pop(plan.id, None)
        self.logger.info("Plan %s registered (mode=%s)", plan.id, mode.value)

    def unregister(self, plan_id: str) -> bool:
        """Remove a plan from the scheduler."""
        self._plans.pop(plan_id, None)
        self._last_run.pop(plan_id, None)
        self._scheduled_at.pop(plan_id, None)
        return True

    def schedule(self, plan: OrchestrationPlan) -> None:
        """Register a plan for later execution (scheduled/recurring/dependency)."""
        self.register(plan)

    # ── Run bookkeeping ───────────────────────────────────────────

    def mark_run(self, plan: OrchestrationPlan, now: datetime | None = None) -> None:
        """Record that a plan was executed; advances recurring counters.

        Args:
            plan: The plan that was executed.
            now: Timestamp to record (defaults to the current wall clock).
                Injectable so callers can drive time deterministically,
                mirroring :meth:`due_plans`.
        """
        self._last_run[plan.id] = now or _utcnow()
        plan.run_count += 1
        self.logger.debug("Plan %s marked as run (count=%d)", plan.id, plan.run_count)

    def notify_completed(self, plan_id: str) -> None:
        """Record that a plan finished (unblocks dependency-mode plans)."""
        self._completed.add(plan_id)
        self.logger.debug("Plan %s completed notification", plan_id)

    # ── Due-plan computation ──────────────────────────────────────

    def due_plans(self, now: datetime | None = None) -> list[OrchestrationPlan]:
        """Return registered plans that are due for execution.

        Immediate plans are due once; scheduled plans when their trigger
        time passes; recurring plans on each interval; dependency plans
        when all upstream plans have completed.
        """
        now = now or _utcnow()
        due: list[OrchestrationPlan] = []

        for plan in self._plans.values():
            if self._is_due(plan, now):
                due.append(plan)
        return due

    def _is_due(self, plan: OrchestrationPlan, now: datetime) -> bool:
        mode = plan.schedule_mode
        last_run = self._last_run.get(plan.id)

        if mode == ScheduleMode.IMMEDIATE:
            return last_run is None

        if mode == ScheduleMode.SCHEDULED:
            if last_run is not None:
                return False
            trigger = self._scheduled_at.get(plan.id)
            return trigger is not None and now >= trigger

        if mode == ScheduleMode.RECURRING:
            if plan.max_runs and plan.run_count >= plan.max_runs:
                return False
            interval = plan.interval_seconds or float(
                self.settings.get("recurring", {}).get("default_interval_seconds", 3600)
            )
            if last_run is None:
                return True
            return now >= last_run + timedelta(seconds=interval)

        if mode == ScheduleMode.DEPENDENCY:
            deps = plan.depends_on
            if not deps:
                return last_run is None
            missing = [d for d in deps if d not in self._completed]
            if missing:
                return False
            return last_run is None

        return False

    def pending_plans(self) -> list[OrchestrationPlan]:
        """Return registered plans that have not run yet."""
        return [plan for plan in self._plans.values() if plan.id not in self._last_run]

    def is_completed(self, plan_id: str) -> bool:
        """Return whether a plan has completed."""
        return plan_id in self._completed

    # ── Background worker ─────────────────────────────────────────

    def start(self) -> None:
        """Start the background worker thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="orchestration-scheduler",
            daemon=True,
        )
        self._thread.start()
        self.logger.info("Scheduler worker started")

    def stop(self) -> None:
        """Stop the background worker thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self.logger.info("Scheduler worker stopped")

    def run_once(self, now: datetime | None = None) -> list[OrchestrationPlan]:
        """Execute the due-plan callback for all due plans (test-friendly)."""
        due = self.due_plans(now)
        for plan in due:
            if self.on_due is not None:
                self.on_due(plan)
        return due

    def _worker_loop(self) -> None:
        interval = float(self.settings.get("worker_interval_seconds", 5.0))
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:  # worker must never die
                self.logger.error("Scheduler worker error: %s", exc)
            self._stop_event.wait(interval)
