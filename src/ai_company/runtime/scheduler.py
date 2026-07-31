"""Scheduler — recurring job execution for the runtime.

Supports five job kinds (see :class:`RuntimeTask`):

* ``one_time`` — execute once at ``scheduled_at`` (or immediately).
* ``recurring`` — execute every ``interval_seconds`` up to ``max_runs``.
* ``cron`` — execute on a cron expression (via croniter when available).
* ``dependency`` — execute when every job in ``depends_on`` completed.
* ``event`` — execute when the named event fires on the event bus.

Jobs execute a registered callable ``(job, runtime) -> result`` in the
calling thread (the worker thread for ticks, the event bus thread for
event jobs). Overlapping executions of the same job are skipped.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from ai_company.runtime.models import (
    JobKind,
    JobRegistrationError,
    JobStatus,
    RuntimeTask,
)

logger = logging.getLogger(__name__)

JobHandler = Callable[[RuntimeTask, Any], Any]

try:  # croniter is an optional dependency
    from croniter import croniter

    _HAS_CRONITER = True
except Exception:  # pragma: no cover
    _HAS_CRONITER = False


def _utcnow() -> datetime:
    return datetime.now(UTC)


class JobScheduler:
    """Schedules and executes runtime jobs.

    Args:
        settings: The ``scheduler`` config section dict.
        runtime: The RuntimeEngine (or any object exposing ``event_bus``)
            passed to handlers as the second argument.
        executor: Optional callable ``fn(job, runtime)`` executed for jobs
            without a dedicated handler.
    """

    def __init__(
        self,
        settings: dict[str, Any] | None = None,
        runtime: Any | None = None,
        executor: Callable[[RuntimeTask, Any], Any] | None = None,
    ) -> None:
        self.settings = settings or {}
        self.runtime = runtime
        self.executor = executor
        self.interval_seconds = float(self.settings.get("tick_interval_seconds", 1.0))
        self._jobs: dict[str, RuntimeTask] = {}
        self._handlers: dict[str, JobHandler] = {}
        self._next_run: dict[str, datetime] = {}
        self._running: set[str] = set()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._executed = 0
        self._failed = 0

    # ── Job registration ───────────────────────────────────────────

    def register(
        self,
        name: str,
        kind: JobKind | str = JobKind.ONE_TIME,
        handler: JobHandler | None = None,
        scheduled_at: str | datetime | None = None,
        interval_seconds: float | None = None,
        cron: str | None = None,
        depends_on: list[str] | None = None,
        event_type: str | None = None,
        params: dict[str, Any] | None = None,
        max_runs: int = 0,
        enabled: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTask:
        """Register a job.

        Args:
            name: Unique job name.
            kind: Job kind (one_time/recurring/cron/dependency/event).
            handler: Callable ``(job, runtime)``; falls back to the shared
                executor, then to a no-op.
            scheduled_at: Start time for one_time jobs (ISO string or
                datetime).
            interval_seconds: Interval for recurring jobs.
            cron: Cron expression for cron jobs (requires croniter).
            depends_on: Upstream job names for dependency jobs.
            event_type: Event type to subscribe to for event jobs.
            params: Fixed params passed to the handler.
            max_runs: Maximum executions (0 = unlimited).
            enabled: Whether the job can run.
            metadata: Optional metadata.
        """
        with self._lock:
            if name in self._jobs:
                raise JobRegistrationError(f"Job already registered: {name}")
            kind_enum = JobKind(kind)
            if kind_enum is JobKind.CRON and not _HAS_CRONITER:
                raise JobRegistrationError(
                    "croniter is required for cron jobs; install it or "
                    "use a recurring job"
                )
            task = RuntimeTask(
                name=name,
                kind=kind_enum,
                params=params or {},
                scheduled_at=_coerce_datetime(scheduled_at),
                interval_seconds=interval_seconds,
                cron=cron,
                depends_on=depends_on or [],
                event_type=event_type,
                max_runs=max_runs,
                enabled=enabled,
                metadata=metadata or {},
            )
            self._jobs[name] = task
            self._handlers[name] = (
                handler if handler is not None else self._default_handler
            )
            self._schedule_initial(task)
            logger.info("Job registered: %s (%s)", name, kind_enum.value)
            if event_type:
                self._subscribe_to_event(name, event_type)
            return task

    def _default_handler(self, job: RuntimeTask, runtime: Any) -> Any:
        if self.executor is not None:
            return self.executor(job, runtime)
        return None

    def _schedule_initial(self, task: RuntimeTask) -> None:
        if task.scheduled_at is not None:
            self._next_run[task.name] = task.scheduled_at
            task.next_run = task.scheduled_at
        elif task.kind in (JobKind.RECURRING, JobKind.CRON, JobKind.ONE_TIME):
            self._next_run[task.name] = _utcnow()
            task.next_run = self._next_run[task.name]
        elif task.kind is JobKind.DEPENDENCY:
            self._next_run[task.name] = _utcnow()
            task.next_run = self._next_run[task.name]

    def _subscribe_to_event(self, name: str, event_type: str) -> None:
        bus = getattr(self.runtime, "event_bus", None)
        if bus is None or not hasattr(bus, "subscribe"):
            logger.warning(
                "Event job %s cannot subscribe (no event bus on runtime)",
                name,
            )
            return

        def handler(payload: dict[str, Any]) -> None:
            self.run_now(name, params=payload or {})

        try:
            bus.subscribe(
                name=f"scheduler-{name}",
                handler=handler,
                event_types=[event_type],
            )
        except Exception as exc:
            logger.warning("Could not subscribe scheduler to %s: %s", event_type, exc)

    def unregister(self, name: str) -> bool:
        """Remove a job."""
        with self._lock:
            existed = name in self._jobs
            self._jobs.pop(name, None)
            self._handlers.pop(name, None)
            self._next_run.pop(name, None)
            self._running.discard(name)
            return existed

    # ── Execution ──────────────────────────────────────────────────

    def run_now(self, name: str, params: dict[str, Any] | None = None) -> bool:
        """Execute a job immediately (in the calling thread).

        Returns:
            True when the job executed (or completed); False when it was
            skipped (already running or disabled).
        """
        job = self._jobs.get(name)
        if job is None:
            raise JobRegistrationError(f"Unknown job: {name}")
        if not job.enabled:
            return False
        with self._lock:
            if name in self._running:
                logger.warning("Job %s already running — skipping overlap", name)
                return False
            self._running.add(name)
        job.status = JobStatus.RUNNING
        try:
            merged = dict(job.params)
            merged.update(params or {})
            handler = self._handlers[name]
            handler(job, self.runtime)
            job.status = JobStatus.COMPLETED
            job.last_run = _utcnow()
            job.run_count += 1
            self._executed += 1
            return True
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.last_run = _utcnow()
            job.run_count += 1
            self._failed += 1
            logger.exception("Job %s failed", name)
            return False
        finally:
            self._running.discard(name)

    # ── Scheduling logic ───────────────────────────────────────────

    def _due(self, job: RuntimeTask) -> bool:
        name = job.name
        if not job.enabled:
            return False
        if job.max_runs > 0 and job.run_count >= job.max_runs:
            return False
        if job.kind is JobKind.DEPENDENCY:
            for dep in job.depends_on:
                dep_job = self._jobs.get(dep)
                if dep_job is None or dep_job.status is not JobStatus.COMPLETED:
                    return False
            return True
        next_run = self._next_run.get(name)
        if next_run is None:
            return False
        return _utcnow() >= next_run

    def _mark_run(self, job: RuntimeTask) -> None:
        now = _utcnow()
        if job.kind is JobKind.RECURRING:
            interval = float(job.interval_seconds or 0.0)
            next_run = self._next_run.get(job.name, now)
            while next_run <= now:
                next_run += timedelta(seconds=interval)
            self._next_run[job.name] = next_run
            job.next_run = next_run
        elif job.kind is JobKind.CRON:
            if _HAS_CRONITER and job.cron:
                try:
                    self._next_run[job.name] = croniter(job.cron, now).get_next(
                        datetime
                    )
                except Exception:
                    self._next_run[job.name] = now + timedelta(
                        seconds=self.interval_seconds
                    )
            else:
                self._next_run[job.name] = now + timedelta(
                    seconds=self.interval_seconds
                )
            job.next_run = self._next_run[job.name]
        elif job.kind is JobKind.DEPENDENCY:
            # re-evaluate when upstream jobs run again
            self._next_run.pop(job.name, None)
            job.next_run = None
        else:
            self._next_run.pop(job.name, None)
            job.next_run = None

    def tick(self) -> int:
        """Evaluate due jobs and execute them. Returns count executed."""
        with self._lock:
            due_names = [
                name
                for name, job in self._jobs.items()
                if job.kind is not JobKind.EVENT and self._due(job)
            ]
        executed = 0
        for name in due_names:
            job = self._jobs.get(name)
            if job is None:
                continue
            if self.run_now(name):
                executed += 1
            self._mark_run(job)
        return executed

    # ── Worker thread ──────────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduler worker thread."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="runtime-scheduler",
                daemon=True,
            )
            self._thread.start()
            logger.info("Scheduler started (tick=%ss)", self.interval_seconds)

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the scheduler worker thread."""
        with self._lock:
            if self._thread is None:
                return
            self._stop_event.set()
            self._thread.join(timeout=timeout)
            self._thread = None
            logger.info("Scheduler stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception as exc:
                logger.error("Scheduler tick failed: %s", exc)
            self._stop_event.wait(self.interval_seconds)

    def is_running(self) -> bool:
        return bool(self._thread is not None and self._thread.is_alive())

    # ── Inspection ─────────────────────────────────────────────────

    def jobs(self) -> list[RuntimeTask]:
        """Return all registered jobs."""
        return list(self._jobs.values())

    def get(self, name: str) -> RuntimeTask | None:
        """Return a job by name."""
        return self._jobs.get(name)

    def executed_count(self) -> int:
        return self._executed

    def failed_count(self) -> int:
        return self._failed

    def queue_sizes(self) -> dict[str, int]:
        """Return a snapshot of job counts per status."""
        sizes: dict[str, int] = {}
        for job in self._jobs.values():
            key = job.status.value
            sizes[key] = sizes.get(key, 0) + 1
        return sizes

    def snapshot(self) -> dict[str, Any]:
        return {
            "running": self.is_running(),
            "jobs": len(self._jobs),
            "executed": self._executed,
            "failed": self._failed,
            "queue": self.queue_sizes(),
        }


def _coerce_datetime(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
