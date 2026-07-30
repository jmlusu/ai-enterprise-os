"""Dependency resolution module.

This module provides functionality for resolving dependencies between generation tasks,
performing topological sorting, and managing the dependency graph for the generation process.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Any

from ai_company.generator.planner import GenerationTask

logger = logging.getLogger(__name__)


class DependencyGraph:
    """Represents a directed acyclic graph of task dependencies.

    This class manages task dependencies, performs topological sorting, and provides
    methods for analyzing the dependency structure.
    """

    def __init__(self) -> None:
        self.tasks: dict[str, GenerationTask] = {}
        self.adjacency_list: dict[str, list[str]] = defaultdict(list)
        self.reverse_adjacency_list: dict[str, list[str]] = defaultdict(list)
        self.in_degree: dict[str, int] = defaultdict(int)
        self.topological_order: list[str] | None = None
        self.cycle_detected: bool = False
        self.cycle_nodes: list[str] = []

    def add_task(self, task: GenerationTask) -> None:
        """Add a task to the dependency graph."""
        self.tasks[task.id] = task

        # Initialize in-degree
        self.in_degree[task.id] = 0

        # Add edges for dependencies
        for dep_id in task.dependencies:
            self.adjacency_list[dep_id].append(task.id)
            self.reverse_adjacency_list[task.id].append(dep_id)
            self.in_degree[task.id] += 1

    def remove_task(self, task_id: str) -> None:
        """Remove a task from the graph."""
        if task_id not in self.tasks:
            return

        # Remove edges pointing to this task
        for dependent_id in self.adjacency_list.get(task_id, []):
            if task_id in self.reverse_adjacency_list.get(dependent_id, []):
                self.reverse_adjacency_list[dependent_id].remove(task_id)
                self.in_degree[dependent_id] -= 1

        # Remove edges pointing from this task
        for dependency_id in self.reverse_adjacency_list.get(task_id, []):
            if task_id in self.adjacency_list.get(dependency_id, []):
                self.adjacency_list[dependency_id].remove(task_id)

        # Remove task from all data structures
        del self.tasks[task_id]
        del self.adjacency_list[task_id]
        del self.reverse_adjacency_list[task_id]
        del self.in_degree[task_id]

        # Invalidate topological order
        self.topological_order = None

    def has_cycle(self) -> bool:
        """Check if the graph contains cycles."""
        if self.topological_order is not None:
            return self.cycle_detected

        # Perform DFS to detect cycles
        visited: set[str] = set()
        recursion_stack: set[str] = set()
        cycle_path: list[str] = []

        def dfs(node: str) -> bool:
            visited.add(node)
            recursion_stack.add(node)

            for neighbor in self.adjacency_list.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        cycle_path.append(node)
                        return True
                elif neighbor in recursion_stack:
                    # Cycle detected
                    cycle_path.extend([node, neighbor])
                    self.cycle_nodes = cycle_path[::-1]
                    return True

            recursion_stack.remove(node)
            return False

        self.cycle_detected = False
        self.cycle_nodes = []

        for task_id in self.tasks:
            if task_id not in visited:
                if dfs(task_id):
                    self.cycle_detected = True
                    break

        return self.cycle_detected

    def topological_sort(self) -> list[str]:
        """Perform topological sort on the graph.

        Returns:
            List of task IDs in topological order.

        Raises:
            ValueError: If the graph contains cycles.
        """
        if self.topological_order is not None:
            return self.topological_order

        # Check for cycles first
        if self.has_cycle():
            raise ValueError(
                f"Cannot perform topological sort on graph with cycles: {self.cycle_nodes}"
            )

        # Kahn's algorithm for topological sort
        in_degree = self.in_degree.copy()
        queue = deque([task_id for task_id, degree in in_degree.items() if degree == 0])
        result: list[str] = []

        while queue:
            current = queue.popleft()
            result.append(current)

            for neighbor in self.adjacency_list.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Verify all tasks were included
        if len(result) != len(self.tasks):
            remaining = set(self.tasks.keys()) - set(result)
            raise ValueError(f"Graph contains disconnected components: {remaining}")

        self.topological_order = result
        return result

    def get_dependent_tasks(self, task_id: str) -> list[str]:
        """Get all tasks that depend on the given task."""
        return self.adjacency_list.get(task_id, [])

    def get_dependency_tasks(self, task_id: str) -> list[str]:
        """Get all tasks that the given task depends on."""
        return self.reverse_adjacency_list.get(task_id, [])

    def get_levelized_tasks(self) -> list[list[str]]:
        """Get tasks grouped by dependency levels (topological layers).

        Returns:
            List of lists, where each inner list contains task IDs at the same level.
        """
        if not self.tasks:
            return []

        # Calculate levels using BFS
        in_degree = self.in_degree.copy()
        queue = deque([task_id for task_id, degree in in_degree.items() if degree == 0])
        levels: list[list[str]] = []

        while queue:
            level_size = len(queue)
            current_level: list[str] = []

            for _ in range(level_size):
                current = queue.popleft()
                current_level.append(current)

                for neighbor in self.adjacency_list.get(current, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            levels.append(current_level)

        # Check if all tasks were assigned
        all_assigned = sum(len(level) for level in levels)
        if all_assigned != len(self.tasks):
            # There are cycles
            unassigned = set(self.tasks.keys()) - set(
                task_id for level in levels for task_id in level
            )
            logger.warning(f"Tasks could not be levelized due to cycles: {unassigned}")

        return levels

    def calculate_critical_path(self) -> list[str]:
        """Calculate the critical path (longest path) through the graph.

        Returns:
            List of task IDs representing the critical path.
        """
        if not self.tasks:
            return []

        # Use DFS to find longest path (critical path)
        longest_path: list[str] = []
        max_length = -1

        def dfs(node: str, current_path: list[str], visited: set[str]) -> None:
            nonlocal longest_path, max_length

            current_path.append(node)
            visited.add(node)

            # Find longest path from this node
            longest_from_node = len(current_path) - 1
            if longest_from_node > max_length:
                max_length = longest_from_node
                longest_path = current_path.copy()

            # Continue to dependents
            for neighbor in self.adjacency_list.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, current_path, visited)

            # Backtrack
            current_path.pop()
            visited.remove(node)

        for task_id in self.tasks:
            if task_id not in set(
                task for level in self.get_levelized_tasks() for task in level
            ):
                continue

            dfs(task_id, [], set())

        return longest_path

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about the dependency graph."""
        if not self.tasks:
            return {
                "total_tasks": 0,
                "total_dependencies": 0,
                "average_dependencies_per_task": 0,
                "max_dependencies": 0,
                "min_dependencies": 0,
                "tasks_with_no_dependencies": 0,
                "tasks_with_many_dependencies": 0,
                "has_cycles": False,
                "topological_order_available": False,
            }

        total_deps = sum(len(task.dependencies) for task in self.tasks.values())
        dep_counts = [len(task.dependencies) for task in self.tasks.values()]

        return {
            "total_tasks": len(self.tasks),
            "total_dependencies": total_deps,
            "average_dependencies_per_task": total_deps / len(self.tasks),
            "max_dependencies": max(dep_counts) if dep_counts else 0,
            "min_dependencies": min(dep_counts) if dep_counts else 0,
            "tasks_with_no_dependencies": sum(1 for count in dep_counts if count == 0),
            "tasks_with_many_dependencies": sum(1 for count in dep_counts if count > 3),
            "has_cycles": self.has_cycle(),
            "topological_order_available": self.topological_order is not None,
            "critical_path_length": len(self.calculate_critical_path()),
        }


