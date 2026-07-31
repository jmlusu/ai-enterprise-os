"""CLI group for memory engine commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from ai_company.memory.engine import MemoryEngine
from ai_company.utils.console import console_print

app = typer.Typer(help="Persistent memory engine operations")

# Default storage path
DEFAULT_STORAGE = Path("memory/store.jsonl")


def _get_engine() -> MemoryEngine:
    """Get memory engine instance."""
    config_path = Path("config/memory/memory.yaml")
    if config_path.exists():
        return MemoryEngine.from_config(str(config_path))
    return MemoryEngine(storage_path=str(DEFAULT_STORAGE))


@app.command()
def save(
    content: str = typer.Argument(..., help="JSON content to save"),
    type: str = typer.Option("system", "--type", "-t", help="Memory type"),
    namespace: str = typer.Option(
        "global", "--namespace", "-n", help="Memory namespace"
    ),
    tags: str = typer.Option("", "--tags", help="Comma-separated tags"),
    source: str = typer.Option("cli", "--source", "-s", help="Memory source"),
    importance: float = typer.Option(0.5, "--importance", "-i", min=0.0, max=1.0),
    parent: str = typer.Option("", "--parent", "-p", help="Parent memory ID"),
) -> None:
    """Save a new memory entry."""
    try:
        content_dict = json.loads(content)
    except json.JSONDecodeError:
        content_dict = {"text": content}

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    engine = _get_engine()
    entry = engine.save(
        content=content_dict,
        memory_type=type,
        namespace=namespace,
        tags=tag_list,
        source=source,
        importance=importance,
        parent_id=parent if parent else None,
    )

    console_print(f"[green]✓[/green] Memory saved: [cyan]{entry.id}[/cyan]")
    console_print(f"  Type: {entry.memory_type.value}")
    console_print(f"  Namespace: {entry.namespace.value}")
    console_print(f"  Summary: {entry.summary[:100]}")


@app.command()
def get(
    memory_id: str = typer.Argument(..., help="Memory ID to retrieve"),
) -> None:
    """Retrieve a memory entry by ID."""
    engine = _get_engine()
    entry = engine.retrieve(memory_id)

    if not entry:
        console_print(f"[red]✗[/red] Memory not found: {memory_id}")
        raise typer.Exit(1)

    console_print(f"[cyan]Memory:[/cyan] {entry.id}")
    console_print(f"  Type: {entry.memory_type.value}")
    console_print(f"  Namespace: {entry.namespace.value}")
    console_print(f"  Importance: {entry.importance:.2f}")
    console_print(f"  Version: {entry.version}")
    console_print(f"  Created: {entry.created_at.isoformat()}")
    console_print(f"  Archived: {entry.archived}")
    if entry.parent_id:
        console_print(f"  Parent: {entry.parent_id}")
    console_print(f"  Summary: {entry.summary}")
    if entry.tags:
        console_print(f"  Tags: {', '.join(entry.tags)}")
    console_print(f"  Content: {json.dumps(entry.content, indent=2)[:500]}")


@app.command()
def update(
    memory_id: str = typer.Argument(..., help="Memory ID to update"),
    content: str = typer.Option("", "--content", "-c", help="JSON content"),
    tags: str = typer.Option("", "--tags", "-t", help="Comma-separated tags"),
    importance: float = typer.Option(None, "--importance", "-i", min=0.0, max=1.0),
) -> None:
    """Update a memory entry."""
    engine = _get_engine()

    content_dict = None
    if content:
        try:
            content_dict = json.loads(content)
        except json.JSONDecodeError:
            content_dict = {"text": content}

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    entry = engine.update(
        memory_id=memory_id,
        content=content_dict,
        tags=tag_list if tag_list else None,
        importance=importance,
    )

    if not entry:
        console_print(f"[red]✗[/red] Memory not found: {memory_id}")
        raise typer.Exit(1)

    console_print(
        f"[green]✓[/green] Memory updated: [cyan]{memory_id}[/cyan] (v{entry.version})"
    )


@app.command()
def delete(
    memory_id: str = typer.Argument(..., help="Memory ID to delete"),
) -> None:
    """Delete a memory entry."""
    engine = _get_engine()
    if engine.delete(memory_id):
        console_print(f"[green]✓[/green] Memory deleted: [cyan]{memory_id}[/cyan]")
    else:
        console_print(f"[red]✗[/red] Memory not found: {memory_id}")
        raise typer.Exit(1)


@app.command()
def search(
    query: str = typer.Argument("", help="Search query text"),
    type: str = typer.Option(None, "--type", "-t", help="Filter by memory type"),
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Filter by namespace"
    ),
    tags: str = typer.Option("", "--tags", help="Comma-separated tags"),
    limit: int = typer.Option(20, "--limit", "-l", min=1, max=1000),
    min_importance: float = typer.Option(
        0.0, "--min-importance", "-i", min=0.0, max=1.0
    ),
    include_archived: bool = typer.Option(
        False, "--include-archived", help="Include archived entries"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Search memory entries."""
    engine = _get_engine()

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    results = engine.search(
        query=query,
        memory_type=type,
        namespace=namespace,
        tags=tag_list,
        limit=limit,
        min_importance=min_importance,
        include_archived=include_archived,
    )

    if json_output:
        console_print(
            json.dumps(
                {
                    "count": len(results),
                    "results": [e.to_dict() for e in results],
                },
                indent=2,
            )
        )
        return

    if not results:
        console_print("[yellow]No results found.[/yellow]")
        return

    console_print(f"[cyan]Results ({len(results)}):[/cyan]")
    for i, entry in enumerate(results, 1):
        console_print(
            f"  {i}. [cyan]{entry.id}[/cyan] "
            f"({entry.memory_type.value}/{entry.namespace.value}) "
            f"[dim]{entry.summary[:120]}[/dim]"
        )


