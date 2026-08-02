"""Runtime metrics persistence (risk R5 — "telemetry is captured, not discarded").

The in-memory :class:`MetricsRegistry` loses every snapshot on restart, so the
Model Usage / Agent Health / KPI panels have no upstream history. This module
provides the JSONL source of truth: each ``RuntimeMetrics`` snapshot is
appended to ``runtime/metrics_history.jsonl`` (fail-open, append-only) with a
UTC timestamp, exactly like the CLI invocation telemetry pattern.

Reads are cheap and idempotent: :func:`read_metrics_history` parses the log
tail, and :func:`metrics_summary` derives the latest snapshot plus lightweight
trend facts (sample count, first/last timestamps, last CPU/memory/engine
counts) for the dashboard panels.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

METRICS_HISTORY_RELATIVE_PATH = Path("runtime") / "metrics_history.jsonl"

# Last timestamp emitted by this process, so rapid successive snapshots always
# get strictly increasing timestamps even on platforms whose system clock has
# coarse resolution (e.g. Windows ~15 ms ticks).
_last_timestamp: str | None = None


def metrics_history_path() -> Path:
    """Return the metrics history log path (relative to the working directory)."""
    return METRICS_HISTORY_RELATIVE_PATH


def log_metrics_snapshot(snapshot: dict[str, Any]) -> None:
    """Append one metrics snapshot to the history log (fail-open).

    The snapshot is tagged with the capture time in UTC. Persistence failures
    are logged at debug level and never raise — telemetry must never break a
    read or write path (project rule, same as CLI telemetry).
    """
    try:
        record: dict[str, Any] = {
            "timestamp": _next_timestamp(),
            "snapshot": snapshot,
        }
        path = metrics_history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("Metrics history write failed: %s", exc)


def _next_timestamp() -> str:
    """UTC ISO-8601 timestamp, strictly increasing within this process.

    ``datetime.now(UTC)`` can return the same value twice on coarse-clock
    platforms; bump by one microsecond so ordering facts (trend, first/last)
    stay meaningful.
    """
    global _last_timestamp
    candidate = datetime.now(UTC).isoformat()
    if _last_timestamp is not None and candidate <= _last_timestamp:
        last_dt = datetime.fromisoformat(_last_timestamp)
        candidate = (last_dt + timedelta(microseconds=1)).isoformat()
    _last_timestamp = candidate
    return candidate


def read_metrics_history(limit: int = 100) -> list[dict[str, Any]]:
    """Return the last ``limit`` persisted snapshots (oldest first within tail).

    Corrupt lines are skipped; a missing file yields an empty list.
    """
    path = metrics_history_path()
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.debug("Skipping corrupt metrics history line")
    except OSError as exc:
        logger.debug("Metrics history read failed: %s", exc)
        return []
    return records[-limit:]


def metrics_summary(limit: int = 100) -> dict[str, Any]:
    """Derive a dashboard-friendly summary from the persisted history.

    Returns the latest snapshot, the sample count, first/last capture times,
    and a small trend dict (last CPU %, last memory %, last healthy/degraded/
    failed engine counts, cumulative jobs executed from the last snapshot).
    """
    records = read_metrics_history(limit=limit)
    if not records:
        return {
            "persistence_enabled": True,
            "samples": 0,
            "latest": None,
            "first_timestamp": None,
            "last_timestamp": None,
            "trend": {},
        }
    latest_record = records[-1]
    snapshot = latest_record.get("snapshot", {})
    gauges = snapshot.get("gauges", {})
    counters = snapshot.get("counters", {})
    trend = {
        "cpu_percent": gauges.get("cpu_percent"),
        "memory_percent": gauges.get("memory_percent"),
        "engine_healthy": int(gauges.get("engine_healthy", 0)),
        "engine_degraded": int(gauges.get("engine_degraded", 0)),
        "engine_failed": int(gauges.get("engine_failed", 0)),
        "jobs_executed": int(counters.get("jobs_executed", 0)),
        "jobs_failed": int(counters.get("jobs_failed", 0)),
        "failed_events": int(counters.get("failed_events", 0)),
        "restarts": int(counters.get("restarts", 0)),
        "uptime_seconds": snapshot.get("uptime_seconds"),
    }
    return {
        "persistence_enabled": True,
        "samples": len(records),
        "latest": latest_record,
        "first_timestamp": records[0].get("timestamp"),
        "last_timestamp": latest_record.get("timestamp"),
        "trend": trend,
    }


__all__ = [
    "METRICS_HISTORY_RELATIVE_PATH",
    "log_metrics_snapshot",
    "metrics_history_path",
    "metrics_summary",
    "read_metrics_history",
]
