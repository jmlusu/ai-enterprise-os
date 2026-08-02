"""Verify the CLI surface contract (additive-only rule, ADR 0006 / R8).

The CLI is a frozen surface: existing commands, their options and
arguments must never be renamed, removed, or changed - only *additive*
changes (new commands, new options) are allowed (R8 "CLI surface
frozen"). This check captures the full command tree via typer/click
introspection and compares it against a committed golden contract
(``src/ai_company/cli/cli_surface_contract.json``):

1. Every contract command must still exist (removal -> hard error).
2. Every contract param must still exist with identical flags and
   required-ness (change/removal -> hard error).
3. New commands/params are reported as additive drift; the contract must
   be regenerated with ``--update`` and committed alongside the change.

Run with::

    uv run python -m ai_company.integrity.check_cli_surface            # CI
    uv run python -m ai_company.integrity.check_cli_surface --update   # accept additive drift
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from click import Command, Parameter

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_FILE = REPO_ROOT / "src" / "ai_company" / "cli" / "cli_surface_contract.json"
CONTRACT_VERSION = 1


def _param_entry(param: Parameter) -> dict:
    """Serialize one click parameter into a stable contract entry."""
    return {
        "opts": sorted(param.opts),
        "required": bool(getattr(param, "required", False)),
    }


def describe_command(cmd: Command) -> dict:
    """Describe a command (or group) as a nested contract dict.

    Group detection is attribute-based (``commands`` dict present) rather
    than ``isinstance(cmd, Group)``: typer's ``TyperGroup`` is not always
    a ``click.Group`` subclass across typer versions (0.25 vs 0.27), but
    every group exposes a ``commands`` mapping.
    """
    entry: dict = {"params": {}}
    for param in cmd.params or []:
        entry["params"][param.name] = _param_entry(param)
    subcommands = getattr(cmd, "commands", None) or {}
    if subcommands:
        entry["commands"] = {
            name: describe_command(sub) for name, sub in sorted(subcommands.items())
        }
    return entry


def collect_surface(app: object) -> dict:
    """Capture the CLI surface of a typer app as a contract dict."""
    from typer.main import get_command

    root = get_command(app)
    return {
        "version": CONTRACT_VERSION,
        "commands": {
            name: describe_command(sub)
            for name, sub in sorted((root.commands or {}).items())
        },
    }


def _compare_commands(
    contract: dict, surface: dict, path: str, errors: list[str], additions: list[str]
) -> None:
    """Compare one command-tree level; appends violations to errors/additions."""
    contract_commands = contract.get("commands", {})
    surface_commands = surface.get("commands", {})

    for name, expected in sorted(contract_commands.items()):
        full = f"{path}{name}"
        actual = surface_commands.get(name)
        if actual is None:
            errors.append(
                f"command '{full}' was REMOVED (in contract, missing from CLI)"
            )
            continue
        for pname, expected_param in (expected.get("params") or {}).items():
            actual_param = (actual.get("params") or {}).get(pname)
            if actual_param is None:
                errors.append(
                    f"command '{full}': option/argument '{pname}' was REMOVED or "
                    f"RENAMED (in contract, missing from CLI)"
                )
                continue
            if sorted(actual_param.get("opts", [])) != sorted(
                expected_param.get("opts", [])
            ) or bool(actual_param.get("required")) != bool(
                expected_param.get("required")
            ):
                errors.append(
                    f"command '{full}': option/argument '{pname}' CHANGED "
                    f"(flags or required-ness differ from contract) - not additive"
                )
        if expected.get("commands") or actual.get("commands"):
            _compare_commands(expected, actual, f"{full} ", errors, additions)

    for name, actual in sorted(surface_commands.items()):
        full = f"{path}{name}"
        expected = contract_commands.get(name)
        if expected is None:
            additions.append(f"new command '{full}' (additive - accept with --update)")
            continue
        for pname in actual.get("params") or {}:
            if pname not in (expected.get("params") or {}):
                additions.append(
                    f"command '{full}': new option/argument '{pname}' "
                    f"(additive - accept with --update)"
                )
        if expected.get("commands") or actual.get("commands"):
            _compare_commands(expected, actual, f"{full} ", errors, additions)


def compare_surface(contract: dict, surface: dict) -> tuple[list[str], list[str]]:
    """Compare contract vs current surface.

    Returns ``(errors, additions)`` where errors are contract violations
    (removals/renames/changes - never allowed) and additions are new
    additive surface entries (allowed only via an ``--update`` commit).
    """
    errors: list[str] = []
    additions: list[str] = []
    _compare_commands(contract, surface, "", errors, additions)
    return errors, additions


def main(argv: list[str] | None = None) -> int:
    """Run the CLI surface check; return 0 when clean, 1 on violation,
    2 on additive drift needing --update."""
    args = list(argv if argv is not None else sys.argv[1:])
    update = "--update" in args

    from ai_company.cli.main import app as cli_app

    surface = collect_surface(cli_app)

    if update:
        CONTRACT_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONTRACT_FILE.write_text(
            json.dumps(surface, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        count = sum(len(c.get("commands", {})) for c in [surface])
        try:
            label = CONTRACT_FILE.relative_to(REPO_ROOT)
        except ValueError:
            label = CONTRACT_FILE
        print(f"CLI surface contract updated: {label}")
        print(f"commands recorded: {count}")
        return 0

    if not CONTRACT_FILE.is_file():
        print(f"ERROR: CLI surface contract missing: {CONTRACT_FILE}")
        print("Run with --update to create it.")
        return 1

    try:
        contract = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: {CONTRACT_FILE.name} is not valid JSON: {exc}")
        return 1

    errors, additions = compare_surface(contract, surface)

    for message in errors:
        print(f"ERROR: {message}")
    for message in additions:
        print(f"ADDED: {message}")

    if errors:
        print(
            f"\nCLI surface contract FAILED: {len(errors)} violation(s) - "
            "the CLI surface is frozen (ADR 0006); removals/renames/changes "
            "are not allowed."
        )
        return 1
    if additions:
        print(
            f"\nCLI surface contract: {len(additions)} additive addition(s) - "
            "re-run with --update and commit the regenerated contract."
        )
        return 2

    print("CLI surface contract OK (additive-only rule holds)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
