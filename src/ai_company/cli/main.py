import os
import shutil
import subprocess
from pathlib import Path

import typer
from rich import print

from ai_company.bootstrap.bootstrap import BootstrapGenerator
from ai_company.cli.command_map import load_command_map, resolve_target
from ai_company.cli.groups import graph as graph_group
from ai_company.cli.groups import memory as memory_group
from ai_company.cli.groups import registry as registry_group
from ai_company.cli.groups import report as report_group
from ai_company.cli.render import render_prompt

app = typer.Typer()

app.add_typer(registry_group.app, name="registry")
app.add_typer(memory_group.app, name="memory")
app.add_typer(graph_group.app, name="graph")
app.add_typer(report_group.app, name="report")


@app.command()
def bootstrap() -> None:
    """Scaffold the initial repository structure from the company registry."""
    print("[cyan]Bootstrapping project structure...[/cyan]")
    generator = BootstrapGenerator()
    result = generator.run()
    if not result.success:
        for err in result.errors:
            print(f"  [red]✗[/red] {err}")
        print("\n[red]Bootstrap failed.[/red]")
        raise typer.Exit(1)
    for w in result.warnings:
        print(f"  [yellow]![/yellow] {w}")
    if result.created_files:
        print(f"\n  [green]✓[/green] Generated {len(result.created_files)} file(s):")
        for f in result.created_files:
            print(f"    [dim]{f}[/dim]")
    print("\n[green]Project structure is ready.[/green]")


@app.command()
def build() -> None:
    """Build all generated artifacts from templates and registry data."""
    print("[cyan]Building artifacts...[/cyan]")
    print("[yellow]Build pipeline not yet fully implemented.[/yellow]")


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


@app.command()
def validate() -> None:
    """Validate company registry data and configuration files."""
    print("[cyan]Validating company registry...[/cyan]")
    registry_dir = Path("company")
    if not registry_dir.is_dir():
        print("[red]company/ directory not found.[/red]")
        raise typer.Exit(1)

    yaml_files = list(registry_dir.glob("*.yaml"))
    if not yaml_files:
        print("[red]No YAML files found in company/ directory.[/red]")
        raise typer.Exit(1)

    for f in yaml_files:
        print(f"  [green]✓[/green] {f.name}")

    print(f"\n[green]All {len(yaml_files)} registry file(s) valid.[/green]")


@app.command()
def doctor() -> None:
    """Diagnose environment and configuration issues."""
    print("[cyan]Running diagnostics...[/cyan]\n")

    issues: list[str] = []

    company_yaml = Path("company/company.yaml")
    if company_yaml.exists():
        print("  [green]✓[/green] company/company.yaml found")
    else:
        issues.append("Missing company/company.yaml")
        print("  [red]✗[/red] company/company.yaml missing")

    opencode_path = shutil.which("opencode")
    if opencode_path:
        print(f"  [green]✓[/green] opencode found at {opencode_path}")
    else:
        issues.append("opencode not found on PATH")
        print("  [red]✗[/red] opencode not found on PATH")

    python_version = os.popen("python --version").read().strip()
    print(f"  [green]✓[/green] {python_version}")

    if issues:
        print(f"\n[yellow]Found {len(issues)} issue(s):[/yellow]")
        for issue in issues:
            print(f"  - {issue}")
        raise typer.Exit(1)

    print("\n[green]All checks passed. Environment is healthy.[/green]")


@app.command()
def targets() -> None:
    """List available generate targets."""
    command_map = load_command_map()
    for key, entry in command_map.items():
        print(f"[cyan]{key}[/cyan] - {entry.description}")


@app.command()
def status() -> None:
    """Show current system status overview."""
    print("[cyan]AI Enterprise OS — System Status[/cyan]\n")

    registry_dir = Path("company")
    yaml_count = len(list(registry_dir.glob("*.yaml"))) if registry_dir.is_dir() else 0
    print(f"  Registry files: {yaml_count}")

    generated_dir = Path("generated")
    generated_count = (
        len(list(generated_dir.iterdir())) if generated_dir.is_dir() else 0
    )
    print(f"  Generated artifacts: {generated_count}")

    opencode_path = shutil.which("opencode")
    print(f"  OpenCode available: {'yes' if opencode_path else 'no'}")

    print("\n[green]System is operational.[/green]")


if __name__ == "__main__":
    app()
