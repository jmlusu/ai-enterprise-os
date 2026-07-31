"""Unit tests for the runtime JobScheduler."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

import pytest

from ai_company.runtime.models import (
    JobKind,
    JobRegistrationError,
    JobStatus,
)
from ai_company.runtime.scheduler import JobScheduler

_NOW = datetime.now(UTC)


def test_register_one_time_runs_immediately_on_tick() -> None:
    executed: list[str] = []
    scheduler = JobScheduler(settings={"tick_interval_seconds": 0.01})
    scheduler.register(
        "hello",
        kind="one_time",
        handler=lambda job, runtime: executed.append(job.name),
    )
    assert scheduler.tick() == 1
    assert executed == ["hello"]
    assert scheduler.get("hello").status is JobStatus.COMPLETED
    # one_time jobs do not re-run
    assert scheduler.tick() == 0


def test_duplicate_registration_raises() -> None:
    scheduler = JobScheduler()
    scheduler.register("dup", kind="one_time")
    with pytest.raises(JobRegistrationError):
        scheduler.register("dup", kind="one_time")


def test_recurring_job_runs_multiple_times() -> None:
    executed: list[str] = []
    scheduler = JobScheduler(settings={"tick_interval_seconds": 0.01})
    scheduler.register(
        "recur",
        kind="recurring",
        interval_seconds=0.05,
        max_runs=3,
        handler=lambda job, runtime: executed.append(job.name),
    )
    time.sleep(0.2)
    ticks = scheduler.tick()
    # only runs when due; loop until max_runs reached
    guard = 0
    while scheduler.get("recur").run_count < 3 and guard < 50:
        scheduler.tick()
        time.sleep(0.02)
        guard += 1
    assert scheduler.get("recur").run_count == 3
    assert ticks >= 0
    assert len(executed) == 3


def test_cron_job_registers_with_croniter() -> None:
    scheduler = JobScheduler(settings={})
    task = scheduler.register(
        "cron-job",
        kind="cron",
        cron="0 7 * * *",
        handler=lambda job, runtime: None,
    )
    assert task.kind is JobKind.CRON
    assert task.next_run is not None


def test_dependency_job_waits_for_upstream() -> None:
    scheduler = JobScheduler(settings={})
    order: list[str] = []
    scheduler.register("up", kind="one_time", handler=lambda j, r: order.append("up"))
    scheduler.register(
        "down",
        kind="dependency",
        depends_on=["up"],
        handler=lambda j, r: order.append("down"),
    )
    assert scheduler.tick() == 1  # only "up" runs first
    assert order == ["up"]
    assert scheduler.tick() == 1  # dependency now satisfied
    assert order == ["up", "down"]


def test_event_job_not_run_by_tick() -> None:
    scheduler = JobScheduler(settings={})
    scheduler.register(
        "event-job",
        kind="event",
        event_type="something.happened",
        handler=lambda job, runtime: None,
    )
    assert scheduler.tick() == 0


def test_run_now_and_overlap_skip() -> None:
    entered = threading.Event()
    release = threading.Event()
    runs: list[str] = []

    def slow(job, runtime) -> None:
        runs.append(job.name)
        entered.set()
        release.wait(2)

    scheduler = JobScheduler(settings={})
    scheduler.register("slow", kind="one_time", handler=slow)

    thread = threading.Thread(target=lambda: scheduler.run_now("slow"))
    thread.start()
    assert entered.wait(2)
    # second call while running is skipped
    assert scheduler.run_now("slow") is False
    release.set()
    thread.join(2)
    assert runs == ["slow"]


def test_disabled_job_does_not_run() -> None:
    scheduler = JobScheduler(settings={})
    scheduler.register(
        "off",
        kind="one_time",
        enabled=False,
        handler=lambda job, runtime: None,
    )
    assert scheduler.tick() == 0
    assert scheduler.run_now("off") is False


def test_failed_job_records_error() -> None:
    def boom(job, runtime) -> None:
        raise ValueError("boom")

    scheduler = JobScheduler(settings={})
    scheduler.register("fails", kind="one_time", handler=boom)
    assert scheduler.run_now("fails") is False
    job = scheduler.get("fails")
    assert job.status is JobStatus.FAILED
    assert "boom" in job.error
    assert scheduler.failed_count() == 1


def test_unregister_removes_job() -> None:
    scheduler = JobScheduler(settings={})
    scheduler.register("bye", kind="one_time")
    assert scheduler.unregister("bye") is True
    assert scheduler.unregister("bye") is False
    assert scheduler.jobs() == []


def test_queue_sizes_and_snapshot() -> None:
    scheduler = JobScheduler(settings={})
    scheduler.register("a", kind="one_time")
    scheduler.register("b", kind="recurring", interval_seconds=60)
    sizes = scheduler.queue_sizes()
    assert sizes.get("pending", 0) == 2
    snapshot = scheduler.snapshot()
    assert snapshot["jobs"] == 2


def test_worker_thread_start_stop() -> None:
    scheduler = JobScheduler(settings={"tick_interval_seconds": 0.02})
    scheduler.start()
    assert scheduler.is_running()
    scheduler.stop()
    assert not scheduler.is_running()


def test_scheduled_at_future_not_due() -> None:
    scheduler = JobScheduler(settings={})
    future = (_NOW + timedelta(hours=1)).isoformat()
    scheduler.register("later", kind="one_time", scheduled_at=future)
    assert scheduler.tick() == 0
