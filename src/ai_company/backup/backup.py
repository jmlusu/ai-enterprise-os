"""Create timestamped backup bundles of the gitignored runtime state.

The AI Enterprise OS keeps its single-writer file state in gitignored
directories (``memory/``, ``events/``, ``generated/``, ``runtime/``,
``.ai-company/``). A backup bundle collects those directories into a
timestamped ``.tar.gz`` under ``backups/`` so the local state has an
off-process copy for disaster recovery and nightly archival.

Local usage::

    uv run python -m ai_company.backup
    uv run python -m ai_company.backup --dest D:/backups --dirs memory events

CI usage (see ``.github/workflows/nightly-backup.yml``) runs the same
entry point on a schedule and uploads the bundle as a workflow artifact.
"""

from __future__ import annotations

import argparse
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_SOURCE_DIRS: list[str] = [
    ".ai-company",
    "memory",
    "events",
    "generated",
    "runtime",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def create_backup(
    dest_dir: str | Path = "backups",
    source_dirs: list[str] | None = None,
    root: str | Path = ".",
) -> Path:
    """Bundle the configured source directories into a timestamped archive.

    Args:
        dest_dir: Directory the ``.tar.gz`` bundle is written to.
        source_dirs: Directory names (relative to ``root``) to include.
            Defaults to :data:`DEFAULT_SOURCE_DIRS`.
        root: Working directory the sources are resolved against.

    Returns:
        The path of the created archive.

    Raises:
        ValueError: When no source directory exists under ``root``.
    """
    root_path = Path(root)
    dest_path = Path(dest_dir)
    sources = source_dirs or list(DEFAULT_SOURCE_DIRS)

    existing = [name for name in sources if (root_path / name).is_dir()]
    if not existing:
        raise ValueError(
            f"No source directories found under {root_path} "
            f"(looked for: {', '.join(sources)})"
        )

    dest_path.mkdir(parents=True, exist_ok=True)
    stamp = _utcnow().strftime("%Y%m%dT%H%M%SZ")
    archive = dest_path / f"ai-enterprise-os-{stamp}.tar.gz"

    with tarfile.open(archive, "w:gz") as handle:
        for name in existing:
            handle.add(root_path / name, arcname=name, recursive=True)

    return archive


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``python -m ai_company.backup``."""
    parser = argparse.ArgumentParser(
        prog="ai_company.backup",
        description="Bundle gitignored runtime state into a tar.gz backup.",
    )
    parser.add_argument(
        "--dest",
        default="backups",
        help="Directory to write the backup bundle to (default: backups)",
    )
    parser.add_argument(
        "--dirs",
        nargs="+",
        default=None,
        help="Source directories to bundle (default: the standard five)",
    )
    args = parser.parse_args(argv)

    try:
        archive = create_backup(dest_dir=args.dest, source_dirs=args.dirs)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    size = archive.stat().st_size
    print(f"Backup created: {archive} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
