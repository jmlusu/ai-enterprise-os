"""Dependency graph for runtime components.

Used to order startup, reverse-order shutdown, drive dependency-aware
scheduling, and detect cyclic component dependencies. Implements a
deterministic topological sort (Kahn's algorithm with insertion-order
stability).
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from ai_company.runtime.models import RuntimeError

logger = logging.getLogger(__name__)


class DependencyCycleError(RuntimeError):
    """Raised when the component graph contains a cycle."""


class RuntimeDependencyGraph:
    """Directed dependency graph of runtime components.

    Args:
        missing_dependency_policy: How to treat unknown dependencies:
            ``raise`` (default), ``warn``, or ``skip``.
        detect_cycles: Whether to raise on cyclic graphs.
    """

    def __init__(
        self,
        missing_dependency_policy: str = "raise",
        detect_cycles: bool = True,
    ) -> None:
        self._nodes: dict[str, set[str]] = {}
        self._order: list[str] = []
        self.missing_dependency_policy = missing_dependency_policy
        self.cycle_detection = detect_cycles

    def add_component(self, name: str, dependencies: list[str] | None = None) -> None:
        """Register a component and its dependencies."""
        if name in self._nodes:
            self._nodes[name] = set(dependencies or [])
            return
        self._order.append(name)
        self._nodes[name] = set(dependencies or [])

    def remove_component(self, name: str) -> bool:
        """Unregister a component (and edges pointing at it)."""
        if name not in self._nodes:
            return False
        del self._nodes[name]
        if name in self._order:
            self._order.remove(name)
        for deps in self._nodes.values():
            deps.discard(name)
        return True

    def add_dependency(self, name: str, dependency: str) -> None:
        """Add a single dependency edge."""
        self._nodes.setdefault(name, set()).add(dependency)

    def components(self) -> list[str]:
        """Return component names in registration order."""
        return list(self._order)

    def dependencies_of(self, name: str) -> list[str]:
        """Return the direct dependencies of a component."""
        return sorted(self._nodes.get(name, set()))

    def dependents_of(self, name: str) -> list[str]:
        """Return components that depend (directly) on ``name``."""
        return [c for c, deps in self._nodes.items() if name in deps]

    def _resolve_dependencies(self, name: str) -> set[str]:
        deps = self._nodes.get(name, set())
        known = set(self._nodes)
        missing = deps - known
        if missing:
            if self.missing_dependency_policy == "raise":
                raise RuntimeError(
                    f"Component {name!r} depends on unknown components: "
                    f"{sorted(missing)}"
                )
            if self.missing_dependency_policy == "warn":
                logger.warning(
                    "Component %s depends on unknown components: %s",
                    name,
                    sorted(missing),
                )
            return deps & known
        return deps

    def detect_cycles(self) -> list[list[str]]:
        """Return every cycle in the graph as a list of component names."""
        cycles: list[list[str]] = []
        visited: set[str] = set()
        stack: list[str] = []

        def visit(node: str) -> None:
            if node in stack:
                idx = stack.index(node)
                cycle = stack[idx:] + [node]
                if cycle not in cycles:
                    cycles.append(cycle)
                return
            if node in visited:
                return
            visited.add(node)
            stack.append(node)
            for dep in self._resolve_dependencies(node):
                visit(dep)
            stack.pop()

        for node in self._order:
            visit(node)
        return cycles

    def topological_order(self) -> list[str]:
        """Return components ordered so dependencies come first.

        Raises:
            DependencyCycleError: If ``detect_cycles`` is enabled and the
                graph contains a cycle.
        """
        if self.cycle_detection:
            cycles = self.detect_cycles()
            if cycles:
                raise DependencyCycleError(f"Cyclic dependencies detected: {cycles}")

        resolved = self._resolve_dependencies  # local alias
        in_degree: dict[str, int] = {name: len(resolved(name)) for name in self._order}
        dependents: dict[str, list[str]] = {name: [] for name in self._order}
        for name in self._order:
            for dep in resolved(name):
                dependents[dep].append(name)

        queue: deque[str] = deque(name for name in self._order if in_degree[name] == 0)
        ordered: list[str] = []
        while queue:
            name = queue.popleft()
            ordered.append(name)
            for dependent in dependents[name]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        return ordered

    def reverse_order(self) -> list[str]:
        """Return components in reverse dependency order (shutdown order)."""
        return list(reversed(self.topological_order()))

    def snapshot(self) -> dict[str, Any]:
        """Return a compact snapshot for diagnostics."""
        return {
            "components": list(self._order),
            "dependencies": {name: sorted(deps) for name, deps in self._nodes.items()},
            "cycles": self.detect_cycles(),
        }
