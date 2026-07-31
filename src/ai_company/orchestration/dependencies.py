"""Dependency resolution for orchestration pipelines.

Resolves the task dependency graph of a pipeline: validates task ids,
detects cycles, produces topological order, computes parallel-ready
groups, and answers "which tasks are ready to run now?" queries.
"""

from __future__ import annotations

from typing import Any

from ai_company.orchestration.exceptions import DependencyError, InvalidPlanError
from ai_company.orchestration.models import Pipeline, PipelineTask, TaskDependency

_DEFAULT_CONFIG: dict[str, Any] = {
    "resolver": "topological",
    "allow_parallel": True,
    "max_parallel_tasks": 4,
    "detect_cycles": True,
    "missing_dependency_policy": "raise",
    "self_dependency_policy": "raise",
}


class DependencyGraph:
    """A validated, queryable dependency graph over pipeline tasks.

    Args:
        pipeline: The pipeline whose tasks form the graph.
        config: Dependency resolution config (see config/orchestration/dependencies.yaml).
    """

    def __init__(
        self,
        pipeline: Pipeline,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.config = _DEFAULT_CONFIG | (config or {})
        self._tasks: dict[str, PipelineTask] = pipeline.task_map()
        self._deps: dict[str, list[TaskDependency]] = {}
        self._validate()

    # ── Validation ────────────────────────────────────────────────

    def _validate(self) -> None:
        """Validate ids, dependency references, and cycles."""
        missing_policy = self.config.get("missing_dependency_policy", "raise")
        self_policy = self.config.get("self_dependency_policy", "raise")

        for task in self.pipeline.all_tasks():
            for dep in task.dependencies:
                if dep == task.id:
                    if self_policy == "ignore":
                        continue
                    raise DependencyError(
                        f"Task {task.id!r} depends on itself",
                        cycle=[task.id],
                    )
                if dep not in self._tasks:
                    if missing_policy == "skip":
                        continue
                    raise InvalidPlanError(
                        f"Task {task.id!r} references unknown dependency {dep!r}",
                        details={"task_id": task.id, "dependency": dep},
                    )
                self._deps.setdefault(task.id, []).append(TaskDependency(task_id=dep))

        if self.config.get("detect_cycles", True):
            cycle = self.find_cycle()
            if cycle:
                raise DependencyError(
                    f"Cyclic task dependency detected: {' -> '.join(cycle)}",
                    cycle=cycle,
                )

    # ── Queries ───────────────────────────────────────────────────

    def dependencies_of(self, task_id: str) -> list[TaskDependency]:
        """Return the enriched dependencies of a task."""
        return list(self._deps.get(task_id, []))

    def dependents_of(self, task_id: str) -> list[str]:
        """Return ids of tasks that depend on the given task."""
        return [
            tid
            for tid, deps in self._deps.items()
            if any(d.task_id == task_id for d in deps)
        ]

    def find_cycle(self) -> list[str]:
        """Return the first dependency cycle found, or an empty list."""
        visited: set[str] = set()
        path: list[str] = []
        in_path: set[str] = set()

        def visit(task_id: str) -> list[str] | None:
            if task_id in in_path:
                start = path.index(task_id)
                return path[start:] + [task_id]
            if task_id in visited:
                return None
            visited.add(task_id)
            in_path.add(task_id)
            path.append(task_id)
            for dep in self.dependencies_of(task_id):
                result = visit(dep.task_id)
                if result:
                    return result
            path.pop()
            in_path.discard(task_id)
            return None

        for task in self.pipeline.all_tasks():
            result = visit(task.id)
            if result:
                return result
        return []

    def topological_order(self) -> list[str]:
        """Return task ids in dependency order (dependencies first)."""
        result: list[str] = []
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visited:
                return
            visited.add(task_id)
            for dep in sorted(self.dependencies_of(task_id), key=lambda d: d.task_id):
                visit(dep.task_id)
            result.append(task_id)

        for task in self.pipeline.all_tasks():
            visit(task.id)
        return result

    def ready_tasks(
        self,
        completed: set[str] | None = None,
        failed: set[str] | None = None,
    ) -> list[str]:
        """Return ids of tasks whose dependencies are all satisfied.

        Args:
            completed: Ids of tasks that completed successfully.
            failed: Ids of tasks that failed (block ready tasks that
                depend on them).
        """
        completed = completed or set()
        failed = failed or set()

        def dep_satisfied(dep: TaskDependency) -> bool:
            if dep.task_id in completed:
                return True
            if dep.type == "optional":
                # Optional deps do not block execution.
                return True
            return False

        ready: list[str] = []
        for task in self.pipeline.all_tasks():
            if task.id in completed or task.id in failed:
                continue
            deps = self.dependencies_of(task.id)
            if all(dep_satisfied(d) for d in deps):
                ready.append(task.id)
        return ready

    def parallel_groups(self, completed: set[str] | None = None) -> list[list[str]]:
        """Return dependency layers; tasks in one layer can run in parallel.

        Uses Kahn's algorithm: repeatedly emit the set of tasks whose
        dependencies are all satisfied.
        """
        completed = completed or set()
        remaining = {t.id for t in self.pipeline.all_tasks() if t.id not in completed}
        layers: list[list[str]] = []

        while remaining:
            ready = [
                tid
                for tid in remaining
                if all(
                    dep.task_id in completed or dep.type == "optional"
                    for dep in self.dependencies_of(tid)
                )
            ]
            if not ready:
                raise DependencyError(
                    "Dependency graph cannot be layered "
                    "(remaining tasks have unsatisfied dependencies)",
                    cycle=self.find_cycle(),
                )
            layers.append(ready)
            for tid in ready:
                remaining.discard(tid)
                completed.add(tid)
        return layers
