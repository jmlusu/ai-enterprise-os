"""Isolation alerts instrumentation (risk R5 closure / sprint 5.4 T3).

When the runtime supervisor isolates a component (engine heartbeat stall,
unhealthy health check, or failed recovery), an operator should see that
immediately on the dashboard — not only in logs. This module provides the
persistence path: a fail-open JSONL log at ``runtime/alerts.jsonl`` plus
read/summary helpers for the dashboard surfaces.

Alert lifecycle (no-spam contract):

- :func:`record_alert_open` appends an ``open`` record when a component is
  isolated. Repeated isolates of the same component are collapsed by the
  summary reader: **the latest record per component wins**, so a component
  stays "open" until a ``resolved`` record supersedes it.
- :func:`record_alert_resolved` appends a ``resolved`` record when the
  component is re-admitted (:meth:`Supervisor.unisolate`). After that the
  component no longer appears in ``open_alerts``.

:func:`alerts_summary` derives the current open-alert set, the open count
(dashboard red chip + KPI line), and the recent record tail. Like every
telemetry module in this package, all functions are fail-open: they never
raise, so monitoring can never break the supervisor or the API path.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ALERTS_RELATIVE_PATH = Path("runtime") / "alerts.jsonl"


def alerts_path() -> Path:
    """Return the alerts log path (relative to the working directory)."""
    return ALERTS_RELATIVE_PATH


def record_alert_open(
    *,
    component: str,
    reason: str = "",
    attempts: int | None = None,
    source: str = "runtime.supervisor",
) -> None:
    """Append one ``open`` alert record (fail-open).

    Called by :meth:`Supervisor.isolate`; never raises.
    """
    try:
        record: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "kind": "open",
            "component": component,
            "reason": reason,
            "attempts": attempts,
            "source": source,
        }
        path = alerts_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("Alert open write failed: %s", exc)


def record_alert_resolved(
    *,
    component: str,
    reason: str = "unisolated",
    source: str = "runtime.supervisor",
) -> None:
    """Append one ``resolved`` alert record (fail-open).

    Called by :meth:`Supervisor.unisolate`; never raises.
    """
    try:
        record: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "kind": "resolved",
            "component": component,
            "reason": reason,
            "attempts": None,
            "source": source,
        }
        path = alerts_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("Alert resolved write failed: %s", exc)


def read_alerts(limit: int = 200) -> list[dict[str, Any]]:
    """Return the last ``limit`` alert records (newest last, corrupt lines skipped)."""
    path = alerts_path()
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
                    logger.debug("Skipping corrupt alert line")
    except OSError as exc:
        logger.debug("Alert read failed: %s", exc)
        return []
    return records[-limit:]


def alerts_summary(limit: int = 200) -> dict[str, Any]:
    """Derive the current open-alert set from the alerts log.

    The latest record per component wins: a component is open only when its
    most recent record is an ``open`` record. Repeated isolates therefore do
    not spam — one open alert per component until a ``resolved`` record
    supersedes it (alert is resolved on recovery / un-isolation).
    """
    records = read_alerts(limit=limit)
    if not records:
        return {
            "persistence_enabled": True,
            "records": 0,
            "open_count": 0,
            "open_alerts": [],
            "recent": [],
        }

    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        component = str(record.get("component") or "(unknown)")
        latest[component] = record

    open_alerts: list[dict[str, Any]] = []
    for component, record in latest.items():
        if record.get("kind") != "open":
            continue
        open_alerts.append(
            {
                "component": component,
                "opened_at": record.get("timestamp"),
                "reason": record.get("reason") or "",
                "attempts": record.get("attempts"),
                "source": record.get("source") or "",
            }
        )

    return {
        "persistence_enabled": True,
        "records": len(records),
        "open_count": len(open_alerts),
        "open_alerts": sorted(open_alerts, key=lambda a: str(a["opened_at"])),
        "recent": records,
    }


__all__ = [
    "ALERTS_RELATIVE_PATH",
    "alerts_path",
    "alerts_summary",
    "read_alerts",
    "record_alert_open",
    "record_alert_resolved",
]
