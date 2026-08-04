"""GUI/desktop action telemetry — honest D5 north-star numerator (sprint 5.5 P5).

The D5 north-star metric (CEO sign-off 2026-08-02) is the share of operator
actions performed via Dashboard/OpenCode desktop, targeting >=80% by month 6.
The denominator is CLI invocations (``runtime/cli_telemetry.jsonl``); the
numerator must distinguish GUI/desktop actions from CLI actions to be honest:

- ``gui`` — dashboard operator writes, recorded here from the shared
  ``WriteGuard`` (ADR 0010): every guarded mutation is one operator action;
- ``desktop`` — explicit desktop actions (``review.submit``, sprint 5.5 P4)
  plus the OpenCode session activity derived from
  ``runtime/session_telemetry.jsonl`` (commands run + tool calls at the newest
  checkpoint per session, matching the Sessions panel);
- ``cli`` — not recorded here: ``runtime/cli_telemetry.jsonl`` is the
  signed-off baseline and is read directly for the share computation.

Telemetry infrastructure writes (``telemetry.session.persist``) are not
operator actions and are excluded from recording. All writes are fail-open:
telemetry must never break the caller's path (same contract as CLI, provider,
and session telemetry).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ai_company.telemetry.cli import TELEMETRY_RELATIVE_PATH
from ai_company.telemetry.sessions import read_session_telemetry

logger = logging.getLogger(__name__)

ACTION_TELEMETRY_RELATIVE_PATH = Path("runtime") / "action_telemetry.jsonl"

#: D5 target share of operator actions via GUI/desktop (signed off 2026-08-02).
D5_TARGET_PCT = 80.0
DEFAULT_WINDOW_DAYS = 30

# Hard cap on the log as a safety net on top of the retention policy (mirrors
# the session telemetry cap; retention truncates by age on the scheduler job).
_MAX_RECORDS = 5000


def action_telemetry_path() -> Path:
    """Return the action telemetry log path (relative to the CWD)."""
    return ACTION_TELEMETRY_RELATIVE_PATH


def record_action(
    source: str,
    action: str,
    *,
    count: int = 1,
    session_id: str | None = None,
    duration_seconds: float | None = None,
) -> None:
    """Append one operator action record to the log (fail-open).

    ``source`` is ``"gui"`` or ``"desktop"`` (CLI actions live in the CLI
    telemetry log). Never raises: telemetry must not break the caller.
    """
    try:
        record: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": source,
            "action": action,
            "count": max(1, int(count)),
        }
        if session_id is not None:
            record["session_id"] = session_id
        if duration_seconds is not None:
            record["duration_seconds"] = duration_seconds
        path = action_telemetry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        _maybe_prune(path)
    except Exception as exc:
        logger.debug("Action telemetry write failed: %s", exc)


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
        logger.debug("Pruned action telemetry to %d records", len(kept))
    except OSError as exc:
        logger.debug("Action telemetry prune skipped: %s", exc)


def _iter_records(path: Path) -> Iterator[dict[str, Any]]:
    """Yield parsed JSON lines from ``path``; missing/corrupt lines skipped."""
    if not path.is_file():
        return
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("Skipping corrupt telemetry line")
    except OSError as exc:
        logger.debug("Telemetry read failed: %s", exc)


def read_action_records(limit: int = 200) -> list[dict[str, Any]]:
    """Return the last ``limit`` action records (oldest first within tail)."""
    return list(_iter_records(action_telemetry_path()))[-limit:]


def _parse_ts(record: dict[str, Any]) -> datetime | None:
    """Parse a record's UTC timestamp; None on missing/invalid."""
    raw = record.get("timestamp")
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(str(raw))
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def _record_count(record: dict[str, Any]) -> int:
    return max(0, int(record.get("count", 1)))


def _count_log(path: Path, since: datetime) -> int:
    """Sum action counts in ``path`` for records at/after ``since``."""
    total = 0
    for record in _iter_records(path):
        ts = _parse_ts(record)
        if ts is not None and ts >= since:
            total += _record_count(record)
    return total


def _desktop_session_actions(since: datetime) -> int:
    """Sum desktop session actions (commands + tool calls) since ``since``.

    Uses the newest checkpoint per session (same dedupe as the Sessions panel)
    so cumulative checkpoints from the same session are never double-counted.
    """
    newest: dict[str, dict[str, Any]] = {}
    for record in read_session_telemetry(limit=_MAX_RECORDS):
        ts = _parse_ts(record)
        if ts is None or ts < since:
            continue
        session_id = record.get("session_id") or "(unknown)"
        current = newest.get(session_id)
        if current is None:
            newest[session_id] = record
            continue
        current_ts = _parse_ts(current)
        if current_ts is None or ts > current_ts:
            newest[session_id] = record
    return sum(
        int(record.get("commands_run", 0)) + int(record.get("tool_calls", 0))
        for record in newest.values()
    )


def action_share_summary(
    window_days: int = DEFAULT_WINDOW_DAYS,
    target_pct: float = D5_TARGET_PCT,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compute the D5 operator-action share over the trailing window.

    Numerator = GUI actions (guarded dashboard writes) + desktop actions
    (explicit records + OpenCode session commands/tool calls). Denominator =
    numerator + CLI invocations (the signed-off D5 baseline). Fail-open: any
    missing/corrupt log contributes zero.
    """
    now = now or datetime.now(UTC)
    since = now - timedelta(days=window_days)

    cli_total = _count_log(TELEMETRY_RELATIVE_PATH, since)
    gui_total = 0
    desktop_total = 0
    by_action: dict[tuple[str, str], int] = {}
    for record in _iter_records(action_telemetry_path()):
        ts = _parse_ts(record)
        if ts is None or ts < since:
            continue
        source = str(record.get("source") or "")
        action = str(record.get("action") or "")
        count = _record_count(record)
        if source == "gui":
            gui_total += count
        elif source == "desktop":
            desktop_total += count
        if source and action:
            key = (source, action)
            by_action[key] = by_action.get(key, 0) + count

    desktop_session_actions = _desktop_session_actions(since)
    numerator = gui_total + desktop_total + desktop_session_actions
    actions_total = numerator + cli_total
    share_pct = round(numerator / actions_total * 100, 1) if actions_total else 0.0

    return {
        "persistence_enabled": True,
        "window_days": window_days,
        "target_pct": target_pct,
        "counts": {
            "cli": cli_total,
            "gui": gui_total,
            "desktop": desktop_total,
        },
        "desktop_session_actions": desktop_session_actions,
        "gui_desktop_total": numerator,
        "cli_total": cli_total,
        "actions_total": actions_total,
        "share_pct": share_pct,
        "at_target": share_pct >= target_pct,
        "by_action": [
            {"source": src, "action": act, "count": count}
            for (src, act), count in sorted(
                by_action.items(), key=lambda item: item[1], reverse=True
            )
        ],
    }


__all__ = [
    "ACTION_TELEMETRY_RELATIVE_PATH",
    "D5_TARGET_PCT",
    "DEFAULT_WINDOW_DAYS",
    "action_share_summary",
    "action_telemetry_path",
    "read_action_records",
    "record_action",
]
