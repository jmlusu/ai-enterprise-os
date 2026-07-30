"""Generation planning module.

This module defines classes and methods for creating dependency-aware generation
plans and determining the execution order of generation tasks.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    pass
from ai_company.generator.context import GeneratorContext
from ai_company.template_engine.renderer import Renderer


@dataclass(frozen=True)
class GenerationTask:
    """Represents a single unit of work in the generation process.

    Each task has a type (e.g., "executive", "specialist", "department"),
    a unique identifier, optional dependencies on other tasks, and metadata
    needed for execution.
    """

    task_type: str
    name: str
    dependencies: list[str] = field(default_factory=list)
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Generate a stable unique identifier for this task."""
        return f"{self.task_type}:{self.name}"


class TaskStatus(Enum):
    """Status of a generation task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskResult:
    """Result of executing a generation task."""

    task_id: str
    status: TaskStatus
    output_path: str | None = None
    error: str | None = None
    duration: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class GenerationPlan:
    """Complete plan for generating all artifacts in correct order.

    The plan includes all tasks, their execution order, dependencies, and
    any constraints or special instructions for the generation process.
    """

    def __init__(self) -> None:
        self.tasks: dict[str, GenerationTask] = {}
        self.task_results: dict[str, TaskResult] = {}
        self.execution_order: list[str] = []
        self.dry_run: bool = False
        self.incremental: bool = False
        self.context: GeneratorContext | None = None
        self.renderer: Renderer | None = None

    def add_task(
        self,
        task_type: str,
        name: str,
        dependencies: list[str] | None = None,
        priority: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a new task to the plan.

        Returns the task ID.
        """
        task_id = f"{task_type}:{name}"
        task = GenerationTask(
            task_type=task_type,
            name=name,
            dependencies=dependencies or [],
            priority=priority,
            metadata=metadata or {},
        )
        self.tasks[task_id] = task
        return task_id

    def get_task(self, task_id: str) -> GenerationTask | None:
        """Get a task by its ID."""
        return self.tasks.get(task_id)

    def add_dependency(self, task_id: str, dependency_id: str) -> None:
        """Add a dependency from one task to another."""
        if task_id in self.tasks and dependency_id in self.tasks:
            if dependency_id not in self.tasks[task_id].dependencies:
                self.tasks[task_id].dependencies.append(dependency_id)

    def generate_execution_order(self) -> list[str]:
        """Generate a topological sort of task IDs based on dependencies.

        Returns:
            List of task IDs in execution order.
        """
        if not self.tasks:
            return []

        # Build adjacency list and in-degree count
        adj_list: dict[str, list[str]] = {task_id: [] for task_id in self.tasks}
        in_degree: dict[str, int] = {task_id: 0 for task_id in self.tasks}

        for task_id, task in self.tasks.items():
            for dep_id in task.dependencies:
                if dep_id in self.tasks:
                    adj_list[dep_id].append(task_id)
                    in_degree[task_id] = in_degree.get(task_id, 0) + 1

        # Kahn's algorithm for topological sort
        queue: deque[str] = deque(
            [task_id for task_id, degree in in_degree.items() if degree == 0]
        )
        execution_order: list[str] = []

        while queue:
            current = queue.popleft()
            execution_order.append(current)

            for neighbor in adj_list[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Check for cycles
        if len(execution_order) != len(self.tasks):
            remaining = set(self.tasks.keys()) - set(execution_order)
            raise ValueError(f"Cycle detected in task dependencies: {remaining}")

        self.execution_order = execution_order
        return execution_order

    def sort_tasks_by_priority_and_dependencies(self) -> list[str]:
        """Sort tasks by priority (descending) and then by dependencies."""
        # Create a copy of tasks to sort
        tasks = list(self.tasks.values())

        # Sort by priority (higher first), then by task type, then by name
        tasks.sort(key=lambda t: (-t.priority, t.task_type, t.name))

        # For tasks with dependencies, ensure dependencies come first
        # Simple approach: group by dependency level
        task_ids_by_level: list[list[str]] = []
        visited: set[str] = set()

        def dfs(task_id: str, current_level: int) -> None:
            if task_id in visited:
                return
            visited.add(task_id)

            # Ensure dependencies are processed first
            task = self.tasks[task_id]
            for dep_id in task.dependencies:
                if dep_id in self.tasks:
                    dfs(dep_id, current_level + 1)

            if len(task_ids_by_level) <= current_level:
                task_ids_by_level.append([])
            task_ids_by_level[current_level].append(task_id)

        for task_id in self.tasks:
            if task_id not in visited:
                dfs(task_id, 0)

        # Flatten with higher levels first (dependencies before dependents)
        execution_order = []
        for level in reversed(task_ids_by_level):
            execution_order.extend(level)

        self.execution_order = execution_order
        return execution_order

    def validate(self) -> list[str]:
        """Validate the plan and return any errors."""
        errors: list[str] = []

        # Check for missing dependencies
        for task_id, task in self.tasks.items():
            for dep_id in task.dependencies:
                if dep_id not in self.tasks:
                    errors.append(
                        f"Task '{task_id}' depends on missing task '{dep_id}'"
                    )

        # Check for duplicate tasks
        if len(self.tasks) != len(set(self.tasks.keys())):
            errors.append("Duplicate task IDs found")

        # Check execution order if generated
        if self.execution_order and len(self.execution_order) != len(self.tasks):
            errors.append("Generated execution order doesn't match number of tasks")

        return errors


class GenerationPlanner:
    """Creates generation plans based on manifest and registry data."""

    def __init__(
        self,
        context: GeneratorContext,
        renderer: Renderer,
    ) -> None:
        self.context = context
        self.renderer = renderer

    def create_plan(
        self,
        dry_run: bool = False,
        incremental: bool = False,
    ) -> GenerationPlan:
        """Create a generation plan based on the current context.

        Args:
            dry_run: If True, only plan without executing.
            incremental: If True, skip tasks that would not change.

        Returns:
            GenerationPlan for the generation process.
        """
        plan = GenerationPlan()
        plan.dry_run = dry_run
        plan.incremental = incremental
        plan.context = self.context
        plan.renderer = self.renderer

        # Get manifest and registry data
        manifest = self.context.manifest
        registry = self.context.registry

        if not registry:
            return plan

        # Determine tasks based on registry contents
        self._add_executive_tasks(plan, registry)
        self._add_specialist_tasks(plan, registry)
        self._add_department_tasks(plan, manifest)

        # Sort and generate execution order
        plan.generate_execution_order()

        return plan

    def _add_executive_tasks(self, plan: GenerationPlan, registry: Any) -> None:
        """Add tasks for each executive."""
        for executive in registry.executives:
            plan.add_task(
                task_type="executive",
                name=executive.name or "unknown",
                priority=10,  # High priority for executives
                metadata={
                    "executive": executive,
                    "template": "executive",
                },
            )

    def _add_specialist_tasks(self, plan: GenerationPlan, registry: Any) -> None:
        """Add tasks for each specialist."""
        for specialist in registry.specialists:
            plan.add_task(
                task_type="specialist",
                name=specialist.name or "unknown",
                priority=8,
                metadata={
                    "specialist": specialist,
                    "template": "specialist",
                },
            )

    def _add_department_tasks(self, plan: GenerationPlan, manifest: Any) -> None:
        """Add tasks for each department."""
        for department in manifest.departments:
            plan.add_task(
                task_type="department",
                name=department.name,
                priority=5,
                metadata={
                    "department": department,
                    "template": "department",
                },
            )

    def analyze_task_dependencies(self, plan: GenerationPlan) -> dict[str, list[str]]:
        """Analyze dependencies between tasks."""
        dependencies: dict[str, list[str]] = defaultdict(list)

        # Executive tasks may depend on company-level data
        for task_id, task in plan.tasks.items():
            if task.task_type == "executive":
                dependencies[task_id].append("company_data")
            elif task.task_type == "specialist":
                dependencies[task_id].append("company_data")
            elif task.task_type == "department":
                dependencies[task_id].append("company_data")

        return dict(dependencies)

    def estimate_task_duration(self, task: GenerationTask) -> float:
        """Estimate duration for a task in seconds.

        Base duration depends on task type and complexity.
        """
        base_durations = {
            "executive": 2.0,
            "specialist": 1.5,
            "department": 1.0,
        }
        base = base_durations.get(task.task_type, 1.0)

        # Adjust based on metadata
        complexity_factor = task.metadata.get("complexity", 1.0)
        return cast(float, base * complexity_factor)


class PlannerError(Exception):
    """Exception raised during generation planning errors."""

    def __init__(self, message: str, task_id: str | None = None) -> None:
        super().__init__(message)
        self.task_id = task_id
