from pathlib import Path

import typer
from rich import print

from ai_company.registry.registry import RegistryEngine

app = typer.Typer(help="Manage the company registry (YAML data)")


@app.command()
def list() -> None:
    """List all entries in the company registry."""
    print("[cyan]Registry list:[/cyan]")
    engine = RegistryEngine()
    result = engine.load(Path("company"))
    if result.errors:
        for err in result.errors:
            print(f"  [red]✗[/red] {err}")
        raise typer.Exit(1)
    reg = result.registry
    if reg is None:
        print("[red]No registry loaded.[/red]")
        raise typer.Exit(1)
    print(f"  [green]✓[/green] Vision: {reg.vision.name}")
    print(f"  [green]✓[/green] Departments: {len(reg.departments)}")
    for dept_name in sorted(reg.departments):
        roles = reg.departments[dept_name].roles
        print(f"      {dept_name} ({len(roles)} roles)")
    print(f"  [green]✓[/green] Board members: {len(reg.board)}")
    print(f"  [green]✓[/green] Executives: {len(reg.executives)}")
    print(f"  [green]✓[/green] Policies: {len(reg.policies)}")
    print(f"  [green]✓[/green] Specialists: {len(reg.specialists)}")
    print(f"  [green]✓[/green] Workflows: {len(reg.workflows)}")


@app.command()
def show(
    name: str = typer.Argument(
        default="company", help="Registry entry name to show"
    ),
) -> None:
    """Show details of a specific registry entry."""
    print(f"[cyan]Registry entry:[/cyan] {name}")
    engine = RegistryEngine()
    result = engine.load(Path("company"))
    if not result.success:
        for err in result.errors:
            print(f"  [red]✗[/red] {err}")
        raise typer.Exit(1)
    reg = result.registry
    if reg is None:
        print("[red]No registry loaded.[/red]")
        raise typer.Exit(1)
    if name == "vision":
        v = reg.vision
        print(f"  Name: {v.name}")
        print(f"  Description: {v.description or ''}")
        print(f"  Company: {v.company_name or ''}")
    elif name == "departments" or name in reg.departments:
        if name == "departments":
            for d_name, dept in sorted(reg.departments.items()):
                print(f"  [bold]{d_name}[/bold] ({len(dept.roles)} roles)")
                for r in dept.roles:
                    print(f"    - {r.title}: {r.description}")
        else:
            found_dept = reg.departments.get(name)
            if found_dept is not None:
                print(f"  Name: {found_dept.name}")
                print(f"  Roles: {len(found_dept.roles)}")
                for r in found_dept.roles:
                    print(f"    - {r.title}: {r.description}")
            else:
                print(f"  [yellow]Department '{name}' not found.[/yellow]")
    elif name == "board":
        for b in reg.board:
            print(f"  - {b.name or '(unnamed)'} ({b.role or 'no role'})")
    elif name == "executives":
        for e in reg.executives:
            print(f"  - {e.name or '(unnamed)'} ({e.title or 'no title'})")
    elif name == "policies":
        for p in reg.policies:
            print(f"  - {p.name or '(unnamed)'}: {p.description or ''}")
    elif name == "specialists":
        for s in reg.specialists:
            print(f"  - {s.name or '(unnamed)'}: {s.expertise or ''}")
    elif name == "workflows":
        for w in reg.workflows:
            print(f"  - {w.name or '(unnamed)'}: {w.description or ''} ({len(w.steps)} steps)")
    else:
        print(f"  [yellow]Unknown entry: {name}. Try: vision, departments, board, executives, policies, specialists, workflows[/yellow]")


@app.command()
def verify() -> None:
    """Verify the integrity of all registry files."""
    print("[cyan]Verifying registry...[/cyan]")
    engine = RegistryEngine()
    result = engine.load(Path("company"))
    if result.errors:
        for err in result.errors:
            print(f"  [red]✗[/red] {err}")
        raise typer.Exit(1)
    for w in result.warnings:
        print(f"  [yellow]![/yellow] {w}")
    if result.registry is None:
        print("[red]Registry could not be loaded.[/red]")
        raise typer.Exit(1)
    print(f"  [green]✓[/green] Vision: {result.registry.vision.name}")
    print(f"  [green]✓[/green] {len(result.registry.departments)} department(s)")
    print("  [green]✓[/green] Registry is valid and consistent.")
