"""Recovery for failed or interrupted pipeline runs.

Recovery follows the configured action sequence:

1. **checkpoint_restore** — resume from the latest checkpoint.
2. **rollback** — undo completed tasks in reverse order.
3. **retry** — re-run failed tasks (or the whole run from a checkpoint).

The :class:`RecoveryManager` composes these steps and returns a
:class:`RecoveryResult` plus the checkpoint (if any) the engine should
resume from.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ai_company.orchestration.exceptions import RecoveryError
from ai_company.orchestration.models import (
    Checkpoint,
    ExecutionState,
    OrchestrationPlan,
    RecoveryAction,
    RecoveryResult,
)

logger = logging.getLogger(__name__)


class RecoveryManager:
    """Drives the recovery sequence for a failed plan run.

    Args:
        config: Recovery config (see config/orchestration/recovery.yaml).
        checkpoint_manager: Manager providing the latest checkpoint.
        rollback_manager: Manager providing undo handlers.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        checkpoint_manager: Any | None = None,
        rollback_manager: Any | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config or {}
        self.checkpoint_manager = checkpoint_manager
        self.rollback_manager = rollback_manager
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    # ── Public API ────────────────────────────────────────────────

    def recover(
        self,
        plan: OrchestrationPlan,
        state: ExecutionState,
        reason: str,
        undo_func: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> tuple[RecoveryResult, Checkpoint | None]:
        """Attempt recovery for a failed plan run.

        Returns:
            A tuple of ``(RecoveryResult, checkpoint)`` where checkpoint
            is the point to resume from (or None to re-run from scratch).

        Raises:
            RecoveryError: If recovery is disabled or impossible.
        """
        if not self.config.get("enabled", True):
            raise RecoveryError("Recovery is disabled by configuration")

        result = RecoveryResult(plan_id=plan.id)
        resume_checkpoint: Checkpoint | None = None
        strategy = self.config.get("strategy", "checkpoint_first")
        action_sequence = list(
            self.config.get(
                "action_sequence",
                ["checkpoint_restore", "rollback", "retry"],
            )
        )
        if strategy == "retry_only":
            action_sequence = ["retry"]
        elif strategy == "rollback_then_retry":
            action_sequence = ["rollback", "retry"]

        for action in action_sequence:
            if RecoveryAction(action) == RecoveryAction.CHECKPOINT_RESTORE:
                if self.config.get("restore_latest_checkpoint", True):
                    resume_checkpoint = self._restore_latest(plan, result)
            elif RecoveryAction(action) == RecoveryAction.ROLLBACK:
                self._rollback(plan, state, reason, result, undo_func)
            elif RecoveryAction(action) == RecoveryAction.RETRY:
                if self.config.get("retry_failed_tasks", True):
                    result.actions_taken.append(RecoveryAction.RETRY)

        result.success = bool(result.actions_taken) or resume_checkpoint is not None
        if not result.success:
            result.message = (
                "No recovery actions available (no checkpoint, handlers, "
                "or retry policy)"
            )
        else:
            result.message = (
                "Recovery prepared: "
                + ", ".join(a.value for a in result.actions_taken)
                + (
                    f" from checkpoint {resume_checkpoint.id}"
                    if resume_checkpoint
                    else ""
                )
            )
        return result, resume_checkpoint

    def should_retry(self, plan: OrchestrationPlan, state: ExecutionState) -> bool:
        """Return whether the run may be retried per configuration."""
        return bool(self.config.get("enabled", True)) and bool(
            self.config.get("retry_failed_tasks", True)
        )

    def should_rollback(self, plan: OrchestrationPlan, state: ExecutionState) -> bool:
        """Return whether rollback should run after an unrecoverable failure."""
        return bool(self.config.get("rollback_on_unrecoverable", True)) and bool(
            self.rollback_manager is not None and self.rollback_manager.has_handlers()
        )

    # ── Internals ─────────────────────────────────────────────────

    def _restore_latest(
        self,
        plan: OrchestrationPlan,
        result: RecoveryResult,
    ) -> Checkpoint | None:
        if self.checkpoint_manager is None:
            return None
        checkpoint = self.checkpoint_manager.latest(plan.pipeline.id)
        if checkpoint is None:
            self.logger.info(
                "No checkpoint available for pipeline %s", plan.pipeline.id
            )
            return None
        result.actions_taken.append(RecoveryAction.CHECKPOINT_RESTORE)
        result.checkpoint_id = checkpoint.id
        self.logger.info(
            "Restoring plan %s from checkpoint %s",
            plan.id,
            checkpoint.id,
        )
        return checkpoint

    def _rollback(
        self,
        plan: OrchestrationPlan,
        state: ExecutionState,
        reason: str,
        result: RecoveryResult,
        undo_func: Callable[[str, str, dict[str, Any]], None] | None,
    ) -> None:
        if self.rollback_manager is None or not self.rollback_manager.has_handlers():
            return
        try:
            rollback = self.rollback_manager.execute_rollback(
                plan, reason, undo_func=undo_func
            )
            result.actions_taken.append(RecoveryAction.ROLLBACK)
            result.rolled_back = [s.task_id for s in rollback.steps]
            self.logger.info(
                "Rollback executed for plan %s (%d steps)",
                plan.id,
                len(rollback.steps),
            )
        except Exception as exc:
            self.logger.error("Rollback failed for plan %s: %s", plan.id, exc)
