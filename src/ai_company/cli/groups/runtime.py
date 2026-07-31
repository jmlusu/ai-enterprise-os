"""Runtime Engine CLI group: boot, supervise, and inspect the enterprise runtime.

Provides the ``ai-company runtime`` command tree:

- ``runtime start``       — boot the runtime (startup sequence + engines + jobs).
- ``runtime stop``        — graceful shutdown of all engines and processes.
- ``runtime restart``     — stop, then boot again (hot restart).
- ``runtime status``      — lifecycle phase, engines, processes, active counts.
- ``runtime health``      — engine + system health checks.
- ``runtime metrics``     — counters, gauges, queue sizes, error rate.
- ``runtime diagnostics`` — full diagnostic report.
- ``runtime reload``      — hot-reload configuration (reports changed sections).
"""

from __future__ import annotations

import signal
import threading
from typing import Any

import typer

from ai_company.runtime import RuntimeEngine, create_runtime, main_loop
from ai_company.utils.console import console_print

app = typer.Typer(help="Enterprise Runtime Engine (boot & supervision)")


def _build_runtime(config_dir: str = "config") -> RuntimeEngine:
    """Construct a runtime engine without booting it."""
    try:
        return create_runtime(config_dir=config_dir)
    except Exception as exc:
        console_print(f"[red]Failed to construct runtime:[/red] {exc}")
        raise typer.Exit(1) from exc


def _ensure_running(runtime: RuntimeEngine) -> None:
    """Boot the runtime if it is not already running."""
    try:
        status = runtime.status()
    except Exception:
        status = None
    if status is None or status.phase.value != "running":
        runtime.start()


def _close(runtime: RuntimeEngine) -> None:
    """Best-effort teardown: stop the runtime if it is still running."""
    try:
        status = runtime.status()
        if status is not None and status.phase.value not in (
            "stopped",
            "failed",
        ):
            runtime.stop(reason="cli-exit")
    except Exception:
        pass


def _format_seconds(seconds: float) -> str:
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


@app.command("start")
def start(
    config_dir: str = typer.Option(
        "config", "--config-dir", help="Directory containing the runtime/ config"
    ),
) -> None:
    """Boot the runtime and run it in the foreground (Ctrl-C to stop)."""
    runtime = _build_runtime(config_dir)
    stop_event = threading.Event()

    def _request_stop(signum: int, _frame: Any) -> None:
        stop_event.set()

    previous = signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    try:
        runtime.start()
    except Exception as exc:
        console_print(f"[red]Runtime failed to start:[/red] {exc}")
        signal.signal(signal.SIGINT, previous)
        raise typer.Exit(1) from exc
    sequence = getattr(runtime, "startup_sequence", None)
    status = runtime.status()
    console_print(
        f"  [green]✓[/green] Runtime [bold]{status.name}[/bold] "
        f"(v{status.version}) is [green]{status.phase.value}[/green]"
    )
    console_print(
        f"  [green]✓[/green] Startup: {len(sequence.steps) if sequence else '-'} "
        f"steps, success={sequence.success if sequence else '-'}"
    )
    console_print(
        f"  [green]✓[/green] Engines: {', '.join(status.engines[i].name for i in range(len(status.engines)))}"
    )
    jobs = runtime.scheduler.jobs() if hasattr(runtime, "scheduler") else []
    console_print(f"  [green]✓[/green] Scheduled jobs: {len(jobs)}")
    console_print(
        "\n[dim]Runtime is running. Press Ctrl-C to stop.[/dim]",
    )
    try:
        main_loop(runtime, stop_event)
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        signal.signal(signal.SIGINT, previous)
        runtime.stop(reason="cli-interrupt")
    status = runtime.status()
    console_print(
        f"\n  [green]✓[/green] Runtime stopped -> [green]{status.phase.value}[/green]"
    )


@app.command("stop")
def stop(
    reason: str = typer.Option("cli", "--reason", help="Shutdown reason"),
    force: bool = typer.Option(
        False, "--force", help="Force shutdown (skip graceful engine stop)"
    ),
    config_dir: str = typer.Option(
        "config", "--config-dir", help="Directory containing the runtime/ config"
    ),
) -> None:
    """Gracefully shut down the runtime."""
    runtime = _build_runtime(config_dir)
    try:
        runtime.stop(reason=reason, force=force)
    except Exception as exc:
        console_print(f"[red]Runtime failed to stop:[/red] {exc}")
        raise typer.Exit(1) from exc
    status = runtime.status()
    console_print(
        f"  [green]✓[/green] Runtime is [green]{status.phase.value}[/green] ({reason})"
    )
    sequence = getattr(runtime, "shutdown_sequence", None)
    if sequence is not None:
        console_print(f"  [green]✓[/green] Shutdown success={sequence.success}")


