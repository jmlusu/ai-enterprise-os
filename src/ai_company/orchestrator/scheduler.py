"""Task scheduler for AI Enterprise OS Orchestration Layer."""

from __future__ import annotations

import logging
from typing import Any

from ai_company.orchestrator.workflow import WorkflowDefinition


class TaskScheduler:
    """Creates and manages task execution plans from workflows."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def create_plan(self, workflow: WorkflowDefinition) -> list[dict[str, Any]]:
        """Create a sequential execution plan from a workflow.

        Args:
            workflow: Workflow definition to plan

        Returns:
            List of task steps in execution order
        """
        plan = []

        for step in workflow.steps:
            task = {
                "type": step.get("type", "task"),
                "name": step.get("name", "unnamed"),
                "params": step.get("params", {}),
                "dependencies": step.get("dependencies", []),
                "retry_count": step.get("retry_count", 0),
                "timeout": step.get("timeout", 3600),
            }
            plan.append(task)

        # Sort by dependencies (topological)
        plan = self._topological_sort(plan)

        self.logger.debug(f"Created execution plan with {len(plan)} steps")
        return plan

    def _topological_sort(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sort tasks so dependencies come first."""
        task_map: dict[str, dict[str, Any]] = {}
        for task in tasks:
            name = task.get("name", "unnamed")
            task_map[name] = task

        visited: set[str] = set()
        result: list[dict[str, Any]] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            task = task_map.get(name)
            if task:
                for dep in task.get("dependencies", []):
                    visit(dep)
                result.append(task)

        for task in tasks:
            visit(task.get("name", "unnamed"))

        return result
