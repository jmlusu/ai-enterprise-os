"""CLI commands for the Company Generator — generate, validate, report, board."""

from pathlib import Path

import typer

from ai_company.cli.utils import load_registry_and_manifest
from ai_company.company.generator import CompanyGenerator
from ai_company.utils.console import console_print

app = typer.Typer(
    help="Company organization commands — generate, validate, report, board"
)


@app.command()
def generate() -> None:
    """Generate the full organization hierarchy and artifacts."""
    console_print("[cyan]Generating organization...[/cyan]")

    try:
        gen = CompanyGenerator()
        result = gen.generate()
    except RuntimeError as e:
        console_print(f"[red]Generation failed:[/red] {e}")
        raise typer.Exit(1) from e

    summary = result.summary()
    console_print("  [green]✓[/green] Organization hierarchy built")
    console_print(f"      Nodes: {summary['nodes']}")
    console_print(f"      Edges: {summary['edges']}")
    console_print(f"      Max depth: {summary['max_depth']} levels")
    console_print(f"      Roles defined: {summary['roles']}")

    if result.warnings:
        console_print(f"\n[yellow]Warnings ({len(result.warnings)}):[/yellow]")
        for w in result.warnings[:10]:  # show first 10
            console_print(f"  [yellow]![/yellow] {w}")
        if len(result.warnings) > 10:
            console_print(f"  [dim]... and {len(result.warnings) - 10} more[/dim]")

    # Show output paths
    output_dir = Path("generated")
    console_print(f"\n[cyan]Artifacts written to:[/cyan] {output_dir.resolve()}")
    for f in [
        "organization.json",
        "organization.yaml",
        "organization_summary.yaml",
        "organization_roles.json",
        "docs/ORGANIZATION.md",
    ]:
        p = output_dir / f
        if p.exists():
            console_print(f"  [green]✓[/green] {f}")


@app.command()
def validate() -> None:
    """Validate that the registry can produce a valid organization."""
    console_print("[cyan]Validating organization structure...[/cyan]")

    gen = CompanyGenerator()
    errors = gen.validate()

    if errors:
        for err in errors:
            console_print(f"  [red]✗[/red] {err}")
        console_print(f"\n[red]Validation failed with {len(errors)} error(s).[/red]")
        raise typer.Exit(1)

    console_print("  [green]✓[/green] Organization structure is valid")


@app.command()
def report() -> None:
    """Show a summary report of the current organization."""
    reg, _manifest = load_registry_and_manifest()

    console_print("[cyan]Organization Report[/cyan]\n")
    console_print(
        f"  Company: [bold]{reg.vision.company_name or reg.vision.name}[/bold]"
    )
    console_print(f"  Vision: {reg.vision.description or 'N/A'}")
    console_print("")
    console_print(
        f"  [bold]Board Members:[/bold] {len(reg.board) + len(reg.board_members)}"
    )
    console_print(f"  [bold]Executives:[/bold] {len(reg.executives)}")
    console_print(f"  [bold]Departments:[/bold] {len(reg.departments)}")
    console_print(f"  [bold]Specialists:[/bold] {len(reg.specialists)}")
    console_print(f"  [bold]Workflows:[/bold] {len(reg.workflows)}")
    console_print(f"  [bold]Policies:[/bold] {len(reg.policies)}")

    total_roles = sum(len(d.roles) for d in reg.departments.values())
    console_print(f"  [bold]Department Roles:[/bold] {total_roles}")

    console_print("\n[bold]Departments:[/bold]")
    for dept_name in sorted(reg.departments):
        console_print(f"    - {dept_name}")

    console_print("\n[bold]Executives:[/bold]")
    for ex in reg.executives:
        if ex.name:
            console_print(f"    - {ex.name} ({ex.title or 'N/A'})")


