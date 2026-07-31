"""Monitoring hooks for the orchestration engine.

The :class:`Monitor` subscribes to pipeline lifecycle callbacks from the
runner, merges run metrics into the aggregate collector, and records a
lightweight event trail on the execution state.
"""

from __future__ import annotations

import logging
from typing import Any

from ai_company.orchestration.metrics import MetricsCollector
from ai_company.orchestration.models import ExecutionMetrics, OrchestrationPlan

logger = logging.getLogger(__name__)


class Monitor:
    """Records metrics and event trails for pipeline runs.

    Args:
        config: Monitoring config (see config/orchestration/monitoring.yaml).
        collector: Aggregate metrics collector.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        collector: MetricsCollector | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config or {}
        self.collector = collector or MetricsCollector(config=config)
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    # ── Lifecycle callbacks (called by PipelineRunner) ────────────

    def on_pipeline_started(
        self,
        plan: OrchestrationPlan,
        state: Any,
    ) -> None:
        if not self.enabled:
            return
        self._append_event(state, "pipeline.started")

    def on_pipeline_finished(
        self,
        plan: OrchestrationPlan,
        state: Any,
        metrics: ExecutionMetrics,
    ) -> None:
        if not self.enabled:
            return
        self._append_event(state, "pipeline.completed")
        self.collector.merge(metrics)

    def on_task_started(
        self,
        plan: OrchestrationPlan,
        state: Any,
        task_id: str,
    ) -> None:
        if not self.enabled:
            return
        self._append_event(state, f"task.started:{task_id}")

    def on_task_finished(
        self,
        plan: OrchestrationPlan,
        state: Any,
        task_id: str,
        result: Any,
    ) -> None:
        if not self.enabled:
            return
        suffix = (
            "completed" if getattr(result, "status", "") == "completed" else "failed"
        )
        self._append_event(state, f"task.{suffix}:{task_id}")

    # ── Helpers ───────────────────────────────────────────────────

    def _append_event(self, state: Any, event: str) -> None:
        try:
            events = state.metadata.setdefault("events", [])
            events.append(event)
        except Exception:
            pass
