"""Unit tests for the shutdown sequence executor."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_company.runtime.models import ShutdownError, ShutdownStepStatus
from ai_company.runtime.shutdown import ShutdownExecutor


def _stub_engine(**overrides) -> SimpleNamespace:
    engine = SimpleNamespace(
        engines={},
        dependency_graph=SimpleNamespace(reverse_order=list),
        process_manager=SimpleNamespace(stop_all=list),
        scheduler=SimpleNamespace(stop=lambda: None),
        watchdog=SimpleNamespace(stop=lambda: None),
        supervisor=SimpleNamespace(stop=lambda: None),
        state_store=SimpleNamespace(set_stopped=lambda: None),
        event_bus=None,
        mark_stopped=lambda: None,
    )
    for key, value in overrides.items():
        setattr(engine, key, value)
    return engine


def test_full_shutdown_succeeds() -> None:
    stopped: list[str] = []

    class _Engine:
        def __init__(self, name: str) -> None:
            self.name = name

        def stop(self) -> None:
            stopped.append(self.name)

    engine = _stub_engine(engines={"memory": _Engine("memory")})
    executor = ShutdownExecutor(engine, config={}, reason="test")
    sequence = executor.run()
    assert sequence.success is True
    assert sequence.reason == "test"
    assert [s.name for s in sequence.steps] == [
        "notify",
        "stop_workers",
        "stop_engines",
        "stop_processes",
        "save_state",
        "finalize",
    ]
    assert stopped == ["memory"]


def test_engines_stopped_in_reverse_dependency_order() -> None:
    stopped: list[str] = []

    class _Engine:
        def __init__(self, name: str) -> None:
            self.name = name

        def stop(self) -> None:
            stopped.append(self.name)

    engine = _stub_engine(
        engines={
            "memory": _Engine("memory"),
            "workflow": _Engine("workflow"),
            "orchestration": _Engine("orchestration"),
        },
        dependency_graph=SimpleNamespace(
            reverse_order=lambda: ["orchestration", "workflow", "memory"]
        ),
    )
    executor = ShutdownExecutor(engine, config={}, reason="test")
    executor.run()
    assert stopped == ["orchestration", "workflow", "memory"]


def test_failed_step_raises_without_force() -> None:
    engine = _stub_engine(mark_stopped=lambda: (_ for _ in ()).throw(RuntimeError("x")))
    executor = ShutdownExecutor(engine, config={}, reason="test")
    with pytest.raises(ShutdownError):
        executor.run()
    assert executor.sequence.steps[-1].status is ShutdownStepStatus.FAILED


def test_force_continues_past_failures() -> None:
    engine = _stub_engine(mark_stopped=lambda: (_ for _ in ()).throw(RuntimeError("x")))
    executor = ShutdownExecutor(engine, config={}, reason="test", force=True)
    sequence = executor.run()
    assert sequence.success is False  # a step failed
    assert sequence.force is True


def test_progress_callback_receives_steps() -> None:
    events: list[str] = []
    engine = _stub_engine()

    def on_progress(name: str, status, message: str) -> None:
        events.append(f"{name}:{status.value}")

    executor = ShutdownExecutor(
        engine, config={}, reason="test", on_progress=on_progress
    )
    executor.run()
    assert len(events) == 6
