import shutil
import subprocess
import sys
import time
from pathlib import Path

import typer

from ai_company.bootstrap.bootstrap import BootstrapGenerator
from ai_company.cli.command_map import load_command_map, resolve_target
from ai_company.cli.groups import company_cli as company_group
from ai_company.cli.groups import executive as executive_group
from ai_company.cli.groups import graph as graph_group
from ai_company.cli.groups import memory as memory_group
from ai_company.cli.groups import orchestration as orchestration_group
from ai_company.cli.groups import registry as registry_group
from ai_company.cli.groups import report as report_group
from ai_company.cli.groups import runtime as runtime_group
from ai_company.cli.render import render_prompt
from ai_company.company.generator import CompanyGenerator
from ai_company.telemetry.cli import record_cli_invocation
from ai_company.utils.console import configure_console, console_print
from ai_company.validator.engine import ValidatorEngine

app = typer.Typer()

# Configure cross-platform console at startup
configure_console()

app.add_typer(company_group.app, name="company")
app.add_typer(executive_group.app, name="exec")
app.add_typer(registry_group.app, name="registry")
app.add_typer(memory_group.app, name="memory")
app.add_typer(graph_group.app, name="graph")
app.add_typer(report_group.app, name="report")
app.add_typer(orchestration_group.app, name="orchestrate")
app.add_typer(runtime_group.app, name="runtime")


@app.callback()
def _telemetry_start(ctx: typer.Context) -> None:
    """Record the invocation start time and register a finish hook.

    Baseline CLI telemetry (Phase 0 WS-0.4): every invocation is recorded as
    one JSONL event in runtime/cli_telemetry.jsonl (fail-open, never breaks
    the CLI). The finish hook uses the click-supported ``Context.call_on_close``
    API -- ``typer.Typer.result_callback`` does not exist in typer 0.27.0 --
    so the record fires after the command completes, including sub-commands
    and failed invocations.
    """
    started_at = time.monotonic()
    ctx.meta["telemetry_started_at"] = started_at

    def _finish() -> None:
        record_cli_invocation(
            argv=list(sys.argv[1:]),
            duration_seconds=round(time.monotonic() - started_at, 4),
        )

    ctx.call_on_close(_finish)


@app.command()
def bootstrap() -> None:
    """Scaffold the project structure and generate the full company."""
    console_print("[cyan]Bootstrapping project structure...[/cyan]")
    generator = BootstrapGenerator()
    result = generator.run()
    if not result.success:
        for err in result.errors:
            console_print(f"  [red]✗[/red] {err}")
        console_print("\n[red]Bootstrap failed.[/red]")
        raise typer.Exit(1)
    for w in result.warnings:
        console_print(f"  [yellow]![/yellow] {w}")
    if result.created_files:
        console_print(
            f"  [green]✓[/green] Scaffolded {len(result.created_files)} file(s)"
        )

    console_print("[cyan]Generating company artifacts...[/cyan]")
    company_gen = CompanyGenerator()
    all_result = company_gen.generate_all()
    for name, summary in all_result.summaries.items():
        parts = ", ".join(f"{k}={v}" for k, v in summary.items())
        console_print(f"  [green]✓[/green] {name:<14} {parts}")
    for w in all_result.warnings:
        console_print(f"  [yellow]![/yellow] {w}")
    console_print(
        f"  [green]✓[/green] Generated {len(all_result.created_files)} artifact file(s)"
    )

    engine = ValidatorEngine()
    validation = engine.validate_all()
    console_print(f"  [green]✓[/green] {validation.summary()}")

    console_print("\n[green]Company bootstrap complete.[/green]")


