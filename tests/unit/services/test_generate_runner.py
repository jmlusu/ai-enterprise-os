"""Unit tests for the streaming generate dispatcher (Phase 2 wave 2b).

The runner shells out to the local ``opencode`` binary exactly like the
frozen CLI; tests substitute a fake process (Popen + shutil.which) so the
dispatch lifecycle, log streaming, and history persistence are verified
without invoking a real model.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from ai_company.services.generate_runner import GenerateRunner

_FAKE_TARGET = "registry"
_FAKE_TARGET_PROMPT = "prompts/opencode/02_registry_engine.md"


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


def _runner(workspace: Path) -> GenerateRunner:
    return GenerateRunner(root=str(workspace))


def _patch_opencode(
    monkeypatch: pytest.MonkeyPatch,
    proc: _FakeProc,
) -> list[list[str]]:
    """Point shutil.which + subprocess.Popen at the fake process."""
    monkeypatch.setattr(
        "ai_company.services.generate_runner.shutil.which",
        lambda _name: "fake-opencode.exe",
    )
    captured: list[list[str]] = []

    def _fake_popen(cmd: list[str], **kwargs: Any) -> _FakeProc:
        captured.append(cmd)
        return proc

    monkeypatch.setattr(
        "ai_company.services.generate_runner.subprocess.Popen", _fake_popen
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
    captured = _patch_opencode(monkeypatch, proc)

    run = runner.start(_FAKE_TARGET)
    assert run.status in ("queued", "running")
    assert _wait_status(runner, run.run_id) == "succeeded"

    finished = runner.get(run.run_id)
    assert finished is not None
    assert finished.exit_code == 0
    assert finished.error == ""

    # Command mirrors the frozen CLI contract.
    assert captured[0][0] == "fake-opencode.exe"
    assert captured[0][1:3] == ["run", "--file"]
    assert "registry" in " ".join(captured[0])

    # Log streamed to runtime/generate_logs/<run_id>.log
    log_tail = runner.log_tail(run.run_id)
    assert "line one" in log_tail
    assert "line two" in log_tail

    # History persisted as JSONL (append-only).
    history_path = workspace / "runtime" / "generate_runs.jsonl"
    assert history_path.is_file()
    records = [
        json.loads(line)
        for line in history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(record["run_id"] == run.run_id for record in records)


def test_start_failed_process_marks_run_failed(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(workspace)
    _patch_opencode(monkeypatch, _FakeProc(lines=["boom"], returncode=7))
    run = runner.start(_FAKE_TARGET)
    assert _wait_status(runner, run.run_id) == "failed"
    finished = runner.get(run.run_id)
    assert finished is not None
    assert finished.exit_code == 7
    assert "exited with code 7" in finished.error


def test_start_unknown_target_raises(workspace: Path) -> None:
    runner = _runner(workspace)
    with pytest.raises(ValueError, match="Unknown target"):
        runner.start("no-such-target")


def test_start_missing_opencode_fails_fast(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(workspace)
    monkeypatch.setattr(
        "ai_company.services.generate_runner.shutil.which", lambda _name: None
    )
    with pytest.raises(ValueError, match="opencode"):
        runner.start(_FAKE_TARGET)


def test_cancel_terminates_and_records_cancelled(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _runner(workspace)
    hold = threading.Event()
    proc = _FakeProc(lines=["started"], returncode=0, hold=hold)
    _patch_opencode(monkeypatch, proc)

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
