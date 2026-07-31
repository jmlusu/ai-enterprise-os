"""Notifications for orchestration lifecycle events.

The :class:`Notifier` publishes ``pipeline.*`` and ``task.*`` events to
the Event Bus, respecting the notification config (enabled channels,
event allow-lists, correlation ids). It is a no-op when the Event Bus is
not registered.
"""

from __future__ import annotations

import logging
from typing import Any

from ai_company.orchestration.models import ExecutionMetrics, OrchestrationPlan

logger = logging.getLogger(__name__)


class Notifier:
    """Publishes lifecycle events to the Event Bus.

    Args:
        config: Notification config (see config/orchestration/notifications.yaml).
        event_bus: The Event Bus instance (optional).
        source: Source name attached to published events.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        event_bus: Any | None = None,
        source: str = "orchestrator",
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config or {}
        self.event_bus = event_bus
        self.source = source
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    # ── Configuration helpers ─────────────────────────────────────

    @property
    def enabled(self) -> bool:
        if not self.config.get("enabled", True):
            return False
        channels = self.config.get("channels", {})
        return bool(channels.get("event_bus", True))

    def event_enabled(self, event_type: str) -> bool:
        """Return whether an event type is allowed by configuration."""
        if not self.enabled:
            return False
        allowed = set(self.config.get("pipeline_events", []))
        allowed.update(self.config.get("task_events", []))
        return not allowed or event_type in allowed

    # ── Pipeline events ───────────────────────────────────────────

    def pipeline_started(self, plan: OrchestrationPlan, state: Any) -> None:
        self._publish(
            "pipeline.started",
            plan,
            state,
            {"stage": state.current_stage_id},
        )

    def pipeline_completed(
        self,
        plan: OrchestrationPlan,
        state: Any,
        metrics: ExecutionMetrics,
    ) -> None:
        self._publish(
            "pipeline.completed",
            plan,
            state,
            {
                "duration_seconds": metrics.duration_seconds,
                "tasks_completed": metrics.tasks_completed,
                "tasks_failed": metrics.tasks_failed,
            },
        )

    def pipeline_failed(self, plan: OrchestrationPlan, state: Any) -> None:
        self._publish(
            "pipeline.failed",
            plan,
            state,
            {"error": state.error, "task": state.current_task_id},
        )

    def pipeline_cancelled(self, plan: OrchestrationPlan, state: Any) -> None:
        self._publish("pipeline.cancelled", plan, state, {})

    def pipeline_recovered(self, plan: OrchestrationPlan, state: Any) -> None:
        self._publish(
            "pipeline.recovered",
            plan,
            state,
            {"checkpoint": state.recovered_from},
        )

    # ── Task events ───────────────────────────────────────────────

    def task_started(self, plan: OrchestrationPlan, state: Any, task_id: str) -> None:
        self._publish(
            "task.started",
            plan,
            state,
            {
                "task_id": task_id,
                "attempt": state.attempts.get(task_id, 1),
                "stage": state.current_stage_id,
            },
        )

    def task_completed(
        self,
        plan: OrchestrationPlan,
        state: Any,
        task_id: str,
        result: Any,
    ) -> None:
        self._publish(
            "task.completed",
            plan,
            state,
            {
                "task_id": task_id,
                "duration_seconds": getattr(result, "duration", 0.0),
                "attempts": getattr(result, "attempts", 1),
            },
        )

    def task_failed(
        self,
        plan: OrchestrationPlan,
        state: Any,
        task_id: str,
        result: Any,
    ) -> None:
        self._publish(
            "task.failed",
            plan,
            state,
            {
                "task_id": task_id,
                "error": getattr(result, "error", "unknown"),
                "attempts": getattr(result, "attempts", 1),
            },
        )

    def task_skipped(self, plan: OrchestrationPlan, state: Any, task_id: str) -> None:
        self._publish(
            "task.skipped",
            plan,
            state,
            {"task_id": task_id},
        )

    # ── Internals ─────────────────────────────────────────────────

    def _publish(
        self,
        event_type: str,
        plan: OrchestrationPlan,
        state: Any,
        extra: dict[str, Any],
    ) -> None:
        if self.event_bus is None:
            return
        if not self.event_enabled(event_type):
            return
        try:
            from ai_company.events.models import EventPriority, EventType

            payload: dict[str, Any] = {
                "plan_id": plan.id,
                "pipeline_id": plan.pipeline.id,
                "pipeline": plan.pipeline.name,
                "status": getattr(state, "status", "unknown"),
                **extra,
            }
            self.event_bus.publish_event(
                event_type=EventType(event_type),
                payload=payload,
                source=self.source,
                priority=EventPriority.NORMAL,
                correlation_id=getattr(state, "correlation_id", None),
            )
        except Exception as exc:
            self.logger.warning("Failed to publish %s event: %s", event_type, exc)
