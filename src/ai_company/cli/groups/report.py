from pathlib import Path

import typer

from ai_company.registry.registry import RegistryEngine
from ai_company.utils.console import console_print
from ai_company.validator.engine import ValidatorEngine

app = typer.Typer(help="Generate reports from registry and state data")


@app.command()
def generate(
    report_type: str = typer.Argument(
        default="summary", help="Report type (summary, detailed, health)"
    ),
) -> None:
    """Generate a report of the specified type."""
    console_print(f"[cyan]Generating report:[/cyan] {report_type}")

    if report_type == "summary":
        engine = RegistryEngine()
        result = engine.load(Path("company"))
        if result.registry is None:
            console_print("[red]No registry loaded.[/red]")
            raise typer.Exit(1)
        reg = result.registry
        console_print(f"\n  Company: {reg.vision.company_name or reg.vision.name}")
        console_print(f"  Vision: {reg.vision.name}")
        console_print(f"  Departments: {len(reg.departments)}")
        total_roles = sum(len(d.roles) for d in reg.departments.values())
        console_print(f"  Roles: {total_roles}")
        console_print(f"  Board members: {len(reg.board)}")
        console_print(f"  Workflows: {len(reg.workflows)}")
        if result.warnings:
            for warn in result.warnings:
                console_print(f"  [yellow]![/yellow] {warn}")

    elif report_type == "detailed":
        engine = RegistryEngine()
        result = engine.load(Path("company"))
        if result.registry is None:
            console_print("[red]No registry loaded.[/red]")
            raise typer.Exit(1)
        reg = result.registry
        console_print(f"\n  Vision: {reg.vision.name}")
        if reg.vision.description:
            console_print(f"  Description: {reg.vision.description}")
        if reg.vision.company_name:
            console_print(f"  Company: {reg.vision.company_name}")
        console_print("\n  Departments:")
        for dept_name, dept in sorted(reg.departments.items()):
            console_print(f"    {dept_name}:")
            for r in dept.roles:
                console_print(f"      - {r.title}: {r.description}")
        if reg.board:
            console_print("\n  Board:")
            for b in reg.board:
                console_print(f"    - {b.name or '(unnamed)'} ({b.role or 'no role'})")
        if reg.executives:
            console_print("\n  Executives:")
            for e in reg.executives:
                console_print(
                    f"    - {e.name or '(unnamed)'} ({e.title or 'no title'})"
                )
        if reg.workflows:
            console_print("\n  Workflows:")
            for wf in reg.workflows:
                steps_desc = f" ({len(wf.steps)} steps)" if wf.steps else ""
                console_print(
                    f"    - {wf.name or '(unnamed)'}: {wf.description or ''}{steps_desc}"
                )

    elif report_type == "health":
        validator = ValidatorEngine()
        validation = validator.validate_all()
        console_print(f"\n  {validation.summary()}")
        for rep in validation.reports:
            status = "[green]PASS[/green]" if rep.passed else "[red]FAIL[/red]"
            console_print(f"    {status} {rep.target}")

    else:
        console_print(f"[red]Unknown report type: {report_type}[/red]")
        console_print("[yellow]Available: summary, detailed, health[/yellow]")
        raise typer.Exit(1)

    console_print("\n[green]Report generated.[/green]")
