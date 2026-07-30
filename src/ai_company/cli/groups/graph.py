from pathlib import Path

import typer

from ai_company.registry.registry import RegistryEngine
from ai_company.utils.console import console_print

app = typer.Typer(help="Query the in-memory company graph")


@app.command()
def show() -> None:
    """Display the company graph structure."""
    engine = RegistryEngine()
    result = engine.load(Path("company"))
    if result.registry is None:
        console_print("[red]No registry loaded.[/red]")
        raise typer.Exit(1)
    reg = result.registry
    console_print("[cyan]Company Graph:[/cyan]")
    console_print(f"  [bold]Vision:[/bold] {reg.vision.name}")
    console_print(f"  [bold]Departments:[/bold] {len(reg.departments)}")
    for dept_name, dept in sorted(reg.departments.items()):
        for r in dept.roles:
            console_print(f"    {dept_name} → {r.title}")
    console_print(f"  [bold]Board:[/bold] {len(reg.board)} member(s)")
    console_print(f"  [bold]Executives:[/bold] {len(reg.executives)}")
    total_roles = sum(len(d.roles) for d in reg.departments.values())
    edge_count = total_roles + len(reg.unresolved_refs)
    console_print(f"\n  Edges: {edge_count} connections")


@app.command()
def stats() -> None:
    """Show graph statistics."""
    engine = RegistryEngine()
    result = engine.load(Path("company"))
    if result.registry is None:
        console_print("[red]No registry loaded.[/red]")
        raise typer.Exit(1)
    reg = result.registry
    total_roles = sum(len(d.roles) for d in reg.departments.values())
    total_nodes = 1 + len(reg.departments) + total_roles
    total_edges = total_roles + len(reg.unresolved_refs)
    density = total_edges / (total_nodes * (total_nodes - 1)) if total_nodes > 1 else 0
    console_print("[cyan]Graph statistics:[/cyan]")
    console_print(f"  Total nodes: {total_nodes}")
    console_print(f"  Total edges: {total_edges}")
    console_print(f"  Graph density: {density:.4f}")
    if reg.unresolved_refs:
        console_print(f"  [yellow]Unresolved refs: {len(reg.unresolved_refs)}[/yellow]")


@app.command()
def export() -> None:
    """Export the company graph as JSON."""
    engine = RegistryEngine()
    result = engine.load(Path("company"))
    if result.registry is None:
        console_print("[red]No registry loaded.[/red]")
        raise typer.Exit(1)
    reg = result.registry

    output_dir = Path("generated")
    output_dir.mkdir(parents=True, exist_ok=True)

    import json

    graph_data = {
        "vision": reg.vision.model_dump() if hasattr(reg.vision, "model_dump") else {},
        "departments": {
            name: {
                "name": dept.name,
                "roles": [r.model_dump() for r in dept.roles]
                if hasattr(dept, "roles")
                else [],
            }
            for name, dept in reg.departments.items()
        },
        "executives": [
            {
                "name": ex.name,
                "title": ex.title,
                "department": ex.department,
                "reports_to": ex.reports_to,
            }
            for ex in reg.executives
        ],
        "board": [
            {
                "name": m.name if hasattr(m, "name") else str(m),
            }
            for m in (reg.board_members or reg.board)
        ],
    }

    json_path = output_dir / "graph_export.json"
    json_path.write_text(json.dumps(graph_data, indent=2), encoding="utf-8")
    console_print(f"[green]Graph exported to {json_path}[/green]")
