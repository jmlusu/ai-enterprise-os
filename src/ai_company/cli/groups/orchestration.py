"""Orchestration Engine CLI group: plan, start, and inspect pipelines.

Provides the ``ai-company orchestrate`` command tree:

- ``orchestrate plan``      — create an orchestration plan (dry planning).
- ``orchestrate start``     — start a plan (immediate plans run synchronously).
- ``orchestrate status``    — engine health + a plan's execution state.
- ``orchestrate resume``    — resume a failed/interrupted plan from a checkpoint.
- ``orchestrate retry``     — retry a failed plan from scratch.
- ``orchestrate rollback``  — execute registered undo handlers for a plan.
- ``orchestrate history``   — show execution history for a plan (or all).
"""

from __future__ import annotations

from typing import Any

import typer

from ai_company.orchestration import OrchestrationEngine
from ai_company.orchestration.models import PipelineStatus, TaskStatus
from ai_company.utils.console import console_print

app = typer.Typer(help="Enterprise Orchestration Engine (COO pipelines)")


def _build_engine() -> OrchestrationEngine:
    """Construct a fully wired orchestration engine."""
    try:
        return OrchestrationEngine()
    except Exception as exc:
        console_print(f"[red]Failed to construct orchestration engine:[/red] {exc}")
        raise typer.Exit(1) from exc


def _require_plan_id(plan_id: str | None) -> str:
    if not plan_id:
        console_print(
            "[red]A plan id is required (see 'ai-company orchestrate history').[/red]"
        )
        raise typer.Exit(1)
    return plan_id


