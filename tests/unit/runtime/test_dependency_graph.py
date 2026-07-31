"""Unit tests for the runtime dependency graph."""

from __future__ import annotations

import pytest

from ai_company.runtime.dependency_graph import (
    DependencyCycleError,
    RuntimeDependencyGraph,
)
from ai_company.runtime.models import RuntimeError


def test_topological_order_dependencies_first() -> None:
    graph = RuntimeDependencyGraph()
    graph.add_component("orchestration", dependencies=["workflow", "memory"])
    graph.add_component("workflow", dependencies=["memory"])
    graph.add_component("memory")
    assert graph.topological_order() == ["memory", "workflow", "orchestration"]


def test_registration_order_is_stable() -> None:
    graph = RuntimeDependencyGraph()
    graph.add_component("a")
    graph.add_component("b", dependencies=["a"])
    graph.add_component("c")
    assert graph.components() == ["a", "b", "c"]
    # "c" has no dependencies; insertion order keeps a stable output
    assert graph.topological_order() == ["a", "c", "b"]


def test_reverse_order_for_shutdown() -> None:
    graph = RuntimeDependencyGraph()
    graph.add_component("memory")
    graph.add_component("workflow", dependencies=["memory"])
    graph.add_component("orchestration", dependencies=["workflow"])
    assert graph.reverse_order() == ["orchestration", "workflow", "memory"]


def test_cycle_detection_raises() -> None:
    graph = RuntimeDependencyGraph()
    graph.add_component("a", dependencies=["b"])
    graph.add_component("b", dependencies=["a"])
    with pytest.raises(DependencyCycleError):
        graph.topological_order()


def test_cycle_detection_returns_cycles() -> None:
    graph = RuntimeDependencyGraph()
    graph.add_component("a", dependencies=["b"])
    graph.add_component("b", dependencies=["a"])
    cycles = graph.detect_cycles()
    assert any("a" in cycle and "b" in cycle for cycle in cycles)


def test_missing_dependency_raises_by_default() -> None:
    graph = RuntimeDependencyGraph()
    graph.add_component("a", dependencies=["ghost"])
    with pytest.raises(RuntimeError):
        graph.topological_order()


def test_missing_dependency_skip_policy() -> None:
    graph = RuntimeDependencyGraph(missing_dependency_policy="skip")
    graph.add_component("a", dependencies=["ghost"])
    assert graph.topological_order() == ["a"]


def test_add_dependency_edge() -> None:
    graph = RuntimeDependencyGraph()
    graph.add_component("a")
    graph.add_component("b")
    graph.add_dependency("b", "a")
    assert graph.topological_order() == ["a", "b"]
    assert graph.dependencies_of("b") == ["a"]
    assert graph.dependents_of("a") == ["b"]


def test_remove_component_prunes_edges() -> None:
    graph = RuntimeDependencyGraph()
    graph.add_component("a")
    graph.add_component("b", dependencies=["a"])
    assert graph.remove_component("a") is True
    assert graph.components() == ["b"]
    assert graph.topological_order() == ["b"]
    assert graph.remove_component("missing") is False


def test_snapshot() -> None:
    graph = RuntimeDependencyGraph()
    graph.add_component("a")
    graph.add_component("b", dependencies=["a"])
    snapshot = graph.snapshot()
    assert snapshot["components"] == ["a", "b"]
    assert snapshot["dependencies"]["b"] == ["a"]
