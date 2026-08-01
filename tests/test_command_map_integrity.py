"""Phase 0 integrity gate (WS-0.1 / WS-0.3) — the CI check that prevents
command_map drift from recurring.

Guards:
1. Every `ai-company generate <target>` resolves to a real prompt file
   (no phantom phases — finding #1).
2. Every prompt in ``prompts/opencode/`` is reachable from the map
   (no dead prompts).
3. The `architect` agent dispatched by the map is defined in ``opencode.json``
   (two-sources-of-truth drift — finding #5).
4. `ai-company targets` (the advertised surface) matches the map.

Run in CI: the standard ``test`` job collects this file automatically.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ai_company.cli.command_map import load_command_map
from ai_company.cli.main import app

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / "prompts" / "opencode"
COMMAND_MAP = REPO_ROOT / "src" / "ai_company" / "cli" / "command_map.yaml"
OPENCODE_JSON = REPO_ROOT / "opencode.json"

runner = CliRunner()


def _real_prompt_files() -> set[str]:
    return {
        f"prompts/opencode/{p.name}" for p in PROMPTS_DIR.glob("*.md") if p.is_file()
    }


def test_command_map_loads() -> None:
    """The map must parse and validate (CommandEntry schema)."""
    command_map = load_command_map()
    assert command_map, "command map must not be empty"


def test_every_target_resolves_to_existing_prompt() -> None:
    """No phantom phases: every target's prompt_file must exist."""
    command_map = load_command_map()
    assert command_map, "command map must not be empty"
    missing = {
        f"{key} -> {entry.prompt_file}"
        for key, entry in command_map.items()
        if not (REPO_ROOT / entry.prompt_file).is_file()
    }
    assert not missing, f"targets with missing prompt files: {missing}"


def test_every_prompt_is_reachable() -> None:
    """No dead prompts: every real prompt file must be referenced by a target."""
    referenced = {entry.prompt_file for entry in load_command_map().values()}
    real = _real_prompt_files()
    unreachable = real - referenced
    assert not unreachable, f"prompt files not reachable from any target: {unreachable}"


def test_dispatch_agent_defined_in_opencode_json() -> None:
    """The architect agent dispatched by the map must exist in opencode.json."""
    data = json.loads(OPENCODE_JSON.read_text(encoding="utf-8"))
    agents = data.get("agent", {})
    command_map = load_command_map()
    dispatched = {entry.agent for entry in command_map.values()}
    undefined = dispatched - set(agents)
    assert not undefined, (
        f"agents dispatched by command_map but undefined in opencode.json: {undefined}"
    )


def test_targets_command_matches_map() -> None:
    """The advertised `ai-company targets` surface must match the map exactly."""
    command_map = load_command_map()
    result = runner.invoke(app, ["targets"])
    assert result.exit_code == 0
    for key in command_map:
        assert key in result.stdout, f"target '{key}' missing from `ai-company targets`"
