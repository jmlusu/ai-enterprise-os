from importlib.resources import files as resource_files
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError
from rich import print

_COMMAND_MAP_RESOURCE = resource_files("ai_company.cli") / "command_map.yaml"
_command_map_cache: dict[str, dict[str, "CommandEntry"]] = {}


class CommandEntry(BaseModel):
    prompt_file: str
    agent: str
    model: str
    description: str = ""


def load_command_map() -> dict[str, CommandEntry]:
    cache_key = str(_COMMAND_MAP_RESOURCE)
    if cache_key in _command_map_cache:
        return dict(_command_map_cache[cache_key])

    try:
        raw_text = _COMMAND_MAP_RESOURCE.read_text(encoding="utf-8")
    except FileNotFoundError:
        print("[red]Missing command map resource[/red]")
        raise SystemExit(1)

    raw = yaml.safe_load(raw_text) or {}

    validated: dict[str, CommandEntry] = {}
    errors: list[str] = []

    for key, entry in raw.items():
        try:
            validated[key] = CommandEntry(**entry)
        except ValidationError as e:
            errors.append(f"'{key}': {e}")

    if errors:
        print("[red]command_map.yaml has invalid entries:[/red]")
        for err in errors:
            print(f"  - {err}")
        raise SystemExit(1)

    _command_map_cache[cache_key] = dict(validated)
    return validated


def resolve_target(target: str) -> CommandEntry:
    command_map = load_command_map()

    if target not in command_map:
        available = ", ".join(sorted(command_map.keys()))
        print(f"[red]Unknown target:[/red] '{target}'")
        print(f"[yellow]Available targets:[/yellow] {available}")
        raise SystemExit(1)

    entry = command_map[target]

    prompt_path = Path(entry.prompt_file)
    if not prompt_path.exists():
        print(f"[red]Prompt file for '{target}' not found:[/red] {entry.prompt_file}")
        raise SystemExit(1)

    return entry