@app.command()
def list(
    type: str = typer.Option(None, "--type", "-t", help="Filter by memory type"),
    namespace: str = typer.Option(
        None, "--namespace", "-n", help="Filter by namespace"
    ),
    limit: int = typer.Option(20, "--limit", "-l", min=1, max=1000),
) -> None:
    """List memory entries."""
    engine = _get_engine()

    if type and namespace:
        results = engine.search(namespace=namespace, memory_type=type, limit=limit)
    elif type:
        results = engine.retrieve_by_type(type)
    elif namespace:
        results = engine.retrieve_by_namespace(namespace)
    else:
        results = engine.retrieve_all()
        results.sort(key=lambda e: e.created_at, reverse=True)
        results = results[:limit]

    if not results:
        console_print("[yellow]No entries found.[/yellow]")
        return

    console_print(f"[cyan]Entries ({len(results)}):[/cyan]")
    for entry in results:
        status = "[dim](archived)[/dim]" if entry.archived else ""
        console_print(
            f"  {entry.id} "
            f"[green]{entry.memory_type.value:12s}[/green] "
            f"[blue]{entry.namespace.value:10s}[/blue] "
            f"[dim]{entry.summary[:80]}[/dim] "
            f"{status}"
        )


@app.command()
def archive(
    memory_id: str = typer.Argument(..., help="Memory ID to archive"),
) -> None:
    """Archive a memory entry."""
    engine = _get_engine()
    if engine.archive(memory_id):
        console_print(f"[green]✓[/green] Memory archived: [cyan]{memory_id}[/cyan]")
    else:
        console_print(f"[red]✗[/red] Memory not found: {memory_id}")
        raise typer.Exit(1)


@app.command()
def unarchive(
    memory_id: str = typer.Argument(..., help="Memory ID to unarchive"),
) -> None:
    """Unarchive a memory entry."""
    engine = _get_engine()
    if engine.unarchive(memory_id):
        console_print(f"[green]✓[/green] Memory unarchived: [cyan]{memory_id}[/cyan]")
    else:
        console_print(f"[red]✗[/red] Memory not found: {memory_id}")
        raise typer.Exit(1)


@app.command()
def archive_old(
    days: int = typer.Argument(30, help="Archive entries older than N days"),
) -> None:
    """Archive memories older than specified days."""
    engine = _get_engine()
    count = engine.archive_older_than(days)
    console_print(f"[green]✓[/green] Archived {count} memories older than {days} days")


