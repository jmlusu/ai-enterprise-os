from pathlib import Path
import yaml
from pydantic import BaseModel, ValidationError
from rich import print

COMMAND_MAP_PATH = Path("src/ai_company/cli/command_map.yaml")


class CommandEntry(BaseModel):
    prompt_file: str
    agent: str
    model: str
    description: str = ""


def load_command_map() -> dict[str, CommandEntry]:
    if not COMMAND_MAP_PATH.exists():
        print(f"[red]Missing command map at {COMMAND_MAP_PATH}[/red]")
        raise SystemExit(1)

    raw = yaml.safe_load(COMMAND_MAP_PATH.read_text()) or {}

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