@app.command()
def board_generate() -> None:
    """Generate board governance artifacts."""
    console_print("[cyan]Generating board artifacts...[/cyan]")

    try:
        gen = CompanyGenerator()
        result = gen.generate_board()
    except RuntimeError as e:
        console_print(f"[red]Board generation failed:[/red] {e}")
        raise typer.Exit(1) from e

    summary = result.summary()
    console_print("  [green]✓[/green] Board artifacts generated")
    console_print(f"      Members: {summary['members']}")
    console_print(f"      Committees: {summary['committees']}")
    console_print(f"      Charters: {summary['charters']}")
    console_print(f"      Scheduled meetings: {summary['meetings']}")

    if result.warnings:
        console_print(f"\n[yellow]Warnings ({len(result.warnings)}):[/yellow]")
        for w in result.warnings:
            console_print(f"  [yellow]![/yellow] {w}")

    output_dir = Path("generated")
    console_print(f"\n[cyan]Artifacts written to:[/cyan] {output_dir.resolve()}")
    for f in [
        "board.json",
        "board.yaml",
        "docs/BOARD.md",
        "docs/BOARD_GOVERNANCE.md",
        "docs/BOARD_CHARTER.md",
    ]:
        p = output_dir / f
        if p.exists():
            console_print(f"  [green]✓[/green] {f}")


@app.command()
def board_validate() -> None:
    """Validate that the registry can produce board artifacts."""
    console_print("[cyan]Validating board data...[/cyan]")

    gen = CompanyGenerator()
    errors = gen.validate_board()

    if errors:
        for err in errors:
            console_print(f"  [red]✗[/red] {err}")
        console_print(
            f"\n[red]Board validation failed with {len(errors)} error(s).[/red]"
        )
        raise typer.Exit(1)

    console_print("  [green]✓[/green] Board data is valid")


@app.command()
def board_report() -> None:
    """Show a summary report of the board."""
    reg, _manifest = load_registry_and_manifest()

    console_print("[cyan]Board Report[/cyan]\n")
    board_members = reg.board_members or reg.board
    console_print(f"  [bold]Board Members:[/bold] {len(board_members)}")
    for m in board_members:
        role = m.role if hasattr(m, "role") and m.role else "Director"
        name = m.name if hasattr(m, "name") and m.name else "Unnamed"
        console_print(f"    - {name} ({role})")

    console_print(f"\n  [bold]Committees:[/bold] {len(reg.committees)}")
    for cm in reg.committees:
        console_print(
            f"    - {cm.name} (chair: {cm.chair or 'TBD'}, {len(cm.members)} members)"
        )

    console_print(f"\n  [bold]Meetings:[/bold] {len(reg.meetings)}")
    for mtg in reg.meetings:
        console_print(f"    - {mtg.title} ({mtg.meeting_date or 'TBD'})")

    console_print(f"\n  [bold]Voting Records:[/bold] {len(reg.voting_records)}")


@app.command()
def exec_generate() -> None:
    """Generate executive artifact packages."""
    console_print("[cyan]Generating executive artifacts...[/cyan]")

    try:
        gen = CompanyGenerator()
        result = gen.generate_executives()
    except RuntimeError as e:
        console_print(f"[red]Executive generation failed:[/red] {e}")
        raise typer.Exit(1) from e

    summary = result.summary()
    console_print("  [green]✓[/green] Executive artifacts generated")
    console_print(f"      Executives: {summary['executives']}")

    if result.warnings:
        console_print(f"\n[yellow]Warnings ({len(result.warnings)}):[/yellow]")
        for w in result.warnings:
            console_print(f"  [yellow]![/yellow] {w}")

    output_dir = Path("generated")
    console_print(f"\n[cyan]Artifacts written to:[/cyan] {output_dir.resolve()}")
    for p in sorted(output_dir.glob("executives/*/executive.yaml")):
        console_print(f"  [green]✓[/green] {p.relative_to(output_dir)}")


@app.command()
def exec_validate() -> None:
    """Validate that the registry can produce executive artifacts."""
    console_print("[cyan]Validating executive data...[/cyan]")

    gen = CompanyGenerator()
    errors = gen.validate_executives()

    if errors:
        for err in errors:
            console_print(f"  [red]✗[/red] {err}")
        console_print(
            f"\n[red]Executive validation failed with {len(errors)} error(s).[/red]"
        )
        raise typer.Exit(1)

    console_print("  [green]✓[/green] Executive data is valid")


