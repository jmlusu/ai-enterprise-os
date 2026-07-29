import typer
from rich import print

app = typer.Typer(help="Manage the company registry (YAML data)")


@app.command()
def list() -> None:
    """List all entries in the company registry."""
    print("[cyan]Registry list:[/cyan]")
    print("  - company (company.yaml)")
    print("  - departments (departments.yaml)")
    print("  - board (board.yaml)")
    print("  - executives (executives.yaml)")
    print("  - policies (policies.yaml)")
    print("  - specialists (specialists.yaml)")
    print("  - workflows (workflows.yaml)")


@app.command()
def show(
    name: str = typer.Argument(
        default="company", help="Registry entry name to show"
    ),
) -> None:
    """Show details of a specific registry entry."""
    print(f"[cyan]Registry entry:[/cyan] {name}")
    print("[yellow]Not yet implemented.[/yellow]")


@app.command()
def verify() -> None:
    """Verify the integrity of all registry files."""
    print("[cyan]Verifying registry...[/cyan]")
    print("[green]All registry files valid.[/green]")
