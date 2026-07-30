"""Execution state for AI Enterprise OS Orchestration Layer."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any


class ExecutionState:
    """Tracks and manages execution state for orchestrated workflows."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.reset()

    def reset(self) -> None:
        self.workflow_name: str = ""
        self.status: str = "idle"
        self.params: dict[str, Any] = {}
        self.dry_run: bool = False
        self.steps: list[dict[str, Any]] = []
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.error: str | None = None
        self.plan: list[dict[str, Any]] = []

    def start(
        self, workflow_name: str, params: dict[str, Any], dry_run: bool = False
    ) -> None:
        self.reset()
        self.workflow_name = workflow_name
        self.params = params
        self.dry_run = dry_run
        self.status = "running"
        self.started_at = datetime.now()
        self.logger.info(f"Execution started: {workflow_name}")

    def set_plan(self, plan: list[dict[str, Any]]) -> None:
        self.plan = plan

    def record_step(self, step_type: str, result: dict[str, Any]) -> None:
        self.steps.append(
            {
                "type": step_type,
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def complete(self) -> None:
        self.status = "completed"
        self.completed_at = datetime.now()
        self.logger.info(f"Execution completed: {self.workflow_name}")

    def fail(self, error: str) -> None:
        self.status = "failed"
        self.error = error
        self.completed_at = datetime.now()
        self.logger.error(f"Execution failed: {self.workflow_name} - {error}")

    def get_status(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow_name,
            "status": self.status,
            "dry_run": self.dry_run,
            "steps_completed": len(self.steps),
            "steps_planned": len(self.plan),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "error": self.error,
        }

    def get_report(self, status: str, error: str | None = None) -> dict[str, Any]:
        """Build a comprehensive execution report."""
        duration = None
        if self.started_at:
            end = self.completed_at or datetime.now()
            duration = (end - self.started_at).total_seconds()

        return {
            "workflow": self.workflow_name,
            "status": status,
            "dry_run": self.dry_run,
            "duration": duration,
            "steps": self.steps,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "error": error or self.error,
            "params": self.params,
        }
