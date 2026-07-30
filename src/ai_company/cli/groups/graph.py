from pathlib import Path

import typer

from ai_company.company.graph_exporter import GraphExporter
from ai_company.registry.registry import RegistryEngine
from ai_company.utils.console import console_print

app = typer.Typer(help="Query and export the company graph")


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
    """Export the company graph as Mermaid diagram and enriched JSON."""
    engine = RegistryEngine()
    registry_result = engine.load(Path("company"))
    if registry_result.registry is None:
        console_print("[red]No registry loaded.[/red]")
        raise typer.Exit(1)
    reg = registry_result.registry

    exporter = GraphExporter(reg)
    errors = exporter.validate()
    if errors:
        for err in errors:
            console_print(f"  [red]✗[/red] {err}")
        raise typer.Exit(1)

    result = exporter.generate()
    output_dir = Path("generated")
    created = exporter.write_artifacts(result, output_dir)

    console_print(f"[green]Generated {len(created)} graph artifact(s):[/green]")
    for p in created:
        console_print(f"  [green]✓[/green] {p.relative_to(output_dir)}")
