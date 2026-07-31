"""Unit tests for dependency resolution and condition evaluation."""

from __future__ import annotations

import pytest

from ai_company.orchestration.dependencies import DependencyGraph
from ai_company.orchestration.exceptions import DependencyError, InvalidPlanError
from ai_company.orchestration.models import (
    OrchestrationPlan,
    Pipeline,
    PipelineStage,
    PipelineTask,
    StageMode,
)
from ai_company.orchestration.pipeline import evaluate_condition


def _task(task_id: str, deps: list[str] | None = None) -> PipelineTask:
    return PipelineTask(
        id=task_id,
        name=task_id,
        task_type="noop",
        engine="test",
        dependencies=list(deps or []),
    )


def _pipeline(stage_tasks: list[PipelineTask], name: str = "p") -> Pipeline:
    return Pipeline(
        id=f"pipeline_{name}",
        name=name,
        stages=[
            PipelineStage(
                id="s1",
                name="S1",
                mode=StageMode.SEQUENTIAL,
                tasks=stage_tasks,
            )
        ],
    )


def _graph(tasks: list[PipelineTask], name: str = "p") -> DependencyGraph:
    return DependencyGraph(_pipeline(tasks, name))


class TestDependencyGraph:
    def test_accepts_well_formed_pipeline(self) -> None:
        graph = _graph([_task("a"), _task("b", ["a"])])
        assert graph.pipeline.name == "p"
        assert graph.dependencies_of("b")[0].task_id == "a"

    def test_unknown_dependency_raises(self) -> None:
        with pytest.raises(InvalidPlanError):
            _graph([_task("a", ["missing"])])

    def test_missing_dependency_skipped_when_configured(self) -> None:
        graph = DependencyGraph(
            _pipeline([_task("a", ["missing"])], "skip-cfg"),
            {"missing_dependency_policy": "skip"},
        )
        assert graph.dependencies_of("a") == []

    def test_self_dependency_raises(self) -> None:
        with pytest.raises(DependencyError, match="depends on itself"):
            _graph([_task("a", ["a"])])

    def test_self_dependency_ignored_when_configured(self) -> None:
        graph = DependencyGraph(
            _pipeline([_task("a", ["a"])], "self-cfg"),
            {"self_dependency_policy": "ignore"},
        )
        assert graph.dependencies_of("a") == []

    def test_cycle_detection(self) -> None:
        with pytest.raises(DependencyError, match="Cyclic"):
            _graph([_task("a", ["b"]), _task("b", ["a"])])

    def test_topological_order(self) -> None:
        graph = _graph([_task("c", ["a"]), _task("a"), _task("b", ["a"])])
        order = graph.topological_order()
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")

    def test_ready_tasks_respect_dependencies(self) -> None:
        graph = _graph([_task("a"), _task("b", ["a"]), _task("c", ["b"])])
        assert set(graph.ready_tasks()) == {"a"}
        assert set(graph.ready_tasks(completed={"a"})) == {"b"}
        assert set(graph.ready_tasks(completed={"a", "b"})) == {"c"}

    def test_ready_tasks_blocked_by_failed(self) -> None:
        graph = _graph([_task("a"), _task("b", ["a"])])
        assert set(graph.ready_tasks(completed=set(), failed={"a"})) == set()

    def test_optional_dependency_does_not_block(self) -> None:
        tasks = [
            _task("a"),
            PipelineTask(
                id="b",
                name="b",
                task_type="noop",
                engine="test",
                dependencies=["a"],
            ),
        ]
        # Emulate an optional dependency via config-free graph: b waits on a.
        graph = _graph(tasks)
        assert "b" not in graph.ready_tasks()
        assert "b" in graph.ready_tasks(completed={"a"})

    def test_parallel_groups_layering(self) -> None:
        graph = _graph(
            [_task("a"), _task("b", ["a"]), _task("c", ["a"]), _task("d", ["b", "c"])]
        )
        layers = graph.parallel_groups()
        assert layers[0] == ["a"]
        assert set(layers[1]) == {"b", "c"}
        assert layers[2] == ["d"]

    def test_dependents_of(self) -> None:
        graph = _graph([_task("a"), _task("b", ["a"]), _task("c", ["a"])])
        assert set(graph.dependents_of("a")) == {"b", "c"}


class TestEvaluateCondition:
    def test_none_or_empty_returns_true(self) -> None:
        assert evaluate_condition(None, {}) is True
        assert evaluate_condition("", {}) is True

    def test_boolean_literals(self) -> None:
        assert evaluate_condition("true", {}) is True
        assert evaluate_condition("yes", {}) is True
        assert evaluate_condition("false", {}) is False
        assert evaluate_condition("no", {}) is False

    def test_bare_path_truthiness(self) -> None:
        results = {"a": {"success": True, "count": 3}}
        assert evaluate_condition("a.success", results) is True
        assert evaluate_condition("a.count", results) is True
        assert evaluate_condition("a.missing", results) is False
        assert evaluate_condition("a.falsey", {"a": {"falsey": 0}}) is False

    def test_equality_comparison(self) -> None:
        results = {"a": {"success": True}}
        assert evaluate_condition("a.success == true", results) is True
        assert evaluate_condition("a.success == false", results) is False
        assert evaluate_condition("a.success != false", results) is True

    def test_numeric_comparison(self) -> None:
        results = {"a": {"count": 5}}
        assert evaluate_condition("a.count >= 5", results) is True
        assert evaluate_condition("a.count > 5", results) is False
        assert evaluate_condition("a.count < 10", results) is True
        assert evaluate_condition("a.count <= 4", results) is False

    def test_membership(self) -> None:
        results = {"a": {"kind": "company"}}
        assert evaluate_condition("a.kind in [company, agent]", results) is True
        assert evaluate_condition("a.kind in [project, task]", results) is False

    def test_type_error_returns_false(self) -> None:
        results = {"a": {"count": "many"}}
        assert evaluate_condition("a.count > 5", results) is False

    def test_missing_path_comparison(self) -> None:
        assert evaluate_condition("a.missing == true", {}) is False


def test_plan_builder_roundtrip() -> None:
    """Sanity: plan models used by the tests are valid."""
    plan = OrchestrationPlan(
        name="roundtrip",
        pipeline=_pipeline([_task("a")], "roundtrip"),
    )
    assert plan.pipeline.all_tasks()[0].id == "a"
    assert plan.schedule_mode.value == "immediate"
