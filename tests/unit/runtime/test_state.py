"""Unit tests for the runtime state store (persistence + memory mirror)."""

from __future__ import annotations

from ai_company.runtime.models import RuntimePhase
from ai_company.runtime.state import RuntimeStateStore


def test_starts_fresh(tmp_path) -> None:
    store = RuntimeStateStore(config={}, state_dir=tmp_path / "state")
    assert store.loaded is False
    assert store.state.phase is RuntimePhase.STOPPED
    store.load()
    assert store.loaded is True


def test_persist_and_recover(tmp_path) -> None:
    state_dir = tmp_path / "state"
    store = RuntimeStateStore(config={}, state_dir=state_dir)
    store.load()
    store.set_phase(RuntimePhase.RUNNING)
    store.add_active("pipelines", "p_1")
    store.add_active("workflows", "w_1")

    recovered = RuntimeStateStore(config={}, state_dir=state_dir)
    state = recovered.load()
    assert state.phase is RuntimePhase.RUNNING
    assert state.active_pipelines == ["p_1"]
    assert state.active_workflows == ["w_1"]


def test_set_engine_and_process_roundtrip(tmp_path) -> None:
    from ai_company.runtime.models import EngineState, RuntimeProcess

    store = RuntimeStateStore(config={}, state_dir=tmp_path / "state")
    store.load()
    store.set_engine(EngineState(name="memory"))
    store.set_process(RuntimeProcess(name="worker", status="running"))

    recovered = RuntimeStateStore(config={}, state_dir=tmp_path / "state")
    state = recovered.load()
    assert "memory" in state.processes or "worker" in state.processes
    assert recovered.engine_states()  # engine states restored


def test_remove_active(tmp_path) -> None:
    store = RuntimeStateStore(config={}, state_dir=tmp_path / "state")
    store.load()
    store.add_active("pipelines", "p_1")
    store.add_active("pipelines", "p_2")
    store.remove_active("pipelines", "p_1")
    assert store.state.active_pipelines == ["p_2"]


def test_clear_removes_persisted_file(tmp_path) -> None:
    state_dir = tmp_path / "state"
    store = RuntimeStateStore(config={}, state_dir=state_dir)
    store.load()
    store.set_phase(RuntimePhase.RUNNING)
    store.clear()
    assert store.state.phase is RuntimePhase.STOPPED
    assert not store.state_file.exists()


def test_active_counts_snapshot(tmp_path) -> None:
    store = RuntimeStateStore(config={}, state_dir=tmp_path / "state")
    store.load()
    store.add_active("pipelines", "p_1")
    store.add_active("pipelines", "p_2")
    store.add_active("agents", "a_1")
    counts = store.active_counts()
    assert counts["pipelines"] == 2
    assert counts["agents"] == 1
    assert counts["workflows"] == 0