@app.command("restart")
def restart(
    reason: str = typer.Option("cli-restart", "--reason", help="Restart reason"),
    config_dir: str = typer.Option(
        "config", "--config-dir", help="Directory containing the runtime/ config"
    ),
) -> None:
    """Stop, then boot the runtime again."""
    runtime = _build_runtime(config_dir)
    try:
        runtime.restart(reason=reason)
    except Exception as exc:
        console_print(f"[red]Runtime restart failed:[/red] {exc}")
        _close(runtime)
        raise typer.Exit(1) from exc
    status = runtime.status()
    console_print(
        f"  [green]✓[/green] Runtime restarted -> [green]{status.phase.value}[/green]"
    )
    console_print(
        f"  [green]✓[/green] Uptime: {_format_seconds(status.uptime_seconds)}"
    )


@app.command("status")
def status(
    config_dir: str = typer.Option(
        "config", "--config-dir", help="Directory containing the runtime/ config"
    ),
) -> None:
    """Show runtime lifecycle, engines, processes, and active counts."""
    runtime = _build_runtime(config_dir)
    try:
        _ensure_running(runtime)
        info = runtime.status().to_dict()
        console_print("[cyan]Runtime Status:[/cyan]")
        console_print(f"  Name: {info['name']} (v{info['version']})")
        console_print(f"  Phase: {info['phase']}")
        console_print(f"  Uptime: {_format_seconds(info['uptime_seconds'])}")
        console_print(f"  Message: {info['message'] or '-'}")

        engines = runtime.engine_states()
        console_print(f"\n  Engines ({len(engines)}):")
        for engine in engines:
            console_print(
                f"    {engine.name:<14} {engine.status.value:<12} "
                f"health={engine.health.value}"
            )
        processes = runtime.process_snapshot()
        console_print(f"\n  Processes ({len(processes)}):")
        if not processes:
            console_print("    (none)")
        for process in processes:
            console_print(
                f"    {process.get('name', '?'):<14} "
                f"state={process.get('status', '?')} "
                f"restarts={process.get('restart_count', 0)}"
            )
        jobs = runtime.scheduler.jobs() if hasattr(runtime, "scheduler") else []
        console_print(f"\n  Scheduled jobs: {len(jobs)}")
        console_print(
            "  Active: "
            f"pipelines={info['active_pipelines']} "
            f"workflows={info['active_workflows']} "
            f"decisions={info['active_decisions']} "
            f"meetings={info['active_meetings']} "
            f"projects={info['active_projects']} "
            f"agents={info['active_agents']}"
        )
    except Exception as exc:
        console_print(f"[red]Status failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        _close(runtime)


@app.command("health")
def health(
    config_dir: str = typer.Option(
        "config", "--config-dir", help="Directory containing the runtime/ config"
    ),
) -> None:
    """Run health probes against every engine and the system."""
    runtime = _build_runtime(config_dir)
    try:
        _ensure_running(runtime)
        checks = runtime.health()
        console_print("[cyan]Runtime Health Checks:[/cyan]")
        for check in checks:
            icon = {
                "healthy": "[green]✓[/green]",
                "degraded": "[yellow]![/yellow]",
                "unhealthy": "[red]✗[/red]",
            }.get(check.status.value, "[dim]?[/dim]")
            latency = (
                f" ({check.latency_ms:.0f}ms)"
                if getattr(check, "latency_ms", None) is not None
                else ""
            )
            console_print(
                f"  {icon} {check.component:<14} {check.status.value}{latency}"
            )
            if check.error:
                console_print(f"       [red]{check.error}[/red]")
        summary = runtime.health_summary()
        console_print(
            f"\n  Summary: {summary.get('healthy', 0)} healthy / "
            f"{summary.get('degraded', 0)} degraded / "
            f"{summary.get('unhealthy', 0)} unhealthy"
        )
    except Exception as exc:
        console_print(f"[red]Health check failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        _close(runtime)


@app.command("metrics")
def metrics(
    config_dir: str = typer.Option(
        "config", "--config-dir", help="Directory containing the runtime/ config"
    ),
) -> None:
    """Show runtime metrics: counters, gauges, queues, and error rates."""
    runtime = _build_runtime(config_dir)
    try:
        _ensure_running(runtime)
        snapshot = runtime.metrics()
        console_print("[cyan]Runtime Metrics:[/cyan]")
        console_print(f"  Uptime: {_format_seconds(snapshot.uptime_seconds)}")
        console_print(
            f"  System: cpu={snapshot.cpu_percent or 0:.1f}% "
            f"mem={snapshot.memory_percent or 0:.1f}%"
        )
        console_print(
            f"  Engines: active={snapshot.active_engines} "
            f"healthy={snapshot.engine_healthy} "
            f"degraded={snapshot.engine_degraded} "
            f"failed={snapshot.engine_failed}"
        )
        console_print(f"  Heartbeat misses: {snapshot.heartbeat_misses}")
        console_print(f"  Error rate: {snapshot.error_rate:.4f}")
        console_print(
            f"  Jobs: executed={snapshot.jobs_executed} "
            f"failed={snapshot.jobs_failed} restarts={snapshot.restarts}"
        )
        if snapshot.queue_sizes:
            queues = ", ".join(
                f"{name}={size}" for name, size in snapshot.queue_sizes.items()
            )
            console_print(f"  Queues: {queues}")
        if snapshot.counters:
            counters = ", ".join(
                f"{name}={value}" for name, value in snapshot.counters.items()
            )
            console_print(f"  Counters: {counters}")
        if snapshot.timers:
            timers = ", ".join(
                f"{name}={value:.3f}s" for name, value in snapshot.timers.items()
            )
            console_print(f"  Timers: {timers}")
    except Exception as exc:
        console_print(f"[red]Metrics failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        _close(runtime)


@app.command("diagnostics")
def diagnostics(
    config_dir: str = typer.Option(
        "config", "--config-dir", help="Directory containing the runtime/ config"
    ),
) -> None:
    """Produce a full diagnostic report (engines, health, config checksums)."""
    runtime = _build_runtime(config_dir)
    try:
        _ensure_running(runtime)
        report = runtime.diagnostics()
        console_print(
            f"[cyan]Diagnostics: {report.runtime_name} v{report.runtime_version}[/cyan]"
        )
        console_print(f"  Phase: {report.phase.value}")
        console_print(f"  Uptime: {_format_seconds(report.uptime_seconds)}")
        console_print(
            f"  Engines: {len(report.engines)} | Health checks: {len(report.health_checks)}"
        )
        console_print(f"  Config sections: {len(report.config_sections)}")
        for section, checksum in report.config_sections.items():
            console_print(f"    {section:<14} {checksum[:12]}")
        if report.errors:
            console_print(f"\n  [red]Errors ({len(report.errors)}):[/red]")
            for error in report.errors:
                console_print(f"    [red]✗[/red] {error}")
        if report.warnings:
            console_print(f"\n  [yellow]Warnings ({len(report.warnings)}):[/yellow]")
            for warning in report.warnings:
                console_print(f"    [yellow]![/yellow] {warning}")
        if report.recommendations:
            console_print("\n  [cyan]Recommendations:[/cyan]")
            for recommendation in report.recommendations:
                console_print(f"    → {recommendation}")
        if not report.errors and not report.warnings:
            console_print("\n  [green]No errors or warnings detected.[/green]")
    except Exception as exc:
        console_print(f"[red]Diagnostics failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        _close(runtime)


@app.command("reload")
def reload(
    config_dir: str = typer.Option(
        "config", "--config-dir", help="Directory containing the runtime/ config"
    ),
) -> None:
    """Hot-reload runtime configuration (restarts jobs, reapplies settings)."""
    runtime = _build_runtime(config_dir)
    try:
        _ensure_running(runtime)
        changed = runtime.reload()
        console_print(
            f"  [green]✓[/green] Configuration reloaded "
            f"({len(changed)} section(s) changed: {', '.join(changed) or 'none'})"
        )
        if changed:
            jobs = runtime.scheduler.jobs() if hasattr(runtime, "scheduler") else []
            console_print(
                f"  [green]✓[/green] Job catalog refreshed ({len(jobs)} jobs active)"
            )
    except Exception as exc:
        console_print(f"[red]Reload failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        _close(runtime)


# Re-export helper for programmatic use.
def build_runtime(config_dir: str = "config") -> RuntimeEngine:
    """Return a constructed RuntimeEngine (programmatic access)."""
    return _build_runtime(config_dir)


__all__: list[Any] = ["app", "build_runtime"]
