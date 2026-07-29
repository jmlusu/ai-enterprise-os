import typer
from rich import print

app = typer.Typer(help="Manage AI agent memory and session state")


@app.command()
def show() -> None:
    """Display current memory state."""
    print("[cyan]Current memory state:[/cyan]")
    print("  Sprint: Phase 2 — Build First Business Feature")
    print("  Active tasks: Generate code, test, document")


@app.command()
def clear() -> None:
    """Clear session memory and reset state."""
    print("[yellow]Clearing session memory...[/yellow]")
    print("[green]Memory cleared.[/green]")
