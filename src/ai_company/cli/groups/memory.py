from pathlib import Path

import typer

from ai_company.utils.console import console_print

app = typer.Typer(help="Manage AI agent memory and session state")

STATE_FILE = Path(".ai-company/state/current_sprint.yaml")


def _load_state() -> dict[str, str]:
    if not STATE_FILE.exists():
        return {}
    import yaml

    raw = STATE_FILE.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    return data if isinstance(data, dict) else {}


@app.command()
def show() -> None:
    """Display current memory state."""
    state = _load_state()
    console_print("[cyan]Current memory state:[/cyan]")
    if state:
        for k, v in state.items():
            console_print(f"  {k}: {v}")
    else:
        console_print("  [yellow]No state file found. Using defaults.[/yellow]")
        console_print("  Sprint: Phase 2 — Build First Business Feature")
        console_print("  Active tasks: Generate code, test, document")


@app.command()
def clear() -> None:
    """Clear session memory and reset state."""
    console_print("[yellow]Clearing session memory...[/yellow]")
    if STATE_FILE.exists():
        STATE_FILE.unlink()
        console_print("[green]State file removed.[/green]")
    else:
        console_print("[green]No state file to clear.[/green]")
