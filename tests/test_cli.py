from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from ai_company.cli.main import app

runner = CliRunner()


def test_bootstrap() -> None:
    result = runner.invoke(app, ["bootstrap"])
    assert result.exit_code == 0
    assert "Bootstrapping" in result.stdout


def test_bootstrap_missing_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil
    import tempfile

    temp_dir = Path(tempfile.mkdtemp())
    try:
        monkeypatch.chdir(temp_dir)
        result = runner.invoke(app, ["bootstrap"])
        assert result.exit_code == 1
        assert "not found" in result.stdout
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_build() -> None:
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 0
    assert "Building" in result.stdout


def test_generate_dry_run() -> None:
    result = runner.invoke(app, ["generate", "bootstrap", "--dry-run"])
    assert result.exit_code == 0
    assert "Target:" in result.stdout
    assert "Dry run" in result.stdout


def test_generate_unknown_target() -> None:
    result = runner.invoke(app, ["generate", "nope", "--dry-run"])
    assert result.exit_code == 1
    assert "Unknown target" in result.stdout


def _patch_generate_dispatch(monkeypatch: pytest.MonkeyPatch, outcome: Any) -> None:
    """Route the CLI generate command through a fixed dispatch outcome."""
    monkeypatch.setattr(
        "ai_company.cli.main.dispatch_generate",
        lambda **kwargs: outcome,
    )
    monkeypatch.setattr(
        "ai_company.cli.main.render_prompt",
        lambda prompt_file: Path(prompt_file),
    )


def _outcome(
    provider: str,
    model: str,
    exit_code: int | None,
    attempts: list[tuple[str, str, int | None, str]],
) -> Any:
    from ai_company.services.generate_dispatch import DispatchAttempt, DispatchOutcome

    return DispatchOutcome(
        provider=provider,
        model=model,
        exit_code=exit_code,
        attempts=tuple(DispatchAttempt(p, m, rc, err) for p, m, rc, err in attempts),
    )


def test_generate_dispatch_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_generate_dispatch(
        monkeypatch,
        _outcome(
            "opencode",
            "opencode/north-mini-code-free",
            0,
            [("opencode", "opencode/north-mini-code-free", 0, "")],
        ),
    )
    result = runner.invoke(app, ["generate", "bootstrap"])
    assert result.exit_code == 0
    assert "opencode finished successfully" in result.stdout


def test_generate_dispatch_fallback_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_generate_dispatch(
        monkeypatch,
        _outcome(
            "local",
            "ollama/llama3.1:8b",
            0,
            [
                (
                    "opencode",
                    "opencode/north-mini-code-free",
                    1,
                    "opencode exited with code 1",
                ),
                ("local", "ollama/llama3.1:8b", 0, ""),
            ],
        ),
    )
    result = runner.invoke(app, ["generate", "bootstrap"])
    assert result.exit_code == 0
    assert "fallback provider 'local'" in result.stdout
    assert "local finished successfully" in result.stdout


def test_generate_dispatch_failure_exits_with_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_generate_dispatch(
        monkeypatch,
        _outcome(
            "opencode",
            "opencode/north-mini-code-free",
            7,
            [
                (
                    "opencode",
                    "opencode/north-mini-code-free",
                    7,
                    "opencode exited with code 7",
                )
            ],
        ),
    )
    result = runner.invoke(app, ["generate", "bootstrap"])
    assert result.exit_code == 7
    assert "failed with code 7" in result.stdout


def test_generate_dispatch_nothing_on_path_exits_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_generate_dispatch(
        monkeypatch,
        _outcome(
            "local",
            "ollama/llama3.1:8b",
            None,
            [
                (
                    "opencode",
                    "opencode/north-mini-code-free",
                    None,
                    "opencode not found on PATH",
                ),
                (
                    "local",
                    "ollama/llama3.1:8b",
                    None,
                    "fallback unavailable: 'ollama' not found on PATH",
                ),
            ],
        ),
    )
    result = runner.invoke(app, ["generate", "bootstrap"])
    assert result.exit_code == 1
    assert "opencode not found on PATH" in result.stdout


def test_validate() -> None:
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0
    assert "Validating" in result.stdout


def test_doctor() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "diagnostics" in result.stdout.lower()


def test_targets() -> None:
    result = runner.invoke(app, ["targets"])
    assert result.exit_code == 0
    assert "bootstrap" in result.stdout


def test_status() -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Status" in result.stdout or "status" in result.stdout.lower()


def test_registry_list() -> None:
    result = runner.invoke(app, ["registry", "list"])
    assert result.exit_code == 0
    assert "Vision" in result.stdout


def test_registry_show() -> None:
    result = runner.invoke(app, ["registry", "show", "vision"])
    assert result.exit_code == 0
    assert "AI Enterprise OS Vision" in result.stdout


def test_registry_verify() -> None:
    result = runner.invoke(app, ["registry", "verify"])
    assert result.exit_code == 0
    assert "Verifying" in result.stdout


def test_memory_show() -> None:
    result = runner.invoke(app, ["memory", "show"])
    assert result.exit_code == 0
    assert "memory" in result.stdout.lower()


def test_memory_clear() -> None:
    result = runner.invoke(app, ["memory", "clear"], input="y\n")
    assert result.exit_code == 0
    assert "All memories cleared" in result.stdout


def test_graph_show() -> None:
    result = runner.invoke(app, ["graph", "show"])
    assert result.exit_code == 0
    assert "Graph" in result.stdout


def test_graph_stats() -> None:
    result = runner.invoke(app, ["graph", "stats"])
    assert result.exit_code == 0
    assert "statistics" in result.stdout.lower()


def test_report_generate() -> None:
    result = runner.invoke(app, ["report", "generate", "summary"])
    assert result.exit_code == 0
    assert "Generating" in result.stdout


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    commands = [
        "bootstrap",
        "build",
        "generate",
        "validate",
        "doctor",
        "targets",
        "status",
        "registry",
        "memory",
        "graph",
        "report",
    ]
    for cmd in commands:
        assert cmd in result.stdout
