"""Unit tests for the runtime process manager."""

from __future__ import annotations

import threading
import time

from ai_company.runtime.models import ProcessStatus
from ai_company.runtime.process_manager import ProcessManager


def _sleeper(stop: threading.Event) -> None:
    while not stop.is_set():
        time.sleep(0.01)


def test_register_and_start() -> None:
    manager = ProcessManager()
    stop = threading.Event()
    process = manager.register("worker", target=lambda: _sleeper(stop))
    assert process.status is ProcessStatus.CREATED
    manager.start("worker")
    process = manager.get_optional("worker")
    assert process is not None
    assert process.status is ProcessStatus.RUNNING
    stop.set()
    manager.stop_all()


def test_stop_joins_thread() -> None:
    manager = ProcessManager()
    stop = threading.Event()
    manager.register("worker", target=lambda: _sleeper(stop))
    manager.start("worker")
    manager.stop("worker")
    process = manager.get_optional("worker")
    assert process.status is ProcessStatus.STOPPED
    stop.set()


def test_restart_increments_count() -> None:
    manager = ProcessManager()
    stop = threading.Event()
    manager.register("worker", target=lambda: _sleeper(stop))
    manager.start("worker")
    process = manager.restart("worker")
    assert process.restart_count >= 1
    stop.set()
    manager.stop_all()


def test_unregister() -> None:
    manager = ProcessManager()
    manager.register("worker")
    assert manager.unregister("worker") is True
    assert manager.unregister("worker") is False
    assert manager.get_optional("worker") is None


def test_external_pid_registration() -> None:
    manager = ProcessManager()
    process = manager.register("external", pid=1234)
    assert process.pid == 1234


def test_status_and_alive_counts() -> None:
    manager = ProcessManager()
    stop = threading.Event()
    manager.register("worker", target=lambda: _sleeper(stop))
    assert manager.alive_count() == 0
    manager.start("worker")
    assert manager.alive_count() == 1
    assert manager.status("worker") is ProcessStatus.RUNNING
    stop.set()
    manager.stop_all()
    assert manager.alive_count() == 0


def test_snapshot_shape() -> None:
    manager = ProcessManager()
    manager.register("worker")
    snapshot = manager.snapshot()
    assert snapshot["alive"] == 0
    assert snapshot["processes"][0]["name"] == "worker"
    assert "restart_count" in snapshot["processes"][0]