class DependencyResolver:
    """Resolves dependencies between generation tasks.

    This class handles:
    1. Building dependency graphs from task definitions
    2. Detecting and handling cycles in dependencies
    3. Performing topological sorting
    4. Analyzing dependency patterns
    5. Managing task priorities based on dependencies

    Args:
        enable_cycle_detection: Whether to enable automatic cycle detection
        strict_mode: Whether to raise exceptions on validation errors
        auto_prioritize: Whether to automatically prioritize tasks based on dependencies
    """

    def __init__(
        self,
        enable_cycle_detection: bool = True,
        strict_mode: bool = True,
        auto_prioritize: bool = False,
    ) -> None:
        self.enable_cycle_detection = enable_cycle_detection
        self.strict_mode = strict_mode
        self.auto_prioritize = auto_prioritize
        self.logger = logging.getLogger(self.__class__.__name__)
        self.graphs: dict[str, DependencyGraph] = {}
        self.task_types_to_priorities: dict[str, int] = {
            "executive": 10,
            "specialist": 8,
            "department": 5,
        }

    def add_task(
        self,
        task_type: str,
        task_id: str,
        name: str,
        dependencies: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GenerationTask:
        """Add a task to the resolver.

        Args:
            task_type: Type of task (e.g., "executive", "specialist", "department")
            task_id: Unique identifier for the task
            name: Human-readable name for the task
            dependencies: List of task IDs this task depends on
            metadata: Additional metadata for the task

        Returns:
            The created GenerationTask
        """
        dependencies = dependencies or []

        # Create task
        task = GenerationTask(
            task_type=task_type,
            name=name,
            dependencies=dependencies,
            priority=self._calculate_task_priority(
                task_type, dependencies, metadata or {}
            ),
            metadata=metadata or {},
        )

        # Update dependency graph
        if task_id not in self.graphs:
            self.graphs[task_id] = DependencyGraph()

        self.graphs[task_id].add_task(task)

        return task

    def resolve_order(
        self,
        task_ids: list[str] | None = None,
        task_type_filter: str | None = None,
    ) -> list[str]:
        """Resolve execution order based on dependencies.

        Args:
            task_ids: Optional list of task IDs to include in resolution
            task_type_filter: Optional filter for task types

        Returns:
            List of task IDs in execution order

        Raises:
            ValueError: If resolution fails
        """
        # Select tasks to include
        tasks_to_include = self._get_tasks_to_include(task_ids, task_type_filter)

        # Build combined graph
        combined_graph = self._build_combined_graph(tasks_to_include)

        # Detect cycles if enabled
        if self.enable_cycle_detection and combined_graph.has_cycle():
            if self.strict_mode:
                raise ValueError(
                    f"Dependency graph has cycles: {combined_graph.cycle_nodes}"
                )
            else:
                self.logger.warning(
                    f"Dependency graph has cycles: {combined_graph.cycle_nodes}"
                )

        # Perform topological sort
        try:
            order = combined_graph.topological_sort()
            return order
        except ValueError as e:
            if self.strict_mode:
                raise
            else:
                self.logger.warning(f"Failed to resolve order: {e}")
                # Fallback: return tasks in original order (may violate dependencies)
                return list(tasks_to_include)

    def get_dependency_analysis(
        self,
        task_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Analyze dependencies between tasks.

        Args:
            task_ids: Optional list of task IDs to analyze

        Returns:
            Dictionary containing dependency analysis
        """
        tasks_to_analyze = self._get_tasks_to_include(task_ids, None)
        combined_graph = self._build_combined_graph(tasks_to_analyze)

        analysis: dict[str, Any] = {
            "total_tasks": len(combined_graph.tasks),
            "total_dependencies": sum(
                len(task.dependencies) for task in combined_graph.tasks.values()
            ),
            "dependency_density": 0.0,
            "levelized_tasks": combined_graph.get_levelized_tasks(),
            "critical_path": combined_graph.calculate_critical_path(),
            "graph_statistics": combined_graph.get_statistics(),
            "task_dependencies": {},
        }

        # Calculate dependency density
        if len(combined_graph.tasks) > 1:
            max_possible_deps = len(combined_graph.tasks) * (
                len(combined_graph.tasks) - 1
            )
            actual_deps = sum(
                len(task.dependencies) for task in combined_graph.tasks.values()
            )
            analysis["dependency_density"] = (
                actual_deps / max_possible_deps if max_possible_deps > 0 else 0.0
            )

        # Map task IDs to task details
        for task_id in tasks_to_analyze:
            analysis["task_dependencies"][task_id] = {
                "type": combined_graph.tasks[task_id].task_type,
                "name": combined_graph.tasks[task_id].name,
                "dependencies": combined_graph.tasks[task_id].dependencies,
                "dependents": combined_graph.get_dependent_tasks(task_id),
                "priority": combined_graph.tasks[task_id].priority,
            }

        return analysis

    def get_task_priority(self, task_id: str) -> int:
        """Get the priority of a task.

        Args:
            task_id: Task ID

        Returns:
            Priority value (higher = earlier execution)
        """
        for graph in self.graphs.values():
            task = graph.tasks.get(task_id)
            if task:
                return task.priority

        return 0

    def update_task_dependencies(
        self,
        task_id: str,
        new_dependencies: list[str],
    ) -> None:
        """Update dependencies for a task.

        Args:
            task_id: Task ID to update
            new_dependencies: New list of dependencies
        """
        # Find the graph containing this task
        for graph in self.graphs.values():
            if task_id in graph.tasks:
                # Remove old task and add new one
                old_task = graph.tasks[task_id]
                new_task = GenerationTask(
                    task_type=old_task.task_type,
                    name=old_task.name,
                    dependencies=new_dependencies,
                    priority=old_task.priority,
                    metadata=old_task.metadata,
                )
                graph.remove_task(task_id)
                graph.add_task(new_task)
                return

        raise ValueError(f"Task {task_id} not found in any dependency graph")

    def remove_task(self, task_id: str) -> None:
        """Remove a task from all dependency graphs.

        Args:
            task_id: Task ID to remove
        """
        for graph in self.graphs.values():
            graph.remove_task(task_id)

    def clear(self) -> None:
        """Clear all dependency graphs."""
        self.graphs.clear()

    def _build_combined_graph(self, task_ids: list[str]) -> DependencyGraph:
        """Build a combined graph from multiple dependency graphs."""
        combined = DependencyGraph()

        for task_id in task_ids:
            for graph in self.graphs.values():
                if task_id in graph.tasks:
                    task = graph.tasks[task_id]
                    combined.add_task(task)
                    break

        return combined

    def _get_tasks_to_include(
        self,
        task_ids: list[str] | None,
        task_type_filter: str | None,
    ) -> list[str]:
        """Get list of task IDs to include in resolution."""
        if task_ids:
            return [tid for tid in task_ids if tid in self._get_all_task_ids()]

        # Get all tasks
        all_ids = self._get_all_task_ids()

        # Apply task type filter
        if task_type_filter:
            return [
                tid for tid in all_ids if self._get_task_type(tid) == task_type_filter
            ]

        return all_ids

    def _get_all_task_ids(self) -> list[str]:
        """Get all task IDs from all graphs."""
        all_ids: list[str] = []
        for graph in self.graphs.values():
            all_ids.extend(graph.tasks.keys())
        return all_ids

    def _get_task_type(self, task_id: str) -> str | None:
        """Get task type for a task ID."""
        for graph in self.graphs.values():
            task = graph.tasks.get(task_id)
            if task:
                return task.task_type
        return None

    def _calculate_task_priority(
        self,
        task_type: str,
        dependencies: list[str],
        metadata: dict[str, Any],
    ) -> int:
        """Calculate priority for a task based on type and dependencies."""
        # Base priority based on task type
        base_priority = self.task_types_to_priorities.get(task_type, 0)

        # Increase priority for tasks with fewer dependencies
        if dependencies:
            # Tasks with fewer dependencies may be prioritized to avoid blocking
            dependency_penalty = max(0, 3 - len(dependencies))
            base_priority += dependency_penalty

        # Check for override in metadata
        if "priority" in metadata:
            base_priority = metadata["priority"]

        return base_priority

    def get_graph_summary(self) -> dict[str, Any]:
        """Get summary of all dependency graphs."""
        total_tasks = sum(len(graph.tasks) for graph in self.graphs.values())
        total_dependencies = sum(
            len(task.dependencies)
            for graph in self.graphs.values()
            for task in graph.tasks.values()
        )

        graph_stats = {}
        for task_id, graph in self.graphs.items():
            graph_stats[task_id] = graph.get_statistics()

        return {
            "total_graphs": len(self.graphs),
            "total_tasks": total_tasks,
            "total_dependencies": total_dependencies,
            "graphs": graph_stats,
        }


class DependencyError(Exception):
    """Exception raised for dependency-related errors."""

    def __init__(
        self, message: str, task_id: str | None = None, dependency_id: str | None = None
    ) -> None:
        super().__init__(message)
        self.task_id = task_id
        self.dependency_id = dependency_id
