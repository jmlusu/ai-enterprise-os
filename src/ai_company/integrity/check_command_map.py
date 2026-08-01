"""Verify the command map <-> prompts/opencode/ <-> opencode.json contract.

The command map (``src/ai_company/cli/command_map.yaml``) is the contract
that drives ``ai-company generate <target>``: each target resolves to a
prompt file under ``prompts/opencode/``, an OpenCode agent, and a model.

This module verifies the contract end-to-end so drift fails the build
instead of surfacing at runtime:

1. Every ``command_map.yaml`` entry references an existing prompt file.
2. Every entry's ``agent`` is defined in ``opencode.json`` (when present).
3. Every entry has a non-empty ``model`` in ``provider/model`` form.
4. Every prompt file under ``prompts/opencode/`` is reachable from at
   least one target (no orphan prompts).

Run with:

    uv run python -m ai_company.integrity.check_command_map
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMAND_MAP = REPO_ROOT / "src" / "ai_company" / "cli" / "command_map.yaml"
OPENCODE_CONFIG = REPO_ROOT / "opencode.json"
PROMPTS_DIR = REPO_ROOT / "prompts" / "opencode"

_ERROR_COUNT: int = 0


def _fail(message: str) -> None:
    """Record an integrity violation and print it."""
    global _ERROR_COUNT
    _ERROR_COUNT += 1
    print(f"ERROR: {message}")


def check_command_map_prompt_files(raw: dict[str, dict]) -> None:
    """Check 1: every target's prompt file exists on disk."""
    for target, entry in raw.items():
        prompt_file = entry.get("prompt_file", "")
        if not prompt_file:
            _fail(f"target '{target}' has no prompt_file")
            continue
        path = REPO_ROOT / prompt_file
        if not path.is_file():
            _fail(
                f"target '{target}' prompt_file not found: {prompt_file} "
                f"(expected at {path})"
            )


def check_command_map_agents(raw: dict[str, dict]) -> set[str]:
    """Check 2: every target's agent is defined in opencode.json."""
    agents: set[str] = set()
    if not OPENCODE_CONFIG.is_file():
        print(f"WARN: {OPENCODE_CONFIG.name} missing - skipping agent existence check")
        return agents
    try:
        data = json.loads(OPENCODE_CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail(f"{OPENCODE_CONFIG.name} is not valid JSON: {exc}")
        return agents
    defined = set((data.get("agent") or {}).keys())
    for target, entry in raw.items():
        agent = entry.get("agent", "")
        if not agent:
            _fail(f"target '{target}' has no agent")
            continue
        agents.add(agent)
        if agent not in defined:
            _fail(
                f"target '{target}' references agent '{agent}' which is not "
                f"defined in {OPENCODE_CONFIG.name} (defined: "
                f"{', '.join(sorted(defined)) or 'none'})"
            )
    return agents


def check_command_map_models(raw: dict[str, dict]) -> None:
    """Check 3: every target's model is a non-empty provider/model."""
    for target, entry in raw.items():
        model = entry.get("model", "")
        if not model:
            _fail(f"target '{target}' has no model")
            continue
        provider, sep, _name = model.partition("/")
        if not sep or not provider or not _name:
            _fail(f"target '{target}' model '{model}' is not in 'provider/model' form")


def check_orphan_prompts(raw: dict[str, dict]) -> None:
    """Check 4: every prompt file under prompts/opencode/ is reachable."""
    if not PROMPTS_DIR.is_dir():
        _fail(f"prompts directory missing: {PROMPTS_DIR}")
        return
    referenced = {entry.get("prompt_file", "") for entry in raw.values()}
    for prompt_path in sorted(PROMPTS_DIR.glob("*.md")):
        relative = prompt_path.relative_to(REPO_ROOT).as_posix()
        if relative not in referenced:
            _fail(
                f"orphan prompt file not reachable from any command_map.yaml "
                f"target: {relative}"
            )


def main(argv: list[str] | None = None) -> int:
    """Run all command-map integrity checks; return 0 when clean."""
    if not COMMAND_MAP.is_file():
        _fail(f"command map missing: {COMMAND_MAP}")
        return 1
    raw = yaml.safe_load(COMMAND_MAP.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        _fail(f"{COMMAND_MAP.name} does not contain a mapping")
        return 1

    check_command_map_prompt_files(raw)
    check_command_map_agents(raw)
    check_command_map_models(raw)
    check_orphan_prompts(raw)

    if _ERROR_COUNT:
        print(f"\ncommand map integrity FAILED: {_ERROR_COUNT} issue(s)")
        return 1
    target_count = len(raw)
    print(
        f"command map integrity OK: {target_count} target(s), "
        f"{len(list(PROMPTS_DIR.glob('*.md')))} prompt file(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