@app.command()
def dept_generate() -> None:
    """Generate department artifacts."""
    console_print("[cyan]Generating department artifacts...[/cyan]")

    gen = CompanyGenerator()
    result = gen.generate_departments()

    summary = result.summary()
    console_print(f"  [green]✓[/green] Departments: {summary['departments']}")
    for w in result.warnings:
        console_print(f"  [yellow]![/yellow] {w}")

    output_dir = Path("generated")
    console_print(f"\n[cyan]Artifacts written to:[/cyan] {output_dir.resolve()}")
    for p in sorted(output_dir.glob("departments/*/README.md")):
        console_print(f"  [green]✓[/green] {p.relative_to(output_dir)}")


@app.command()
def dept_validate() -> None:
    """Validate department data."""
    console_print("[cyan]Validating department data...[/cyan]")
    gen = CompanyGenerator()
    errors = gen.validate_departments()
    if errors:
        for err in errors:
            console_print(f"  [red]✗[/red] {err}")
        raise typer.Exit(1)
    console_print("  [green]✓[/green] Department data is valid")


@app.command()
def specialist_generate() -> None:
    """Generate specialist agent artifacts."""
    console_print("[cyan]Generating specialist artifacts...[/cyan]")

    gen = CompanyGenerator()
    result = gen.generate_specialists()

    summary = result.summary()
    console_print(f"  [green]✓[/green] Specialists: {summary['specialists']}")
    for w in result.warnings:
        console_print(f"  [yellow]![/yellow] {w}")

    output_dir = Path("generated")
    console_print(f"\n[cyan]Artifacts written to:[/cyan] {output_dir.resolve()}")
    for p in sorted(output_dir.glob("specialists/*/profile.md")):
        console_print(f"  [green]✓[/green] {p.relative_to(output_dir)}")


@app.command()
def specialist_validate() -> None:
    """Validate specialist data."""
    console_print("[cyan]Validating specialist data...[/cyan]")
    gen = CompanyGenerator()
    errors = gen.validate_specialists()
    if errors:
        for err in errors:
            console_print(f"  [red]✗[/red] {err}")
        raise typer.Exit(1)
    console_print("  [green]✓[/green] Specialist data is valid")


@app.command()
def workflow_generate() -> None:
    """Generate workflow artifacts."""
    console_print("[cyan]Generating workflow artifacts...[/cyan]")

    gen = CompanyGenerator()
    result = gen.generate_workflows()

    console_print(f"  [green]✓[/green] Workflows: {result['workflows']}")
    for w in result.get("warnings", []):
        console_print(f"  [yellow]![/yellow] {w}")


@app.command()
def workflow_validate() -> None:
    """Validate workflow data."""
    console_print("[cyan]Validating workflow data...[/cyan]")
    gen = CompanyGenerator()
    errors = gen.validate_workflows()
    if errors:
        for err in errors:
            console_print(f"  [red]✗[/red] {err}")
        raise typer.Exit(1)
    console_print("  [green]✓[/green] Workflow data is valid")


@app.command()
def prompt_generate() -> None:
    """Generate prompt library artifacts."""
    console_print("[cyan]Generating prompt library...[/cyan]")

    gen = CompanyGenerator()
    result = gen.generate_prompts()

    console_print(f"  [green]✓[/green] Prompts: {result['prompts']}")
    for w in result.get("warnings", []):
        console_print(f"  [yellow]![/yellow] {w}")


@app.command()
def prompt_validate() -> None:
    """Validate prompt data."""
    console_print("[cyan]Validating prompt data...[/cyan]")
    gen = CompanyGenerator()
    errors = gen.validate_prompts()
    if errors:
        for err in errors:
            console_print(f"  [red]✗[/red] {err}")
        raise typer.Exit(1)
    console_print("  [green]✓[/green] Prompt data is valid")


@app.command()
def docs_generate() -> None:
    """Generate documentation artifacts."""
    console_print("[cyan]Generating documentation...[/cyan]")

    gen = CompanyGenerator()
    result = gen.generate_docs()

    console_print(f"  [green]✓[/green] Docs: {result['docs']}")
    for w in result.get("warnings", []):
        console_print(f"  [yellow]![/yellow] {w}")


@app.command()
def docs_validate() -> None:
    """Validate documentation data."""
    console_print("[cyan]Validating documentation data...[/cyan]")
    gen = CompanyGenerator()
    errors = gen.validate_docs()
    if errors:
        for err in errors:
            console_print(f"  [red]✗[/red] {err}")
        raise typer.Exit(1)
    console_print("  [green]✓[/green] Documentation data is valid")