@app.command("plan")
def plan(
    pipeline: str = typer.Argument(
        default="bootstrap",
        help="Pipeline catalog name (bootstrap | generation | report)",
    ),
    file: str = typer.Option(
        None, "--file", "-f", help="Path to a plan/pipeline YAML file"
    ),
    schedule_mode: str = typer.Option(
        "immediate",
        "--schedule-mode",
        help="immediate | scheduled | recurring | dependency",
    ),
    interval: float = typer.Option(
        None, "--interval", help="Recurring interval in seconds"
    ),
    max_runs: int = typer.Option(
        0, "--max-runs", help="Max runs for recurring plans (0 = unlimited)"
    ),
) -> None:
    """Create an orchestration plan without executing it."""
    console_print("[cyan]Planning pipeline...[/cyan]")
    engine = _build_engine()
    try:
        plan_obj = engine.plan(
            name=pipeline if not file else None,
            yaml_path=file,
            schedule_mode=schedule_mode,
            interval_seconds=interval,
            max_runs=max_runs,
        )
    except Exception as exc:
        console_print(f"[red]Planning failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        engine.close()
    console_print(f"  [green]✓[/green] Plan id: [bold]{plan_obj.id}[/bold]")
    console_print(f"  [green]✓[/green] Pipeline: {plan_obj.pipeline.name}")
    console_print(f"  [green]✓[/green] Schedule: {plan_obj.schedule_mode.value}")
    console_print(f"  [green]✓[/green] Tasks: {len(plan_obj.pipeline.all_tasks())}")


@app.command("start")
def start(
    pipeline: str = typer.Argument(
        default="bootstrap",
        help="Pipeline catalog name (bootstrap | generation | report)",
    ),
    file: str = typer.Option(
        None, "--file", "-f", help="Path to a plan/pipeline YAML file"
    ),
    schedule_mode: str = typer.Option(
        "immediate",
        "--schedule-mode",
        help="immediate | scheduled | recurring | dependency",
    ),
    interval: float = typer.Option(
        None, "--interval", help="Recurring interval in seconds"
    ),
    max_runs: int = typer.Option(
        0, "--max-runs", help="Max runs for recurring plans (0 = unlimited)"
    ),
) -> None:
    """Start an orchestration plan.

    Immediate plans run synchronously; scheduled, recurring, and
    dependency plans are registered with the in-process scheduler.
    """
    engine = _build_engine()
    try:
        plan_obj = engine.plan(
            name=pipeline if not file else None,
            yaml_path=file,
            schedule_mode=schedule_mode,
            interval_seconds=interval,
            max_runs=max_runs,
        )
        console_print(
            f"  [green]✓[/green] Plan [bold]{plan_obj.id}[/bold] "
            f"({plan_obj.pipeline.name}, mode={plan_obj.schedule_mode.value})"
        )
        result = engine.start(plan_obj)
        if hasattr(result, "state"):  # ExecutionRecord
            state = result.state
            console_print(f"  [green]✓[/green] Status: {state.status.value}")
            metrics = result.metrics
            console_print(
                f"  [green]✓[/green] Tasks: {metrics.tasks_total} | "
                f"completed: {metrics.tasks_completed} | "
                f"failed: {metrics.tasks_failed} | "
                f"skipped: {metrics.tasks_skipped}"
            )
            if state.error:
                console_print(f"  [red]✗[/red] Error: {state.error}")
                raise typer.Exit(1)
        else:
            console_print(
                "  [yellow]![/yellow] Plan registered with scheduler "
                "(not immediate). Use 'status' to inspect."
            )
    except typer.Exit:
        raise
    except Exception as exc:
        console_print(f"[red]Start failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        engine.close()


@app.command("status")
def status(
    plan_id: str = typer.Argument(
        None, help="Plan id to inspect (optional; engine status only)"
    ),
) -> None:
    """Show engine status and (optionally) a plan's execution state."""
    engine = _build_engine()
    try:
        engine_status = engine.engine_status()
        console_print("[cyan]Orchestration Engine:[/cyan]")
        console_print(f"  Name: {engine_status.name} (v{engine_status.version})")
        console_print(f"  Running: {engine_status.running}")
        console_print(f"  Active plans: {engine_status.active_plans}")
        console_print(f"  Started at: {engine_status.started_at or 'not started'}")

        unhealthy = [h for h in engine_status.health if not h.healthy]
        console_print(f"  Health: {len(engine_status.health)} probe(s)")
        for h in unhealthy:
            console_print(f"    [red]✗[/red] {h.engine}: {h.message}")
        if not unhealthy:
            console_print("    [green]✓[/green] all engines operational")

        if plan_id:
            plan_id = _require_plan_id(plan_id)
            state = engine.state_store.get_state(plan_id)
            if state is None:
                console_print(
                    f"[yellow]Plan {plan_id} has no recorded execution state.[/yellow]"
                )
            else:
                console_print(f"\n[cyan]Plan {plan_id}:[/cyan]")
                console_print(f"  Status: {state.status.value}")
                console_print(f"  Current task: {state.current_task_id or '-'}")
                console_print(f"  Started: {state.started_at}")
                console_print(f"  Completed: {state.completed_at or '-'}")
                if state.error:
                    console_print(f"  [red]Error:[/red] {state.error}")
                if state.recovered_from:
                    console_print(
                        f"  Recovered from checkpoint: {state.recovered_from}"
                    )
                failed = [
                    tid
                    for tid, st in state.task_statuses.items()
                    if st == TaskStatus.FAILED
                ]
                if failed:
                    console_print(f"  Failed tasks: {', '.join(failed)}")
    except typer.Exit:
        raise
    except Exception as exc:
        console_print(f"[red]Status failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        engine.close()


@app.command("resume")
def resume(
    plan_id: str = typer.Argument(..., help="Plan id to resume"),
    checkpoint_id: str = typer.Option(
        None, "--checkpoint-id", help="Specific checkpoint to restore from"
    ),
) -> None:
    """Resume a failed or interrupted plan from its latest checkpoint."""
    engine = _build_engine()
    try:
        plan_id = _require_plan_id(plan_id)
        record = engine.resume(plan_id, checkpoint_id=checkpoint_id)
        console_print(
            f"  [green]✓[/green] Plan {plan_id} resumed -> {record.state.status.value}"
        )
        console_print(
            f"  [green]✓[/green] Tasks: {record.metrics.tasks_completed}/"
            f"{record.metrics.tasks_total} completed"
        )
        if record.state.error:
            console_print(f"  [red]✗[/red] Error: {record.state.error}")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        console_print(f"[red]Resume failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        engine.close()


@app.command("retry")
def retry(
    plan_id: str = typer.Argument(..., help="Plan id to retry"),
) -> None:
    """Retry a failed plan from scratch (fresh run, same plan id)."""
    engine = _build_engine()
    try:
        plan_id = _require_plan_id(plan_id)
        record = engine.retry(plan_id)
        console_print(
            f"  [green]✓[/green] Plan {plan_id} retried -> {record.state.status.value}"
        )
        console_print(
            f"  [green]✓[/green] Tasks: {record.metrics.tasks_completed}/"
            f"{record.metrics.tasks_total} completed"
        )
        if record.state.error:
            console_print(f"  [red]✗[/red] Error: {record.state.error}")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        console_print(f"[red]Retry failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        engine.close()


@app.command("rollback")
def rollback(
    plan_id: str = typer.Argument(..., help="Plan id to roll back"),
    reason: str = typer.Option(
        "manual rollback", "--reason", help="Reason recorded in the audit trail"
    ),
) -> None:
    """Execute registered undo handlers for a plan (reverse order)."""
    engine = _build_engine()
    try:
        plan_id = _require_plan_id(plan_id)
        rollback_plan = engine.rollback(plan_id, reason=reason)
        console_print(f"  [green]✓[/green] Rollback status: {rollback_plan.status}")
        for step in rollback_plan.steps:
            icon = "[green]✓[/green]" if step.success else "[red]✗[/red]"
            console_print(f"  {icon} {step.task_id}: {step.action}")
    except Exception as exc:
        console_print(f"[red]Rollback failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        engine.close()


@app.command("history")
def history(
    plan_id: str = typer.Argument(
        None, help="Plan id filter (optional; lists all plans)"
    ),
    limit: int = typer.Option(20, "--limit", help="Maximum number of records to show"),
) -> None:
    """Show execution history for a plan (or the most recent runs)."""
    engine = _build_engine()
    try:
        records = engine.history(plan_id)
        records = records[:limit]
        if not records:
            console_print("[yellow]No execution history found.[/yellow]")
            return
        console_print("[cyan]Execution history:[/cyan]")
        for record in records:
            state = record.state
            icon = (
                "[green]✓[/green]"
                if state.status == PipelineStatus.COMPLETED
                else "[red]✗[/red]"
                if state.status == PipelineStatus.FAILED
                else "[yellow]•[/yellow]"
            )
            console_print(
                f"  {icon} {record.plan_id} | {state.status.value} | "
                f"{record.recorded_at.isoformat()} | "
                f"tasks {record.metrics.tasks_completed}/"
                f"{record.metrics.tasks_total}"
            )
    except Exception as exc:
        console_print(f"[red]History failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        engine.close()


# Re-export helper for programmatic use.
def build_engine() -> OrchestrationEngine:
    """Return a wired OrchestrationEngine (programmatic access)."""
    return _build_engine()


__all__: list[Any] = ["app", "build_engine"]
