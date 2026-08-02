"""Command line interface for the persona agent sync.

Usage::

    python -m ai_company.agents sync [--dry-run] [--force]
        [--scope project|global|both] [--output-dir PATH]

- ``--scope both`` (default) persists personas to both the project
  ``.opencode/agents`` directory and the user-global opencode agents
  directory (``~/.config/opencode/agents``); ``--scope project`` writes to
  ``.opencode/agents`` only; ``--scope global`` writes globally only.

This is a standalone argparse entry point — deliberately NOT part of the
frozen ``ai_company.cli`` Typer tree.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ai_company.agents.slug_map import AgentSlugCollisionError
from ai_company.agents.sync import (
    AgentSyncConfig,
    AgentSyncEngine,
    print_plan_summary,
)
from ai_company.utils.console import configure_console, console_print


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m ai_company.agents",
        description=(
            "Sync company personas (executives, specialists, board) into "
            "opencode agent files so they can be invoked by @-mention."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    sync = subparsers.add_parser("sync", help="Synchronize persona agent files")
    sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing any files",
    )
    sync.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files whose content differs",
    )
    sync.add_argument(
        "--include-departments",
        action="store_true",
        help="Phase 2 opt-in: generate department role agents (not implemented)",
    )
    sync.add_argument(
        "--scope",
        choices=("project", "global", "both"),
        default="both",
        help=(
            "Where to write agent files: 'both' (project + global; default), "
            "'project' (.opencode/agents only), or 'global' "
            "(~/.config/opencode/agents only)"
        ),
    )
    sync.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Explicit directory override (wins over --scope; default: "
            "resolved from --scope)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI; returns a process exit code."""
    configure_console()
    args = build_parser().parse_args(argv)
    if args.command != "sync":
        return 2

    config = AgentSyncConfig(
        dry_run=args.dry_run,
        force=args.force,
        include_departments=args.include_departments,
        scope=args.scope,
        output_dir=args.output_dir,
    )
    engine = AgentSyncEngine(config=config)

    for out_dir in config.output_dirs():
        console_print(f"[cyan]Target:[/cyan] {out_dir}")

    try:
        if config.dry_run:
            plan = engine.plan()
            print_plan_summary(plan, dry_run=True)
            return 0
        result = engine.run()
    except (RuntimeError, NotImplementedError, AgentSlugCollisionError) as exc:
        console_print(f"[red]✗ {exc}[/red]")
        return 1

    if result.errors:
        return 1
    if result.conflicts:
        console_print(
            "[yellow]Conflicts remain — rerun with --force to overwrite "
            "existing files.[/yellow]"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
