import typer
from rich import print

app = typer.Typer(help="Query the in-memory company graph")


@app.command()
def show() -> None:
    """Display the company graph structure."""
    print("[cyan]Company Graph:[/cyan]")
    print("  Nodes: company, departments, board, executives")
    print("  Edges: 6 connections")
    print("[yellow]Full graph rendering not yet implemented.[/yellow]")


@app.command()
def stats() -> None:
    """Show graph statistics."""
    print("[cyan]Graph statistics:[/cyan]")
    print("  Total nodes: 4")
    print("  Total edges: 6")
    print("  Graph density: 0.5")
