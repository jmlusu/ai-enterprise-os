"""Unit tests for the streaming generate dispatcher (Phase 2 wave 2b).

The runner shells out through ``generate_dispatch.dispatch_generate`` exactly
like the frozen CLI: ``opencode`` primary, free/local ``ollama`` fallback on
failure (R4, decision D9). Tests substitute fake processes (Popen +
shutil.which on the dispatch module's globals) so the dispatch lifecycle, the
fallback path, log streaming, cancellation, and history persistence are
verified without invoking a real model.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from ai_company.services.generate_dispatch import DEFAULT_FALLBACK_MODEL, FallbackConfig
from ai_company.services.generate_runner import GenerateRunner

_FAKE_TARGET = "registry"
_FAKE_TARGET_PROMPT = "prompts/opencode/02_registry_engine.md"
_FAKE_MODEL = "opencode/north-mini-code-free"


class _FakeStdout:
    """Iterable of lines used as the child process stdout pipe."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def __iter__(self) -> Any:
        for line in self._lines:
            yield line + "\n"


class _FakeProc:
    """Substitute for subprocess.Popen that never starts a real process."""

    def __init__(
        self,
        lines: list[str] | None = None,
        returncode: int = 0,
        *,
        hold: threading.Event | None = None,
    ) -> None:
        self._lines = list(lines or ["fake opencode output", "done"])
        self._rc = returncode
        self.hold = hold
        self.arrived = threading.Event() if hold is not None else None
        self.terminated = False

    @property
    def stdout(self) -> Any:
        return self

    def __iter__(self) -> Any:
        for line in self._lines:
            yield line + "\n"
        if self.hold is not None:
            if self.arrived is not None:
                self.arrived.set()
            self.hold.wait(timeout=5)
            if self.terminated:
                return

    def wait(self) -> int:
        return self._rc

    def poll(self) -> int | None:
        return None if not self.terminated else -15

    def terminate(self) -> None:
        self.terminated = True


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A bare workspace with the mapped prompt file for the fake target."""
    prompt = tmp_path / _FAKE_TARGET_PROMPT
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text("Generate the registry artifact.", encoding="utf-8")

    # render_prompt requires config/company/company.yaml; the runner's fallback
    # writes the raw prompt text instead, so force the fallback path cleanly.
    def _fake_render(prompt_file: str) -> Path:
        return prompt

    monkeypatch.setattr("ai_company.cli.render.render_prompt", _fake_render)
    return tmp_path


def _runner(workspace: Path, **kwargs: Any) -> GenerateRunner:
    return GenerateRunner(root=str(workspace), **kwargs)


def _patch_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    which: dict[str, str],
    procs: list[_FakeProc],
) -> list[list[str]]:
    """Point the dispatch module's which/Popen at the fake processes.

    ``which`` maps executable name -> fake path (missing key = not on PATH);
    ``procs`` are returned in order for each spawned process.
    """
    monkeypatch.setattr(
        "ai_company.services.generate_dispatch.shutil.which",
        lambda name: which.get(name),
    )
    captured: list[list[str]] = []

    def _fake_popen(cmd: list[str], **kwargs: Any) -> _FakeProc:
        captured.append(cmd)
        return procs.pop(0)

    monkeypatch.setattr(
        "ai_company.services.generate_dispatch.subprocess.Popen", _fake_popen
    )
    return captured


def _wait_status(runner: GenerateRunner, run_id: str, timeout: float = 5.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = runner.get(run_id)
        if run is not None and run.status not in ("queued", "running"):
            return run.status
        time.sleep(0.05)
    raise AssertionError("run did not finish within timeout")


def test_start_success_streams_log_and_persists_history(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(workspace)
    proc = _FakeProc(lines=["line one", "line two"], returncode=0)
    captured = _patch_dispatch(monkeypatch, {"opencode": "fake-opencode.exe"}, [proc])

    run = runner.start(_FAKE_TARGET)
    assert run.status in ("queued", "running")
    assert _wait_status(runner, run.run_id) == "succeeded"

    finished = runner.get(run.run_id)
    assert finished is not None
    assert finished.exit_code == 0
    assert finished.error == ""
    assert finished.provider == "opencode"
    assert finished.model == _FAKE_MODEL

    # Command mirrors the frozen CLI contract.
    assert captured[0][0] == "fake-opencode.exe"
    assert captured[0][1:3] == ["run", "--file"]
    assert "registry" in " ".join(captured[0])

    # Log streamed to runtime/generate_logs/<run_id>.log
    log_tail = runner.log_tail(run.run_id)
    assert "line one" in log_tail
    assert "line two" in log_tail

    # History persisted as JSONL (append-only) with honest provider/model.
    history_path = workspace / "runtime" / "generate_runs.jsonl"
    assert history_path.is_file()
    records = [
        json.loads(line)
        for line in history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    record = [r for r in records if r["run_id"] == run.run_id][-1]
    assert record["provider"] == "opencode"
    assert record["model"] == _FAKE_MODEL


def test_start_failed_process_marks_run_failed(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(workspace)
    _patch_dispatch(
        monkeypatch,
        {"opencode": "fake-opencode.exe"},
        [_FakeProc(lines=["boom"], returncode=7)],
    )
    run = runner.start(_FAKE_TARGET)
    assert _wait_status(runner, run.run_id) == "failed"
    finished = runner.get(run.run_id)
    assert finished is not None
    assert finished.exit_code == 7
    assert finished.provider == "opencode"
    assert "exited with code 7" in finished.error


def test_start_unknown_target_raises(workspace: Path) -> None:
    runner = _runner(workspace)
    with pytest.raises(ValueError, match="Unknown target"):
        runner.start("no-such-target")


def test_start_missing_opencode_with_disabled_fallback_fails_fast(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(workspace, fallback=FallbackConfig(enabled=False))
    monkeypatch.setattr(
        "ai_company.services.generate_dispatch.shutil.which", lambda _name: None
    )
    with pytest.raises(ValueError, match="opencode"):
        runner.start(_FAKE_TARGET)


def test_cancel_terminates_and_records_cancelled(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(workspace)
    hold = threading.Event()
    proc = _FakeProc(lines=["started"], returncode=0, hold=hold)
    _patch_dispatch(monkeypatch, {"opencode": "fake-opencode.exe"}, [proc])

    run = runner.start(_FAKE_TARGET)
    # Wait until the worker thread reaches the blocking line.
    assert proc.arrived is not None
    assert proc.arrived.wait(timeout=5.0)

    cancelled = runner.cancel(run.run_id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    hold.set()  # release the worker; it must NOT overwrite the cancelled status
    time.sleep(0.2)
    assert runner.get(run.run_id) is not None
    assert runner.get(run.run_id).status == "cancelled"  # type: ignore[union-attr]


def test_history_reload_reconstructs_runs(workspace: Path) -> None:
    history_path = workspace / "runtime" / "generate_runs.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(
            {
                "run_id": "g1",
                "target": "registry",
                "status": "succeeded",
                "started_at": "2026-01-01T00:00:00+00:00",
                "finished_at": "2026-01-01T00:01:00+00:00",
                "exit_code": 0,
                "error": "",
                "log_path": "runtime/generate_logs/g1.log",
                "output_dir": "generated",
                "provider": "opencode",
                "model": _FAKE_MODEL,
            }
        )
        + "\n"
        + json.dumps(
            {
                "run_id": "g2",
                "target": "registry",
                "status": "running",
                "started_at": "2026-01-01T00:00:00+00:00",
                "finished_at": None,
                "exit_code": None,
                "error": "",
                "log_path": "runtime/generate_logs/g2.log",
                "output_dir": "generated",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    runner = _runner(workspace)
    g1 = runner.get("g1")
    assert g1 is not None and g1.status == "succeeded"
    assert g1.provider == "opencode"
    assert g1.model == _FAKE_MODEL
    g2 = runner.get("g2")
    assert g2 is not None and g2.status == "failed"
    assert "interrupted by restart" in g2.error


def test_list_targets_includes_command_map(workspace: Path) -> None:
    runner = _runner(workspace)
    names = [target.name for target in runner.list_targets()]
    assert "registry" in names
    assert "bootstrap" in names
    assert names == sorted(names)


def test_log_tail_unknown_run_is_empty(workspace: Path) -> None:
    runner = _runner(workspace)
    assert runner.log_tail("does-not-exist") == []


# ── R4 / D9: free-local fallback ────────────────────────────────────────── #


def test_fallback_used_when_opencode_fails(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(workspace)
    captured = _patch_dispatch(
        monkeypatch,
        {"opencode": "fake-opencode.exe", "ollama": "fake-ollama.exe"},
        [
            _FakeProc(lines=["opencode boom"], returncode=1),
            _FakeProc(lines=["ollama answer"], returncode=0),
        ],
    )

    run = runner.start(_FAKE_TARGET)
    assert _wait_status(runner, run.run_id) == "succeeded"

    finished = runner.get(run.run_id)
    assert finished is not None
    assert finished.exit_code == 0
    assert finished.provider == "local"
    assert finished.model == DEFAULT_FALLBACK_MODEL
    assert finished.error == ""

    # Both providers were attempted, in order: opencode then ollama.
    assert captured[0][0] == "fake-opencode.exe"
    assert captured[1] == ["fake-ollama.exe", "run", "llama3.1:8b"]

    # The log keeps the failed primary's output AND the fallback's output
    # (append mode): honest history of what actually happened.
    log_tail = runner.log_tail(run.run_id)
    assert "opencode boom" in log_tail
    assert "ollama answer" in log_tail

    history_path = workspace / "runtime" / "generate_runs.jsonl"
    records = [
        json.loads(line)
        for line in history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    record = [r for r in records if r["run_id"] == run.run_id][-1]
    assert record["provider"] == "local"
    assert record["model"] == DEFAULT_FALLBACK_MODEL


def test_fallback_used_when_opencode_missing(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(workspace)
    _patch_dispatch(
        monkeypatch,
        {"ollama": "fake-ollama.exe"},
        [_FakeProc(lines=["local answer"], returncode=0)],
    )

    run = runner.start(_FAKE_TARGET)
    assert _wait_status(runner, run.run_id) == "succeeded"

    finished = runner.get(run.run_id)
    assert finished is not None
    assert finished.exit_code == 0
    assert finished.provider == "local"
    assert finished.model == DEFAULT_FALLBACK_MODEL


def test_both_providers_missing_marks_run_failed(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(workspace)
    _patch_dispatch(monkeypatch, {}, [])

    run = runner.start(_FAKE_TARGET)
    assert _wait_status(runner, run.run_id) == "failed"

    finished = runner.get(run.run_id)
    assert finished is not None
    assert finished.exit_code is None
    assert "opencode not found on PATH" in finished.error
    assert "fallback unavailable" in finished.error


def test_fallback_disabled_keeps_strict_failure(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(workspace, fallback=FallbackConfig(enabled=False))
    _patch_dispatch(
        monkeypatch,
        {"opencode": "fake-opencode.exe"},
        [_FakeProc(lines=["boom"], returncode=7)],
    )

    run = runner.start(_FAKE_TARGET)
    assert _wait_status(runner, run.run_id) == "failed"

    finished = runner.get(run.run_id)
    assert finished is not None
    assert finished.provider == "opencode"
    assert finished.exit_code == 7
