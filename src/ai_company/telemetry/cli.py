"""Baseline CLI invocation telemetry.

Every ``ai-company`` invocation is recorded as one JSON line appended to
``runtime/cli_telemetry.jsonl`` (fail-open: telemetry must never break the
CLI, so all writes are wrapped and logged at debug level).

The log is the source of truth for "who ran what, when" and feeds the
dashboard's model/command usage views in later phases. Each record:

- ``timestamp`` — UTC ISO-8601 when the command finished
- ``argv`` — full command line (excluding the program name)
- ``command`` — first token (the command/group that was invoked)
- ``duration_seconds`` — wall-clock time of the invocation
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TELEMETRY_RELATIVE_PATH = Path("runtime") / "cli_telemetry.jsonl"


def telemetry_path() -> Path:
    """Return the telemetry log path (relative to the working directory)."""
    return TELEMETRY_RELATIVE_PATH


def record_cli_invocation(
    command: str | None = None,
    argv: list[str] | None = None,
    duration_seconds: float | None = None,
) -> None:
    """Append one invocation record to the telemetry log (fail-open).

    ``command`` is optional for backwards compatibility: when omitted it is
    derived from the first token of ``argv`` (falling back to an empty
    string when no arguments are present).

    Args:
        command: The invoked command/group name (e.g. ``generate``).
        argv: Full argument vector (excluding the program name); defaults
            to the current process's ``sys.argv[1:]``.
        duration_seconds: Wall-clock time of the invocation.
    """
    try:
        if argv is None:
            argv = list(sys.argv[1:])
        if command is None:
            command = argv[0] if argv else ""
        record: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "command": command,
            "argv": list(argv),
            "duration_seconds": duration_seconds,
        }
        path = telemetry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # telemetry must never break the CLI
        logger.debug("CLI telemetry write failed: %s", exc)
