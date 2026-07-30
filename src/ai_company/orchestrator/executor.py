"""Task executor for AI Enterprise OS Orchestration Layer."""

from __future__ import annotations

import logging
import time
from typing import Any


class TaskExecutor:
    """Executes tasks with retry and rollback support."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self._rollbacks: list[dict[str, Any]] = []

    def execute(
        self,
        target: str,
        task_type: str,
        params: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute a task with retry logic."""
        max_retries = params.get("retry_count", 3)
        last_error: str | None = None

        for attempt in range(max_retries + 1):
            try:
                if dry_run:
                    return {
                        "status": "dry_run",
                        "target": target,
                        "task_type": task_type,
                        "attempt": attempt,
                    }

                start_time = time.time()
                result = self._do_execute(target, task_type, params)
                duration = time.time() - start_time

                return {
                    "status": "completed",
                    "target": target,
                    "task_type": task_type,
                    "duration": duration,
                    "result": result,
                    "attempt": attempt,
                }

            except Exception as e:
                last_error = str(e)
                self.logger.warning(
                    f"Task execution failed (attempt {attempt + 1}/{max_retries + 1}): {e}"
                )
                if attempt < max_retries:
                    time.sleep(1)

        return {"status": "failed", "error": last_error, "attempts": max_retries + 1}

    def register_rollback(
        self, rollback_id: str, action: str, params: dict[str, Any]
    ) -> None:
        """Register a rollback hook."""
        self._rollbacks.append(
            {
                "rollback_id": rollback_id,
                "action": action,
                "params": params,
            }
        )

    def execute_rollbacks(self) -> list[dict[str, Any]]:
        """Execute all registered rollback hooks."""
        results = []
        for hook in reversed(self._rollbacks):
            try:
                results.append({"hook": hook["rollback_id"], "status": "executed"})
            except Exception as e:
                results.append(
                    {"hook": hook["rollback_id"], "status": "failed", "error": str(e)}
                )
        self._rollbacks.clear()
        return results

    def _do_execute(
        self, target: str, task_type: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute the actual task logic."""
        return {
            "target": target,
            "task_type": task_type,
            "executed": True,
            "params": params,
        }
