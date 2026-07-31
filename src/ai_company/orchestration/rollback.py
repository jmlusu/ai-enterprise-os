"""Rollback management for the Enterprise Orchestration Engine.

Tasks that declare a ``rollback_action`` register an undo handler when
they complete successfully. On failure, :class:`RollbackManager` executes
those handlers in reverse completion order, producing a
:class:`RollbackPlan` that is stored with the execution record.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ai_company.orchestration.exceptions import RollbackError
from ai_company.orchestration.models import (
    OrchestrationPlan,
    Pipeline,
    RollbackPlan,
    RollbackStep,
)

logger = logging.getLogger(__name__)


class RollbackManager:
    """Registers and executes task rollback handlers."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config or {}
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._handlers: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._rollback_plans: dict[str, RollbackPlan] = {}

    # ── Handler registration ──────────────────────────────────────

    def register_handler(
        self,
        task_id: str,
        action: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Register an undo handler for a completed task."""
        self._handlers[task_id] = {
            "action": action,
            "params": params or {},
        }
        if task_id not in self._order:
            self._order.append(task_id)
        self.logger.debug("Rollback handler registered for task %s", task_id)

    def unregister_handler(self, task_id: str) -> bool:
        """Remove the undo handler of a task."""
        if self._handlers.pop(task_id, None) is not None:
            if task_id in self._order:
                self._order.remove(task_id)
            return True
        return False

    def list_handlers(self) -> list[str]:
        """Return task ids with registered undo handlers (execution order)."""
        return list(self._order)

    def has_handlers(self) -> bool:
        """Return whether any undo handlers are registered."""
        return bool(self._handlers)

    def clear_handlers(self) -> None:
        """Drop all registered undo handlers."""
        self._handlers.clear()
        self._order.clear()

    # ── Rollback plans ────────────────────────────────────────────

    def get_rollback_plan(self, plan_id: str) -> RollbackPlan | None:
        """Return the stored rollback plan of a plan run."""
        return self._rollback_plans.get(plan_id)

    def create_rollback_plan(
        self,
        pipeline: Pipeline,
        plan_id: str,
        reason: str,
    ) -> RollbackPlan:
        """Build a rollback plan from registered handlers."""
        steps = [
            RollbackStep(
                task_id=task_id,
                action=self._handlers[task_id]["action"],
            )
            for task_id in reversed(self._order)
        ]
        rollback = RollbackPlan(
            pipeline_id=pipeline.id,
            plan_id=plan_id,
            reason=reason,
            steps=steps,
        )
        self._rollback_plans[plan_id] = rollback
        return rollback

    def execute_rollback(
        self,
        plan: OrchestrationPlan,
        reason: str,
        undo_func: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> RollbackPlan:
        """Execute registered undo handlers in reverse order.

        Args:
            plan: The failed plan being rolled back.
            reason: Human-readable reason for the rollback.
            undo_func: Optional callable ``(task_id, action, params)``
                that performs the actual undo at the target engine. When
                None, steps are recorded as executed without a side effect.

        Returns:
            The completed :class:`RollbackPlan`.

        Raises:
            RollbackError: If no handlers are registered.
        """
        if not self.has_handlers():
            raise RollbackError(f"No rollback handlers registered for plan {plan.id}")

        rollback = self.create_rollback_plan(plan.pipeline, plan.id, reason)

        for step in rollback.steps:
            handler = self._handlers.get(step.task_id, {})
            try:
                if undo_func is not None:
                    undo_func(
                        step.task_id,
                        str(handler.get("action", "")),
                        dict(handler.get("params", {})),
                    )
                step.status = "executed"
                step.executed_at = datetime.now(UTC)
                self.logger.info(
                    "Rollback step executed: %s (%s)",
                    step.task_id,
                    step.action,
                )
            except Exception as exc:
                step.status = "failed"
                step.error = f"{type(exc).__name__}: {exc}"
                self.logger.error(
                    "Rollback step failed: %s (%s): %s",
                    step.task_id,
                    step.action,
                    exc,
                )

        failed_steps = [s for s in rollback.steps if s.status == "failed"]
        rollback.status = "completed" if not failed_steps else "failed"
        rollback.completed_at = datetime.now(UTC)
        self.clear_handlers()
        return rollback
