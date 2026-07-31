"""Execution metrics collection for the orchestration engine.

The :class:`MetricsCollector` accumulates engine-level counters across
runs and merges per-run :class:`ExecutionMetrics` into a snapshot that
is exposed on :class:`EngineStatus`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ai_company.orchestration.models import ExecutionMetrics

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Accumulates orchestration metrics across pipeline runs."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config or {}
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._metrics = ExecutionMetrics()

    def reset(self) -> None:
        """Reset all accumulated metrics."""
        self._metrics = ExecutionMetrics()

    def merge(self, metrics: ExecutionMetrics) -> None:
        """Merge a run's metrics into the aggregate totals."""
        current = self._metrics
        current.tasks_total += metrics.tasks_total
        current.tasks_completed += metrics.tasks_completed
        current.tasks_failed += metrics.tasks_failed
        current.tasks_skipped += metrics.tasks_skipped
        current.retries_total += metrics.retries_total
        current.checkpoints_created += metrics.checkpoints_created
        current.rollbacks_executed += metrics.rollbacks_executed
        current.recoveries_performed += metrics.recoveries_performed
        current.duration_seconds += metrics.duration_seconds
        if current.started_at is None or (
            metrics.started_at and metrics.started_at < current.started_at
        ):
            current.started_at = metrics.started_at or current.started_at
        if metrics.completed_at and (
            current.completed_at is None or metrics.completed_at > current.completed_at
        ):
            current.completed_at = metrics.completed_at

    def snapshot(self) -> ExecutionMetrics:
        """Return a copy of the current aggregate metrics."""
        return self._metrics.model_copy(deep=True)

    def to_dict(self) -> dict[str, Any]:
        """Return the aggregate metrics as a JSON-safe dict."""
        return self._metrics.model_dump(mode="json")

    def record_checkpoint(self) -> None:
        """Increment the checkpoint counter."""
        self._metrics.checkpoints_created += 1

    def record_rollback(self) -> None:
        """Increment the rollback counter."""
        self._metrics.rollbacks_executed += 1

    def record_recovery(self) -> None:
        """Increment the recovery counter."""
        self._metrics.recoveries_performed += 1

    def mark_started(self, at: datetime | None = None) -> None:
        """Mark the engine start time."""
        self._metrics.started_at = at or datetime.now(UTC)