@app.command()
def purge() -> None:
    """Permanently delete all archived memories."""
    engine = _get_engine()
    count = engine.purge_archived()
    console_print(f"[green]✓[/green] Purged {count} archived memories")


@app.command()
def snapshot(
    name: str = typer.Argument(..., help="Snapshot name"),
) -> None:
    """Create a snapshot of current memory state."""
    engine = _get_engine()
    snap_id = engine.snapshot(name)
    console_print(f"[green]✓[/green] Snapshot created: [cyan]{snap_id}[/cyan]")


@app.command()
def snapshots() -> None:
    """List available snapshots."""
    engine = _get_engine()
    snaps = engine.list_snapshots()
    if not snaps:
        console_print("[yellow]No snapshots found.[/yellow]")
        return
    console_print(f"[cyan]Snapshots ({len(snaps)}):[/cyan]")
    for snap in snaps:
        console_print(
            f"  {snap['id']} - {snap['name']} "
            f"({snap.get('entry_count', '?')} entries) "
            f"[dim]{snap.get('created_at', '')}[/dim]"
        )


@app.command()
def restore(
    snapshot_id: str = typer.Argument(..., help="Snapshot ID to restore"),
) -> None:
    """Restore memory state from a snapshot."""
    engine = _get_engine()
    count = engine.restore_snapshot(snapshot_id)
    console_print(f"[green]✓[/green] Restored {count} memories from snapshot")


@app.command()
def show() -> None:
    """Display current memory state (summary view)."""
    engine = _get_engine()
    stats_data = engine.get_statistics()

    console_print("[cyan]Memory State:[/cyan]")
    console_print(f"  Total entries: {stats_data['total_memories']}")
    console_print(f"  Archived: {stats_data['total_archived']}")
    console_print(f"  Snapshots: {stats_data['total_snapshots']}")
    console_print(f"  Knowledge entries: {stats_data.get('knowledge_count', 0)}")
    console_print(f"  Average importance: {stats_data['average_importance']:.3f}")

    console_print("\n  [dim]Use 'memory stats' for detailed view[/dim]")


@app.command()
def stats() -> None:
    """Show memory engine statistics."""
    engine = _get_engine()
    stats_data = engine.get_statistics()

    console_print("[cyan]Memory Engine Statistics:[/cyan]")
    console_print(f"  Total entries: {stats_data['total_memories']}")
    console_print(f"  Archived: {stats_data['total_archived']}")
    console_print(f"  Snapshots: {stats_data['total_snapshots']}")
    console_print(f"  Knowledge entries: {stats_data.get('knowledge_count', 0)}")

    console_print("\n[cyan]By Type:[/cyan]")
    for mtype, count in sorted(stats_data["by_type"].items()):
        console_print(f"  {mtype:15s}: {count}")

    if stats_data.get("by_namespace"):
        console_print("\n[cyan]By Namespace:[/cyan]")
        for ns, count in sorted(stats_data["by_namespace"].items()):
            console_print(f"  {ns:15s}: {count}")

    console_print(f"\n  Avg importance: {stats_data['average_importance']:.3f}")
    console_print(f"  Embeddings: {stats_data.get('embedding_count', 0)}")
    console_print(f"  Total size: {stats_data.get('total_size_bytes', 0):,} bytes")


@app.command()
def clear() -> None:
    """Clear ALL memories (irreversible)."""
    confirm = typer.confirm("[red]Are you sure you want to clear ALL memories?[/red]")
    if not confirm:
        console_print("[yellow]Cancelled.[/yellow]")
        raise typer.Exit(0)
    engine = _get_engine()
    engine.clear()
    console_print("[green]All memories cleared.[/green]")


@app.command()
def export(
    file_path: str = typer.Argument("memory/export.json", help="Output file path"),
) -> None:
    """Export all memories to JSON file."""
    engine = _get_engine()
    path = engine.export_to_json(file_path)
    console_print(f"[green]✓[/green] Memories exported to: [cyan]{path}[/cyan]")


@app.command()
def apply_retention() -> None:
    """Apply retention policy to archive/purge old entries."""
    engine = _get_engine()
    result = engine.apply_retention_policy()
    console_print(
        f"[green]✓[/green] Retention applied: "
        f"{result['archived']} archived, {result['purged']} purged"
    )
