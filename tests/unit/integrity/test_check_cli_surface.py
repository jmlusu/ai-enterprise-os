"""Tests for the CLI surface integrity check (R8, additive-only rule).

The CLI surface is frozen (ADR 0006): removals, renames and changes are
contract violations; additions are allowed only with a regenerated
contract. These tests exercise the compare logic and the main() plumbing
against a small demo typer app so the real CLI is not required.
"""

from __future__ import annotations

import json

import pytest
import typer

from ai_company.integrity import check_cli_surface as mod


@pytest.fixture()
def demo_app() -> typer.Typer:
    """A small typer app with a nested group for surface capture."""

    app = typer.Typer()

    @app.command()
    def hello(
        name: str = typer.Argument(...),
        loud: bool = typer.Option(False, "--loud", help="Shout it"),
    ) -> None:
        """Greet someone."""

    tools = typer.Typer(help="toolbox")

    @tools.command()
    def ping(
        count: int = typer.Option(1, "--count", help="How many pings"),
    ) -> None:
        """Ping."""

    app.add_typer(tools, name="tools")
    return app


@pytest.fixture()
def demo_surface(demo_app: typer.Typer) -> dict:
    return mod.collect_surface(demo_app)


def test_collect_surface_records_nested_commands(
    demo_surface: dict,
) -> None:
    assert demo_surface["version"] == mod.CONTRACT_VERSION
    commands = demo_surface["commands"]
    assert "hello" in commands
    assert commands["hello"]["params"]["name"]["opts"] == ["name"]
    assert commands["hello"]["params"]["name"]["required"] is True
    assert commands["hello"]["params"]["loud"]["opts"] == ["--loud"]
    assert "tools" in commands
    assert "ping" in commands["tools"]["commands"]
    assert commands["tools"]["commands"]["ping"]["params"]["count"]["opts"] == [
        "--count"
    ]


def test_removed_command_is_error(demo_surface: dict, demo_app: typer.Typer) -> None:
    from typer.main import get_command

    root = get_command(demo_app)
    del root.commands["hello"]  # simulate a removal
    mutated = {
        "version": mod.CONTRACT_VERSION,
        "commands": {
            name: mod.describe_command(sub)
            for name, sub in sorted(root.commands.items())
        },
    }
    errors, additions = mod.compare_surface(demo_surface, mutated)
    assert any("hello" in e and "REMOVED" in e for e in errors)
    assert additions == []


def test_removed_option_is_error(demo_surface: dict, demo_app: typer.Typer) -> None:
    from typer.main import get_command

    root = get_command(demo_app)
    # delete the --loud param from the hello command
    hello_cmd = root.commands["hello"]
    hello_cmd.params = [p for p in hello_cmd.params if p.name != "loud"]
    mutated = {
        "version": mod.CONTRACT_VERSION,
        "commands": {
            name: mod.describe_command(sub)
            for name, sub in sorted(root.commands.items())
        },
    }
    errors, additions = mod.compare_surface(demo_surface, mutated)
    assert any("loud" in e and "REMOVED" in e for e in errors)
    assert additions == []


def test_changed_option_is_error(demo_surface: dict, demo_app: typer.Typer) -> None:
    from typer.main import get_command

    root = get_command(demo_app)
    hello_cmd = root.commands["hello"]
    # rename the flag (--loud -> --shout) — a change, not an addition
    param = next(p for p in hello_cmd.params if p.name == "loud")
    param.opts = ["--shout"]
    mutated = {
        "version": mod.CONTRACT_VERSION,
        "commands": {
            name: mod.describe_command(sub)
            for name, sub in sorted(root.commands.items())
        },
    }
    errors, additions = mod.compare_surface(demo_surface, mutated)
    assert any("loud" in e and "CHANGED" in e for e in errors)
    assert additions == []


def test_additions_reported_not_errors(demo_surface: dict) -> None:
    """New commands and new options are additive, never contract violations."""
    extended = typer.Typer()

    @extended.command()
    def hello(
        name: str = typer.Argument(...),
        loud: bool = typer.Option(False, "--loud", help="Shout it"),
        extra: bool = typer.Option(False, "--extra", help="New additive option"),
    ) -> None:
        """Greet someone."""

    @extended.command()
    def goodbye() -> None:
        """New additive command."""

    tools = typer.Typer(help="toolbox")

    @tools.command()
    def ping(count: int = typer.Option(1, "--count", help="How many pings")) -> None:
        """Ping."""

    extended.add_typer(tools, name="tools")

    errors, additions = mod.compare_surface(demo_surface, mod.collect_surface(extended))
    assert errors == []
    assert any("goodbye" in a and "additive" in a for a in additions)
    assert any("extra" in a and "additive" in a for a in additions)
    assert len(additions) == 2


def test_main_update_then_clean_pass(
    demo_surface: dict,
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = tmp_path / "contract.json"
    monkeypatch.setattr(mod, "CONTRACT_FILE", contract)
    monkeypatch.setattr(mod, "collect_surface", lambda app: demo_surface)

    assert mod.main(["--update"]) == 0
    assert contract.is_file()
    stored = json.loads(contract.read_text(encoding="utf-8"))
    assert "hello" in stored["commands"]

    assert mod.main([]) == 0


def test_main_fails_on_violation(
    demo_surface: dict,
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = tmp_path / "contract.json"
    monkeypatch.setattr(mod, "CONTRACT_FILE", contract)
    monkeypatch.setattr(mod, "collect_surface", lambda app: demo_surface)
    assert mod.main(["--update"]) == 0

    broken = dict(demo_surface)
    broken["commands"] = dict(demo_surface["commands"])
    del broken["commands"]["hello"]
    monkeypatch.setattr(mod, "collect_surface", lambda app: broken)

    assert mod.main([]) == 1


def test_main_returns_2_on_additive_drift(
    demo_surface: dict,
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = tmp_path / "contract.json"
    monkeypatch.setattr(mod, "CONTRACT_FILE", contract)
    monkeypatch.setattr(mod, "collect_surface", lambda app: demo_surface)
    assert mod.main(["--update"]) == 0

    extended = json.loads(json.dumps(demo_surface))
    extended["commands"] = dict(demo_surface["commands"])
    extended["commands"]["newcmd"] = {"params": {}}
    monkeypatch.setattr(mod, "collect_surface", lambda app: extended)

    assert mod.main([]) == 2