@app.command()
def build() -> None:
    """Build all generated artifacts from templates and registry data."""
    console_print("[cyan]Building artifacts...[/cyan]")

    generator = BootstrapGenerator()
    result = generator.run()
    if not result.success:
        for err in result.errors:
            console_print(f"  [red]✗[/red] {err}")
        console_print("\n[red]Build failed during bootstrap.[/red]")
        raise typer.Exit(1)

    for w in result.warnings:
        console_print(f"  [yellow]![/yellow] {w}")
    if result.created_files:
        console_print(
            f"  [green]✓[/green] Scaffolded {len(result.created_files)} file(s)"
        )

    company_gen = CompanyGenerator()
    all_result = company_gen.generate_all()
    for name, summary in all_result.summaries.items():
        parts = ", ".join(f"{k}={v}" for k, v in summary.items())
        console_print(f"  [green]✓[/green] {name:<14} {parts}")
    for w in all_result.warnings:
        console_print(f"  [yellow]![/yellow] {w}")
    console_print(
        f"  [green]✓[/green] Generated {len(all_result.created_files)} artifact file(s)"
    )

    engine = ValidatorEngine()
    validation = engine.validate_all()
    console_print(f"  [green]✓[/green] {validation.summary()}")

    console_print("\n[green]Build complete.[/green]")


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

    console_print(f"[cyan]Target:[/cyan] {target}  [dim]({entry.description})[/dim]")
    console_print(f"[cyan]Rendered prompt written to:[/cyan] {rendered_path}")

    if dry_run:
        console_print("[yellow]Dry run - command not executed.[/yellow]")
        return

    opencode_path = shutil.which("opencode")
    if opencode_path is None:
        console_print(
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

    console_print(f"[cyan]Command:[/cyan] {' '.join(cmd)}")

    console_print(
        "[dim]Streaming opencode output below - this may take a while on a local model...[/dim]\n"
    )

    result = subprocess.run(cmd, check=False, shell=False)
    if result.returncode != 0:
        console_print(
            f"\n[red]opencode exited with error code {result.returncode}[/red]"
        )
        raise typer.Exit(result.returncode)

    console_print("\n[green]opencode finished successfully.[/green]")


@app.command()
def validate() -> None:
    """Validate company registry data and configuration files."""
    console_print("[cyan]Validating company registry...[/cyan]")
    engine = ValidatorEngine()
    result = engine.validate_all()
    console_print(f"\n[dim]{result.summary()}[/dim]")
    for report in result.reports:
        status = "[green]PASS[/green]" if report.passed else "[red]FAIL[/red]"
        console_print(f"  {status} {report.target}")
        for err in report.errors:
            console_print(f"       [red]✗[/red] {err.message}")
        for w in report.warnings:
            console_print(f"       [yellow]![/yellow] {w.message}")
    if not result.passed:
        raise typer.Exit(1)
    console_print("\n[green]Validation complete.[/green]")


@app.command()
def doctor(
    force_ascii: bool = typer.Option(
        False, "--force-ascii", help="Use ASCII-only output (safe for all terminals)"
    ),
) -> None:
    """Diagnose environment and configuration issues."""
    if force_ascii:
        configure_console(force_ascii=True)

    try:
        _doctor_run()
    except (UnicodeEncodeError, UnicodeDecodeError) as e:
        configure_console(force_ascii=True)
        console_print(
            f"[yellow]Terminal encoding issue ({e.reason}), retrying with ASCII fallback...[/yellow]"
        )
        _doctor_run()


def _doctor_run() -> None:
    console_print("[cyan]Running diagnostics...[/cyan]\n")

    issues: list[str] = []

    company_yaml = Path("company/company.yaml")
    if company_yaml.exists():
        console_print("  [green]OK[/green] company/company.yaml found")
    else:
        issues.append("Missing company/company.yaml")
        console_print("  [red]X[/red] company/company.yaml missing")

    opencode_path = shutil.which("opencode")
    if opencode_path:
        console_print(f"  [green]OK[/green] opencode found at {opencode_path}")
    else:
        issues.append("opencode not found on PATH")
        console_print("  [red]X[/red] opencode not found on PATH")

    python_version = sys.version
    console_print(f"  [green]OK[/green] Python {python_version}")

    if issues:
        console_print(f"\n[yellow]Found {len(issues)} issue(s):[/yellow]")
        for issue in issues:
            console_print(f"  - {issue}")
    else:
        console_print("\n[green]All checks passed. Environment is healthy.[/green]")


@app.command()
def targets() -> None:
    """List available generate targets."""
    command_map = load_command_map()
    for key, entry in command_map.items():
        console_print(f"[cyan]{key}[/cyan] - {entry.description}")


@app.command()
def status() -> None:
    """Show current system status overview."""
    console_print("[cyan]AI Enterprise OS — System Status[/cyan]\n")

    registry_dir = Path("company")
    yaml_count = len(list(registry_dir.glob("*.yaml"))) if registry_dir.is_dir() else 0
    console_print(f"  Registry files: {yaml_count}")

    generated_dir = Path("generated")
    generated_count = (
        len(list(generated_dir.iterdir())) if generated_dir.is_dir() else 0
    )
    console_print(f"  Generated artifacts: {generated_count}")

    opencode_path = shutil.which("opencode")
    console_print(f"  OpenCode available: {'yes' if opencode_path else 'no'}")

    console_print("\n[green]System is operational.[/green]")


if __name__ == "__main__":
    app()
