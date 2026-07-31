"""Unit tests for the startup sequence executor."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_company.runtime.models import StartupError, StartupStepStatus
from ai_company.runtime.startup import StartupExecutor


def _stub_engine(**overrides) -> SimpleNamespace:
    engine = SimpleNamespace(
        config_dir="config",
        constitution={},
        engines={},
        event_bus=None,
        state_store=SimpleNamespace(load=lambda: None),
        runtime_config=SimpleNamespace(
            section=lambda name: {"x": 1},
            to_dict=lambda: {"runtime": {"x": 1}},
        ),
        start_workers=lambda: None,
        mark_ready=lambda: None,
        register_engine=lambda name, instance: engine.engines.__setitem__(
            name, instance
        ),
    )
    for key, value in overrides.items():
        setattr(engine, key, value)
    return engine


def test_internal_steps_complete() -> None:
    engine = _stub_engine()
    executor = StartupExecutor(
        engine,
        config={},
        steps=[
            {"name": "load_constitution", "target": "load_constitution"},
            {"name": "load_project_state", "target": "load_project_state"},
            {"name": "load_configuration", "target": "load_configuration"},
            {"name": "start_runtime", "target": "start_runtime"},
            {"name": "ready", "target": "ready"},
        ],
    )
    sequence = executor.run()
    assert sequence.success is True
    assert sequence.completed_steps == 5
    assert sequence.failed_steps == 0


def test_load_constitution_populates_engine() -> None:
    engine = _stub_engine(config_dir="config")
    executor = StartupExecutor(
        engine, config={}, steps=[{"name": "c", "target": "load_constitution"}]
    )
    executor.run()
    # constitution is a dict keyed by section stem
    assert isinstance(engine.constitution, dict)


def test_failed_step_records_error_and_raises() -> None:
    engine = _stub_engine()

    def boom() -> None:
        raise RuntimeError("kaboom")

    engine.start_workers = boom
    executor = StartupExecutor(
        engine, config={}, steps=[{"name": "start_runtime", "target": "start_runtime"}]
    )
    with pytest.raises(StartupError):
        executor.run()
    step = executor.sequence.steps[0]
    assert step.status is StartupStepStatus.FAILED
    assert "kaboom" in (step.error or "")


def test_class_step_reuses_existing_engine() -> None:
    existing = object()
    engine = _stub_engine(engines={"memory": existing})
    executor = StartupExecutor(
        engine,
        config={},
        steps=[
            {
                "name": "initialize_memory",
                "module": "ai_company.memory.engine",
                "class": "MemoryEngine",
                "engine": "memory",
                "params": {"storage_path": "x.jsonl"},
            }
        ],
    )
    sequence = executor.run()
    step = sequence.steps[0]
    assert step.status is StartupStepStatus.COMPLETED
    assert step.reused is True


def test_class_step_instantiates_and_registers() -> None:
    engine = _stub_engine()
    executor = StartupExecutor(
        engine,
        config={},
        steps=[
            {
                "name": "initialize_memory",
                "module": "ai_company.memory.engine",
                "class": "MemoryEngine",
                "engine": "memory",
                "params": {"storage_path": "x.jsonl"},
            }
        ],
    )
    sequence = executor.run()
    assert sequence.success is True
    assert "memory" in engine.engines
    assert sequence.steps[0].reused is False


def test_param_resolution_markers() -> None:
    engine = _stub_engine(
        engines={"memory": object()},
        state_store=SimpleNamespace(state_dir="runtime/state"),
    )
    executor = StartupExecutor(
        engine,
        config={},
        steps=[
            {
                "name": "resolve",
                "module": "ai_company.memory.engine",
                "class": "MemoryEngine",
                "engine": "memory",
                "params": {
                    "storage_path": "@state_dir",
                    "config": "@config:runtime",
                    "runtime": "@runtime",
                },
            }
        ],
    )
    sequence = executor.run()
    assert sequence.success is True


def test_unknown_step_definition_fails() -> None:
    engine = _stub_engine()
    executor = StartupExecutor(engine, config={}, steps=[{"name": "mystery"}])
    with pytest.raises(StartupError):
        executor.run()
    assert executor.sequence.steps[0].status is StartupStepStatus.FAILED
