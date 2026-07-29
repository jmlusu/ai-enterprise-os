from pathlib import Path

import typer
from rich import print

from ai_company.registry.registry import RegistryEngine

app = typer.Typer(help="Query the in-memory company graph")


@app.command()
def show() -> None:
    """Display the company graph structure."""
    engine = RegistryEngine()
    result = engine.load(Path("company"))
    if result.registry is None:
        print("[red]No registry loaded.[/red]")
        raise typer.Exit(1)
    reg = result.registry
    print("[cyan]Company Graph:[/cyan]")
    print(f"  [bold]Vision:[/bold] {reg.vision.name}")
    print(f"  [bold]Departments:[/bold] {len(reg.departments)}")
    for dept_name, dept in sorted(reg.departments.items()):
        for r in dept.roles:
            print(f"    {dept_name} → {r.title}")
    print(f"  [bold]Board:[/bold] {len(reg.board)} member(s)")
    print(f"  [bold]Executives:[/bold] {len(reg.executives)}")
    total_roles = sum(len(d.roles) for d in reg.departments.values())
    edge_count = total_roles + len(reg.unresolved_refs)
    print(f"\n  Edges: {edge_count} connections")


@app.command()
def stats() -> None:
    """Show graph statistics."""
    engine = RegistryEngine()
    result = engine.load(Path("company"))
    if result.registry is None:
        print("[red]No registry loaded.[/red]")
        raise typer.Exit(1)
    reg = result.registry
    total_roles = sum(len(d.roles) for d in reg.departments.values())
    total_nodes = 1 + len(reg.departments) + total_roles
    total_edges = total_roles + len(reg.unresolved_refs)
    density = total_edges / (total_nodes * (total_nodes - 1)) if total_nodes > 1 else 0
    print("[cyan]Graph statistics:[/cyan]")
    print(f"  Total nodes: {total_nodes}")
    print(f"  Total edges: {total_edges}")
    print(f"  Graph density: {density:.4f}")
    if reg.unresolved_refs:
        print(f"  [yellow]Unresolved refs: {len(reg.unresolved_refs)}[/yellow]")
