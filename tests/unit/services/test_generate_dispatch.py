"""Unit tests for generate dispatch with the free/local fallback (R4, D9).

``dispatch_generate`` is the shared seam used by both the streaming runner and
the frozen CLI. Tests stub ``shutil.which``/``subprocess.Popen`` on the module
globals so no real binary is ever spawned; ``load_fallback_config`` is tested
against real YAML files on disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_company.services.generate_dispatch import (
    DEFAULT_FALLBACK_MODEL,
    dispatch_generate,
    load_fallback_config,
)

_AGENT = "architect"
_MODEL = "opencode/north-mini-code-free"
_EXECUTE = "Execute the attached prompt against the current company registry."


class _FakeProc:
    """Stand-in for subprocess.Popen: yields stdout lines, waits with a code."""

    def __init__(self, lines: list[str], returncode: int) -> None:
        self._lines = lines
        self._rc = returncode

    @property
    def stdout(self) -> Any:
        return self

    def __iter__(self) -> Any:
        for line in self._lines:
            yield line + "\n"

    def wait(self) -> int:
        return self._rc


def _patch_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    which: dict[str, str],
    procs: list[_FakeProc],
) -> list[list[str]]:
    """Point which/Popen at fakes; return the captured command list."""
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


def _prompt(tmp_path: Path) -> Path:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Generate the artifact.", encoding="utf-8")
    return prompt


def test_dispatch_opencode_success_uses_primary_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompt = _prompt(tmp_path)
    captured = _patch_dispatch(
        monkeypatch, {"opencode": "/bin/opencode"}, [_FakeProc(["ok"], 0)]
    )
    outcome = dispatch_generate(
        agent=_AGENT,
        model=_MODEL,
        prompt_path=prompt,
        cwd=tmp_path,
        log_path=None,
    )

    assert outcome.provider == "opencode"
    assert outcome.model == _MODEL
    assert outcome.exit_code == 0
    assert outcome.used_fallback is False
    assert len(outcome.attempts) == 1

    # Command mirrors the frozen CLI contract exactly.
    assert captured[0] == [
        "/bin/opencode",
        "run",
        "--file",
        str(prompt),
        "--agent",
        _AGENT,
        "--model",
        _MODEL,
        _EXECUTE,
    ]


def test_dispatch_falls_back_when_opencode_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _patch_dispatch(
        monkeypatch,
        {"opencode": "/bin/opencode", "ollama": "/bin/ollama"},
        [_FakeProc(["boom"], 1), _FakeProc(["local ok"], 0)],
    )
    outcome = dispatch_generate(
        agent=_AGENT,
        model=_MODEL,
        prompt_path=_prompt(tmp_path),
        cwd=tmp_path,
        log_path=None,
    )

    assert outcome.provider == "local"
    assert outcome.model == DEFAULT_FALLBACK_MODEL
    assert outcome.exit_code == 0
    assert outcome.used_fallback is True
    assert len(outcome.attempts) == 2

    # Fallback runs the local model without the provider prefix.
    assert captured[1] == ["/bin/ollama", "run", "llama3.1:8b"]


def test_dispatch_falls_back_when_opencode_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dispatch(
        monkeypatch, {"ollama": "/bin/ollama"}, [_FakeProc(["local ok"], 0)]
    )
    outcome = dispatch_generate(
        agent=_AGENT,
        model=_MODEL,
        prompt_path=_prompt(tmp_path),
        cwd=tmp_path,
        log_path=None,
    )

    assert outcome.used_fallback is True
    assert outcome.provider == "local"
    assert outcome.exit_code == 0
    assert outcome.attempts[0].error == "opencode not found on PATH"


def test_dispatch_nothing_on_path_reports_none_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dispatch(monkeypatch, {}, [])
    outcome = dispatch_generate(
        agent=_AGENT,
        model=_MODEL,
        prompt_path=_prompt(tmp_path),
        cwd=tmp_path,
        log_path=None,
    )

    assert outcome.exit_code is None
    assert len(outcome.attempts) == 2
    assert outcome.attempts[0].error == "opencode not found on PATH"
    assert "fallback unavailable" in outcome.attempts[1].error


def test_dispatch_fallback_disabled_keeps_primary_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dispatch(
        monkeypatch,
        {"opencode": "/bin/opencode"},
        [_FakeProc(["boom"], 3)],
    )
    outcome = dispatch_generate(
        agent=_AGENT,
        model=_MODEL,
        prompt_path=_prompt(tmp_path),
        cwd=tmp_path,
        log_path=None,
        fallback_enabled=False,
    )

    assert outcome.provider == "opencode"
    assert outcome.exit_code == 3
    assert outcome.used_fallback is False
    assert len(outcome.attempts) == 1  # ollama never attempted


def test_dispatch_custom_fallback_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _patch_dispatch(
        monkeypatch,
        {"opencode": "/bin/opencode", "ollama": "/bin/ollama"},
        [_FakeProc(["boom"], 1), _FakeProc(["ok"], 0)],
    )
    outcome = dispatch_generate(
        agent=_AGENT,
        model=_MODEL,
        prompt_path=_prompt(tmp_path),
        cwd=tmp_path,
        log_path=None,
        fallback_model="ollama/qwen2.5:7b",
    )

    assert outcome.model == "ollama/qwen2.5:7b"
    assert captured[1] == ["/bin/ollama", "run", "qwen2.5:7b"]


def test_dispatch_registers_and_unregisters_active_proc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeProc(["ok"], 0)
    _patch_dispatch(monkeypatch, {"opencode": "/bin/opencode"}, [fake])
    events: list[Any] = []
    dispatch_generate(
        agent=_AGENT,
        model=_MODEL,
        prompt_path=_prompt(tmp_path),
        cwd=tmp_path,
        log_path=None,
        register_proc=events.append,
    )
    assert events == [fake, None]  # registered at spawn, unregistered at exit


def test_dispatch_streams_both_attempts_to_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_path = tmp_path / "runtime" / "generate_logs" / "run.log"
    _patch_dispatch(
        monkeypatch,
        {"opencode": "/bin/opencode", "ollama": "/bin/ollama"},
        [_FakeProc(["primary out"], 1), _FakeProc(["fallback out"], 0)],
    )
    outcome = dispatch_generate(
        agent=_AGENT,
        model=_MODEL,
        prompt_path=_prompt(tmp_path),
        cwd=tmp_path,
        log_path=log_path,
    )
    assert outcome.exit_code == 0
    text = log_path.read_text(encoding="utf-8")
    assert "primary out" in text
    assert "fallback out" in text


# ── fallback config loading ─────────────────────────────────────────────── #


def test_load_fallback_config_defaults_when_missing(tmp_path: Path) -> None:
    config = load_fallback_config(tmp_path)
    assert config.enabled is True
    assert config.provider == "ollama"
    assert config.model == DEFAULT_FALLBACK_MODEL


def test_load_fallback_config_reads_yaml(tmp_path: Path) -> None:
    target = tmp_path / "runtime" / "model_fallback.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        'fallback:\n  enabled: false\n  provider: "ollama"\n  model: "ollama/qwen3:4b"\n',
        encoding="utf-8",
    )
    config = load_fallback_config(tmp_path)
    assert config.enabled is False
    assert config.provider == "ollama"
    assert config.model == "ollama/qwen3:4b"


def test_load_fallback_config_broken_yaml_returns_defaults(tmp_path: Path) -> None:
    target = tmp_path / "runtime" / "model_fallback.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("fallback: [unclosed\n", encoding="utf-8")
    config = load_fallback_config(tmp_path)
    assert config.enabled is True
    assert config.model == DEFAULT_FALLBACK_MODEL
