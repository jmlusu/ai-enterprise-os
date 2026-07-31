"""Process manager — owns the lifecycle of runtime worker processes.

Each managed process is tracked as a :class:`RuntimeProcess`. Thread-backed
processes run a target callable in a daemon thread; external processes can
be tracked by pid without a thread. The supervisor uses this manager to
restart failed processes.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ai_company.runtime.models import (
    EngineNotRegisteredError,
    ProcessStatus,
    RuntimeProcess,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ProcessManager:
    """Registry and lifecycle manager for runtime processes."""

    def __init__(self) -> None:
        self._processes: dict[str, RuntimeProcess] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._targets: dict[str, Callable[..., Any]] = {}
        # RLock: unregister() holds the lock and calls stop() which re-acquires it.
        self._lock = threading.RLock()

    # ── Registration ───────────────────────────────────────────────

    def register(
        self,
        name: str,
        target: Callable[..., Any] | None = None,
        pid: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeProcess:
        """Register a process (optionally with a target to run in a thread).

        Args:
            name: Unique process name.
            target: Callable executed when the process is started.
            pid: External pid to track (when no thread target is used).
            metadata: Optional metadata attached to the process.
        """
        with self._lock:
            existing = self._processes.get(name)
            if existing is not None and self.is_alive(name):
                logger.warning("Process %s is already running", name)
                return existing
            process = RuntimeProcess(name=name, pid=pid, metadata=metadata or {})
            if existing is not None:
                process.restart_count = existing.restart_count
            self._processes[name] = process
            self._targets[name] = target if target is not None else self._noop
            logger.info("Process %s registered", name)
            return process

    def unregister(self, name: str) -> bool:
        """Stop and remove a process."""
        with self._lock:
            if name not in self._processes:
                return False
            self.stop(name)
            self._processes.pop(name, None)
            self._threads.pop(name, None)
            self._targets.pop(name, None)
            return True

    @staticmethod
    def _noop() -> None:
        return None

    # ── Lifecycle ──────────────────────────────────────────────────

    def start(self, name: str) -> RuntimeProcess:
        """Start a registered process in a daemon thread."""
        with self._lock:
            process = self._get(name)
            if self.is_alive(name):
                return process
            target = self._targets.get(name, self._noop)
            thread = threading.Thread(
                target=target,
                name=f"runtime-{name}",
                daemon=True,
            )
            self._threads[name] = thread
            thread.start()
            process.status = ProcessStatus.RUNNING
            process.thread_alive = True
            process.started_at = _utcnow()
            process.stopped_at = None
            process.error = None
            logger.info("Process %s started (thread=%s)", name, thread.name)
            return process

    def stop(self, name: str, timeout: float = 5.0) -> RuntimeProcess:
        """Stop a process (join its thread with a timeout)."""
        with self._lock:
            process = self._get(name)
            thread = self._threads.get(name)
            process.status = ProcessStatus.STOPPED
            process.thread_alive = False
            process.stopped_at = _utcnow()
            if thread is not None and thread.is_alive():
                thread.join(timeout=timeout)
                self._threads.pop(name, None)
            logger.info("Process %s stopped", name)
            return process

    def restart(self, name: str, timeout: float = 5.0) -> RuntimeProcess:
        """Restart a process (stop, then start again)."""
        process = self._get(name)
        if self.is_alive(name):
            self.stop(name, timeout=timeout)
        process.restart_count += 1
        return self.start(name)

    def stop_all(self, timeout: float = 5.0) -> list[str]:
        """Stop every managed process. Returns stopped names."""
        stopped: list[str] = []
        for name in list(self._processes):
            self.stop(name, timeout=timeout)
            stopped.append(name)
        return stopped

    # ── Inspection ─────────────────────────────────────────────────

    def _get(self, name: str) -> RuntimeProcess:
        process = self._processes.get(name)
        if process is None:
            raise EngineNotRegisteredError(f"Process not registered: {name}")
        return process

    def get(self, name: str) -> RuntimeProcess:
        """Return a process record (raises if unknown)."""
        return self._get(name)

    def get_optional(self, name: str) -> RuntimeProcess | None:
        """Return a process record, or None when unknown."""
        return self._processes.get(name)

    def is_alive(self, name: str) -> bool:
        """Return whether a process's thread is currently alive."""
        thread = self._threads.get(name)
        return bool(thread is not None and thread.is_alive())

    def status(self, name: str) -> ProcessStatus:
        """Return a process's status (live thread wins)."""
        process = self._get(name)
        if self.is_alive(name):
            return ProcessStatus.RUNNING
        return process.status

    def list_processes(self) -> list[RuntimeProcess]:
        """Return all process records."""
        return list(self._processes.values())

    def names(self) -> list[str]:
        """Return all process names."""
        return list(self._processes)

    def alive_count(self) -> int:
        """Return the number of live process threads."""
        return sum(1 for name in self._processes if self.is_alive(name))

    def snapshot(self) -> dict[str, Any]:
        """Return a compact snapshot for diagnostics."""
        return {
            "processes": [
                {
                    "name": p.name,
                    "status": p.status.value,
                    "restart_count": p.restart_count,
                }
                for p in self._processes.values()
            ],
            "alive": self.alive_count(),
        }
