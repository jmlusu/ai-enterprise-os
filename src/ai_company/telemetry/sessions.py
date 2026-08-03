"""OpenCode desktop session telemetry (sprint 5.5 P2).

The OpenCode desktop plugin captures per-session activity (messages, tool
calls, commands, tokens, cost) and posts checkpoints to the guarded
``POST /api/telemetry/session`` endpoint. This module is the server-side
source of truth — a fail-open JSONL log at ``runtime/session_telemetry.jsonl``
following the exact ``provider_usage`` pattern:

- :func:`record_session_telemetry` appends one checkpoint (never raises);
  every checkpoint carries a ``timestamp`` capture time so the shared
  retention machinery (``telemetry/retention.py``, ``rollup: false``) can
  truncate by age without a session-specific aggregator;
- :func:`read_session_telemetry` parses the log tail;
- :func:`session_telemetry_summary` dedups checkpoints to the newest per
  session and derives totals for the dashboard Sessions panel.

Session records are read straight from the JSONL (no SQLite read-model
projection yet — the readmodel sync keys stay metrics/provider/cli only).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SESSION_TELEMETRY_RELATIVE_PATH = Path("runtime") / "session_telemetry.jsonl"

# Hard cap as a secondary safety net on top of the retention policy: when the
# log exceeds this many lines it is rewritten keeping the newest half. The
# retention scheduler truncates by age (180 days); this bounds an idle box.
_MAX_RECORDS = 5000


def session_telemetry_path() -> Path:
    """Return the session telemetry log path (relative to the CWD)."""
    return SESSION_TELEMETRY_RELATIVE_PATH


def record_session_telemetry(
    *,
    session_id: str,
    started_at: str | None = None,
    updated_at: str | None = None,
    end_reason: str = "checkpoint",
    title: str = "",
    directory: str = "",
    project_id: str | None = None,
    agent: str | None = None,
    model_id: str | None = None,
    provider_id: str | None = None,
    messages_user: int = 0,
    messages_assistant: int = 0,
    tool_calls: int = 0,
    commands_run: int = 0,
    tools_used: dict[str, int] | None = None,
    tokens_input: int = 0,
    tokens_output: int = 0,
    tokens_reasoning: int = 0,
    cost: float = 0.0,
    additions: int = 0,
    deletions: int = 0,
    files_changed: int = 0,
) -> None:
    """Append one session checkpoint to the log (fail-open).

    Never raises: telemetry ingestion must never break the caller's path
    (same contract as ``provider_usage`` / CLI telemetry).
    """
    try:
        record: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "session_id": session_id,
            "started_at": started_at,
            "updated_at": updated_at,
            "end_reason": end_reason,
            "title": title,
            "directory": directory,
            "project_id": project_id,
            "agent": agent,
            "model_id": model_id,
            "provider_id": provider_id,
            "messages_user": messages_user,
            "messages_assistant": messages_assistant,
            "tool_calls": tool_calls,
            "commands_run": commands_run,
            "tools_used": dict(tools_used or {}),
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "tokens_reasoning": tokens_reasoning,
            "cost": cost,
            "additions": additions,
            "deletions": deletions,
            "files_changed": files_changed,
        }
        path = session_telemetry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        _maybe_prune(path)
    except Exception as exc:
        logger.debug("Session telemetry write failed: %s", exc)


def _maybe_prune(path: Path) -> None:
    """Rewind an oversized log to the newest ``_MAX_RECORDS`` lines (fail-open)."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
        if len(lines) <= _MAX_RECORDS:
            return
        kept = lines[-_MAX_RECORDS:]
        temp = path.with_name(f"{path.name}.tmp")
        with temp.open("w", encoding="utf-8") as handle:
            handle.writelines(kept)
        temp.replace(path)
        logger.debug("Pruned session telemetry to %d records", len(kept))
    except OSError as exc:
        logger.debug("Session telemetry prune skipped: %s", exc)


def read_session_telemetry(limit: int = 200) -> list[dict[str, Any]]:
    """Return the last ``limit`` session checkpoints (oldest first within tail)."""
    path = session_telemetry_path()
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
                    logger.debug("Skipping corrupt session telemetry line")
    except OSError as exc:
        logger.debug("Session telemetry read failed: %s", exc)
        return []
    return records[-limit:]


def session_telemetry_summary(limit: int = 200) -> dict[str, Any]:
    """Derive the dashboard Sessions panel data from the persisted log.

    Returns the newest checkpoint per session (newest first), distinct session
    count, aggregate totals, per-model rows, and per end-reason counts.
    """
    records = read_session_telemetry(limit=limit)
    if not records:
        return {
            "persistence_enabled": True,
            "records": 0,
            "sessions": 0,
            "recent": [],
            "totals": _empty_totals(),
            "by_model": [],
            "by_end_reason": {},
        }

    newest_by_session: dict[str, dict[str, Any]] = {}
    for record in records:
        session_id = record.get("session_id") or "(unknown)"
        current = newest_by_session.get(session_id)
        if current is None or _record_ts(record) > _record_ts(current):
            newest_by_session[session_id] = record

    recent = sorted(
        newest_by_session.values(),
        key=lambda r: _record_ts(r),
        reverse=True,
    )

    totals = _empty_totals()
    by_model: dict[str, dict[str, Any]] = {}
    by_end_reason: dict[str, int] = {}
    for record in recent:
        totals["sessions"] += 1
        totals["user_messages"] += int(record.get("messages_user", 0))
        totals["assistant_messages"] += int(record.get("messages_assistant", 0))
        totals["tool_calls"] += int(record.get("tool_calls", 0))
        totals["commands_run"] += int(record.get("commands_run", 0))
        totals["tokens_input"] += int(record.get("tokens_input", 0))
        totals["tokens_output"] += int(record.get("tokens_output", 0))
        totals["tokens_reasoning"] += int(record.get("tokens_reasoning", 0))
        totals["cost"] += float(record.get("cost", 0.0))
        reason = record.get("end_reason") or "checkpoint"
        by_end_reason[reason] = by_end_reason.get(reason, 0) + 1
        model = record.get("model_id") or "(unknown)"
        row = by_model.setdefault(
            model,
            {
                "model_id": model,
                "sessions": 0,
                "assistant_messages": 0,
                "tool_calls": 0,
                "cost": 0.0,
            },
        )
        row["sessions"] += 1
        row["assistant_messages"] += int(record.get("messages_assistant", 0))
        row["tool_calls"] += int(record.get("tool_calls", 0))
        row["cost"] += float(record.get("cost", 0.0))

    totals["cost"] = round(totals["cost"], 6)
    models = sorted(by_model.values(), key=lambda m: m["sessions"], reverse=True)
    return {
        "persistence_enabled": True,
        "records": len(records),
        "sessions": totals["sessions"],
        "recent": recent,
        "totals": totals,
        "by_model": models,
        "by_end_reason": by_end_reason,
    }


def _empty_totals() -> dict[str, Any]:
    return {
        "sessions": 0,
        "user_messages": 0,
        "assistant_messages": 0,
        "tool_calls": 0,
        "commands_run": 0,
        "tokens_input": 0,
        "tokens_output": 0,
        "tokens_reasoning": 0,
        "cost": 0.0,
    }


def _record_ts(record: dict[str, Any]) -> str:
    """Comparable capture timestamp (missing values sort as oldest)."""
    value = record.get("timestamp")
    return str(value) if isinstance(value, str) else ""


__all__ = [
    "SESSION_TELEMETRY_RELATIVE_PATH",
    "read_session_telemetry",
    "record_session_telemetry",
    "session_telemetry_path",
    "session_telemetry_summary",
]
