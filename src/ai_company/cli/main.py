import os
import shutil
import subprocess

import typer
from rich import print

from ai_company.cli.command_map import load_command_map, resolve_target
from ai_company.cli.render import render_prompt

app = typer.Typer()


@app.command()
def targets() -> None:
    """List available generate targets."""
    command_map = load_command_map()
    for key, entry in command_map.items():
        print(f"[cyan]{key}[/cyan] - {entry.description}")


@app.command()
def generate(
    target: str = typer.Argument(..., help="e.g. bootstrap, registry, dashboard"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show the command without running it"
    ),
) -> None:
    """Dispatch a phase to OpenCode using its mapped prompt file."""
    entry = resolve_target(target)
    rendered_path = render_prompt(entry.prompt_file)

    opencode_path = shutil.which("opencode")
    if opencode_path is None:
        print(
            "[red]Could not find 'opencode' on PATH.[/red] Is it installed and available in this shell?"
        )
        raise typer.Exit(1)

    cmd = [
        opencode_path,
        "run",
        "--file",
        str(rendered_path),
        "--agent",
        entry.agent,
        "--model",
        entry.model,
        "Execute the attached prompt against the current company registry.",
    ]

    print(f"[cyan]Target:[/cyan] {target}  [dim]({entry.description})[/dim]")
    print(f"[cyan]Rendered prompt written to:[/cyan] {rendered_path}")
    print(f"[cyan]Command:[/cyan] {' '.join(cmd)}")

    if dry_run:
        print("[yellow]Dry run - command not executed.[/yellow]")
        return

    print(
        "[dim]Streaming opencode output below - this may take a while on a local model...[/dim]\n"
    )

    result = subprocess.run(cmd, check=False, shell=(os.name == "nt"))
    if result.returncode != 0:
        print(f"\n[red]opencode exited with error code {result.returncode}[/red]")
        raise typer.Exit(result.returncode)

    print("\n[green]opencode finished successfully.[/green]")


if __name__ == "__main__":
    app()
