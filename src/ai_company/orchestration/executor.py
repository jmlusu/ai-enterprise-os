"""Task executor for the Enterprise Orchestration Engine.

Runs individual pipeline tasks against the coordinator with retry,
backoff, timeout, and dry-run support. Returns a :class:`TaskResult`
rather than raising, so the pipeline runner can apply ``on_failure``
policies.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

from ai_company.orchestration.exceptions import EngineNotReadyError
from ai_company.orchestration.models import PipelineTask, RetryPolicy

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """Outcome of executing a single pipeline task."""

    task_id: str
    status: str = "failed"  # completed | failed | skipped
    output: Any = None
    error: str | None = None
    attempts: int = 1
    duration: float = 0.0
    retried: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskExecutor:
    """Executes tasks with retry and backoff via the coordinator.

    Args:
        coordinator: The coordinator that dispatches tasks to engines.
        default_retry: Default :class:`RetryPolicy` when a task does not
            declare its own.
        dry_run: When True, tasks are not dispatched; a dry-run result
            is returned instead.
    """

    def __init__(
        self,
        coordinator: Any | None = None,
        default_retry: RetryPolicy | None = None,
        dry_run: bool = False,
        logger: logging.Logger | None = None,
    ) -> None:
        self.coordinator = coordinator
        self.default_retry = default_retry or RetryPolicy()
        self.dry_run = dry_run
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    def execute_task(
        self,
        task: PipelineTask,
        context: dict[str, Any] | None = None,
    ) -> TaskResult:
        """Execute a task, retrying according to its retry policy.

        Returns a :class:`TaskResult`; never raises for task failures.
        """
        context = context or {}
        retry = task.retry or self.default_retry
        max_retries = max(0, retry.max_retries)
        last_error: str | None = None
        attempts = 0

        for attempt in range(max_retries + 1):
            attempts = attempt + 1
            start = time.time()
            try:
                output = self._dispatch(task, context)
                duration = time.time() - start
                self.logger.info(
                    "Task %s completed (attempt %d, %.3fs)",
                    task.id,
                    attempts,
                    duration,
                )
                return TaskResult(
                    task_id=task.id,
                    status="completed",
                    output=output,
                    attempts=attempts,
                    duration=duration,
                    retried=attempts > 1,
                )
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                duration = time.time() - start
                self.logger.warning(
                    "Task %s failed (attempt %d/%d): %s",
                    task.id,
                    attempts,
                    max_retries + 1,
                    exc,
                )
                if attempt >= max_retries or not self._retryable(exc, retry):
                    return TaskResult(
                        task_id=task.id,
                        status="failed",
                        error=last_error,
                        attempts=attempts,
                        duration=duration,
                        retried=attempts > 1,
                    )
                time.sleep(self._backoff(attempt, retry))

        return TaskResult(
            task_id=task.id,
            status="failed",
            error=last_error,
            attempts=attempts,
            retried=attempts > 1,
        )

    # ── Internals ─────────────────────────────────────────────────

    def _dispatch(self, task: PipelineTask, context: dict[str, Any]) -> Any:
        """Dispatch a task to the coordinator (or dry-run)."""
        if self.dry_run:
            return {
                "status": "dry_run",
                "task_id": task.id,
                "task_type": task.task_type,
                "engine": task.engine,
            }
        if self.coordinator is None:
            raise EngineNotReadyError("coordinator", "not configured")
        return self.coordinator.execute(task, context)

    @staticmethod
    def _retryable(exc: Exception, retry: RetryPolicy) -> bool:
        """Decide whether an exception may be retried."""
        if not retry.retryable_errors:
            return True
        return type(exc).__name__ in retry.retryable_errors

    @staticmethod
    def _backoff(attempt: int, retry: RetryPolicy) -> float:
        """Compute exponential backoff with jitter for an attempt."""
        delay = retry.backoff_base_seconds * (retry.backoff_multiplier**attempt)
        delay = min(delay, retry.max_backoff_seconds)
        if retry.backoff_base_seconds > 0:
            jitter = random.uniform(0, retry.backoff_base_seconds * 0.1)
            delay += jitter
        return max(0.0, delay)
