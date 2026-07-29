from pathlib import Path

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
    result = runner.invoke(app, ["memory", "clear"])
    assert result.exit_code == 0
    assert "Clearing" in result.stdout


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
