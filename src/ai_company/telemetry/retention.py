"""Telemetry retention + rollup (sprint 5.4 T2).

The telemetry JSONL logs (metrics history, provider usage, CLI invocations)
grow without bound. This module bounds them with config-driven retention
policies (``config/runtime/telemetry.yaml``) under the **rollup-then-truncate**
contract:

1. Records older than a source's retention window are *expired*.
2. Expired records are aggregated into hourly/daily **rollup** records and
   appended to the source's rollup file (``runtime/rollup_<source>.jsonl``).
3. Only after the rollup write succeeds is the raw log truncated to keep the
   non-expired records — raw data is never truncated before rollup.

Rollup is idempotent: a bucket already present in the rollup file is skipped,
so re-running apply (or a crash between rollup-append and truncate) cannot
double-count a bucket.

API
---
- :func:`load_policies` — merge the ``telemetry`` config section over defaults.
- :func:`retention_summary` — dry-run report (what the next apply would do).
- :func:`apply_retention` — rollup-then-truncate (``dry_run`` to preview).
- :func:`read_rollups` / :func:`rollup_summary` — rollup-aware read path.

Like every telemetry module, everything is fail-open: retention can never
break the scheduler job or the API path.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# (raw_path, rollup_path) per telemetry source, relative to the CWD.
SOURCE_PATHS: dict[str, tuple[Path, Path]] = {
    "metrics_history": (
        Path("runtime") / "metrics_history.jsonl",
        Path("runtime") / "rollup_metrics_history.jsonl",
    ),
    "provider_usage": (
        Path("runtime") / "provider_usage.jsonl",
        Path("runtime") / "rollup_provider_usage.jsonl",
    ),
    "cli_telemetry": (
        Path("runtime") / "cli_telemetry.jsonl",
        Path("runtime") / "rollup_cli_telemetry.jsonl",
    ),
}

# Default retention policies (mirror config/runtime/telemetry.yaml).
DEFAULT_POLICIES: dict[str, dict[str, Any]] = {
    "metrics_history": {"days": 7, "rollup": True},
    "provider_usage": {"days": 90, "rollup": True},
    "cli_telemetry": {"days": 180, "rollup": True},
}

GRANULARITIES: tuple[str, ...] = ("hourly", "daily")


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


def bucket_key(timestamp: datetime, granularity: str) -> str:
    """Return the bucket start key for a timestamp and granularity."""
    if granularity == "daily":
        return timestamp.date().isoformat()
    # hourly (and any unknown granularity fall back to hourly precision)
    return timestamp.replace(minute=0, second=0, microsecond=0).isoformat()


# ── Policy loading ─────────────────────────────────────────────────


def telemetry_config_path() -> Path:
    """Return the telemetry config path (relative to the working directory)."""
    return Path("config") / "runtime" / "telemetry.yaml"


def load_policies(config: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Merge the ``telemetry`` config section (or file) over defaults.

    ``config`` may be the engine's ``telemetry`` section dict (the
    ``retention`` key) or ``None`` to read ``config/runtime/telemetry.yaml``.
    Unknown sources in the config are ignored; missing sources use defaults.
    """
    policies: dict[str, dict[str, Any]] = {}
    for key, default in DEFAULT_POLICIES.items():
        policies[key] = dict(default)
    retention: dict[str, Any] = {}
    if config is not None:
        retention = config.get("retention") or {}
    else:
        try:
            path = telemetry_config_path()
            if path.is_file():
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}
                retention = data.get("retention") or {}
        except (OSError, ValueError) as exc:
            logger.debug("Telemetry config read failed: %s", exc)
    for key, spec in retention.items():
        if key not in policies or not isinstance(spec, dict):
            continue
        merged = dict(policies[key])
        merged["days"] = max(0, int(spec.get("days", merged["days"])))
        merged["rollup"] = bool(spec.get("rollup", merged["rollup"]))
        policies[key] = merged
    return policies


# ── Aggregators ────────────────────────────────────────────────────


def _row_metrics(source: str) -> dict[str, Any]:
    """Empty per-bucket metrics dict for a source."""
    if source == "provider_usage":
        return {
            "samples": 0,
            "requests": 0,
            "successes": 0,
            "errors": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "latency_sum": 0.0,
            "latency_count": 0,
        }
    if source == "cli_telemetry":
        return {
            "samples": 0,
            "invocations": 0,
            "duration_sum": 0.0,
            "duration_count": 0,
        }
    return {"samples": 0}


def _agg_key(source: str, record: dict[str, Any]) -> str:
    """Bucket aggregation key: model / command / ``system`` for metrics."""
    if source == "provider_usage":
        return str(record.get("model") or "(unknown)")
    if source == "cli_telemetry":
        return str(record.get("command") or "(unknown)")
    return "system"


def _fold(source: str, row: dict[str, Any], record: dict[str, Any]) -> None:
    """Fold one record into a bucket row."""
    row["samples"] += 1
    if source == "metrics_history":
        snapshot = record.get("snapshot") or {}
        for key, value in snapshot.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                row[key] = value  # last sample in bucket wins (gauges/counters)
        return
    if source == "provider_usage":
        row["requests"] += 1
        ok = bool(record.get("ok", True))
        if ok:
            row["successes"] += 1
        else:
            row["errors"] += 1
        usage = record.get("usage") or {}
        row["prompt_tokens"] += int(usage.get("prompt_tokens", 0))
        row["completion_tokens"] += int(usage.get("completion_tokens", 0))
        row["total_tokens"] += int(
            usage.get("total_tokens", 0)
            or int(usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))
        )
        latency = record.get("latency_seconds")
        if latency is not None:
            row["latency_sum"] += float(latency)
            row["latency_count"] += 1
        return
    if source == "cli_telemetry":
        row["invocations"] += 1
        duration = record.get("duration_seconds")
        if duration is not None:
            row["duration_sum"] += float(duration)
            row["duration_count"] += 1
        return


def _finalize_metrics(source: str, row: dict[str, Any]) -> dict[str, Any]:
    """Derive averages and drop internals before writing a rollup row."""
    metrics = dict(row)
    if source == "provider_usage":
        metrics["avg_latency_seconds"] = (
            round(metrics["latency_sum"] / metrics["latency_count"], 4)
            if metrics["latency_count"]
            else None
        )
        metrics.pop("latency_sum", None)
        metrics.pop("latency_count", None)
    elif source == "cli_telemetry":
        metrics["avg_duration_seconds"] = (
            round(metrics["duration_sum"] / metrics["duration_count"], 4)
            if metrics["duration_count"]
            else None
        )
        metrics.pop("duration_sum", None)
        metrics.pop("duration_count", None)
    return metrics


def _aggregate(
    source: str, records: list[dict[str, Any]], granularity: str
) -> list[dict[str, Any]]:
    """Group records into rollup rows for one granularity."""
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        ts = _parse_ts(record)
        if ts is None:
            continue
        key = (bucket_key(ts, granularity), _agg_key(source, record))
        if key not in rows:
            rows[key] = _row_metrics(source)
        _fold(source, rows[key], record)
    result: list[dict[str, Any]] = []
    for (bucket, agg_key), row in rows.items():
        result.append(
            {
                "timestamp": bucket,
                "source": source,
                "granularity": granularity,
                "key": agg_key,
                "metrics": _finalize_metrics(source, row),
                "records": row["samples"],
            }
        )
    return result


# ── File helpers ───────────────────────────────────────────────────


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read all JSON lines from a file; corrupt lines skipped."""
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
                    logger.debug("Skipping corrupt line in %s", path)
    except OSError as exc:
        logger.debug("Read failed for %s: %s", path, exc)
        return []
    return records


def _append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Append records as JSON lines (raises on failure)."""
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _existing_rollup_keys(path: Path) -> set[tuple[str, str, str]]:
    """Set of ``(timestamp, granularity, key)`` already rolled up (idempotency)."""
    keys: set[tuple[str, str, str]] = set()
    for record in _read_jsonl(path):
        ts = record.get("timestamp")
        granularity = record.get("granularity")
        key = record.get("key")
        if ts is not None and granularity is not None and key is not None:
            keys.add((str(ts), str(granularity), str(key)))
    return keys


def _truncate_keep(path: Path, keep: list[dict[str, Any]]) -> bool:
    """Rewrite the raw file keeping only ``keep`` records (temp + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.tmp")
    with temp.open("w", encoding="utf-8") as handle:
        for record in keep:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temp.replace(path)
    return True


# ── Reports / apply ────────────────────────────────────────────────


def _source_report(
    key: str,
    policies: dict[str, dict[str, Any]],
    now: datetime,
    include_rollups: bool = True,
) -> dict[str, Any]:
    raw_path, rollup_path = SOURCE_PATHS[key]
    policy = policies[key]
    records = _read_jsonl(raw_path)
    cutoff = now - timedelta(days=policy["days"])
    expired = 0
    newest: str | None = None
    oldest: str | None = None
    for record in records:
        ts = _parse_ts(record)
        if ts is None:
            continue  # corrupt/unparseable rows are never truncated
        iso = record.get("timestamp")
        if not isinstance(iso, str):
            continue  # non-string timestamps are ignored for the range
        if oldest is None or iso < oldest:
            oldest = iso
        if newest is None or iso > newest:
            newest = iso
        if ts < cutoff:
            expired += 1
    rollup_records = len(_read_jsonl(rollup_path)) if include_rollups else 0
    return {
        "key": key,
        "days": policy["days"],
        "rollup": policy["rollup"],
        "path": str(raw_path),
        "raw_records": len(records),
        "expired_records": expired,
        "keep_records": len(records) - expired,
        "oldest": oldest,
        "newest": newest,
        "rollup_records": rollup_records,
        "would_rollup": expired if policy["rollup"] else 0,
    }


def retention_summary(
    policies: dict[str, dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Dry-run report: raw/expired/rollup counts per source.

    Never mutates any file. ``now`` defaults to the current UTC time.
    """
    policies = policies or load_policies()
    now = now or datetime.now(UTC)
    sources = []
    total_raw = total_expired = 0
    for key in DEFAULT_POLICIES:
        if key not in policies:
            continue
        report = _source_report(key, policies, now)
        sources.append(report)
        total_raw += report["raw_records"]
        total_expired += report["expired_records"]
    return {
        "persistence_enabled": True,
        "applied": False,
        "sources": sources,
        "total_raw": total_raw,
        "total_expired": total_expired,
    }


def apply_retention(
    policies: dict[str, dict[str, Any]] | None = None,
    dry_run: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Rollup-then-truncate expired telemetry records (fail-open).

    Args:
        policies: Retention policies (defaults from config).
        dry_run: Preview only — no files are modified.
        now: Clock override for deterministic tests.

    Contract: for every source, expired records are aggregated into the
    source's rollup file **before** the raw log is truncated; if the rollup
    write fails, the raw log is left untouched for that source (raw is never
    truncated before rollup). Rollup skips buckets already present, so apply
    is idempotent.
    """
    policies = policies or load_policies()
    now = now or datetime.now(UTC)
    summary = retention_summary(policies=policies, now=now)
    if dry_run:
        return summary

    results: list[dict[str, Any]] = []
    total_rolled = total_truncated = 0
    for key in DEFAULT_POLICIES:
        if key not in policies:
            continue
        policy = policies[key]
        raw_path, rollup_path = SOURCE_PATHS[key]
        try:
            records = _read_jsonl(raw_path)
            cutoff = now - timedelta(days=policy["days"])
            kept: list[dict[str, Any]] = []
            expired: list[dict[str, Any]] = []
            for record in records:
                ts = _parse_ts(record)
                if ts is not None and ts < cutoff:
                    expired.append(record)
                else:
                    kept.append(record)
            rolled = 0
            truncated = 0
            if expired and policy["rollup"]:
                existing = _existing_rollup_keys(rollup_path)
                for granularity in GRANULARITIES:
                    for row in _aggregate(key, expired, granularity):
                        row_key = (row["timestamp"], row["granularity"], row["key"])
                        if row_key in existing:
                            continue  # idempotent: bucket already rolled up
                        _append_jsonl(rollup_path, [row])  # may raise (OSError)
                        existing.add(row_key)
                        rolled += 1
            if expired:
                # Truncation only after rollup succeeded (or rollup disabled).
                _truncate_keep(raw_path, kept)
                truncated = len(expired)
            total_rolled += rolled
            total_truncated += truncated
            results.append(
                {
                    "key": key,
                    "raw_records": len(records),
                    "expired_records": len(expired),
                    "keep_records": len(kept),
                    "rolled_up": rolled,
                    "truncated": truncated,
                }
            )
        except Exception as exc:  # fail-open: never break the scheduler job
            logger.warning("Retention failed for %s: %s", key, exc)
            results.append(
                {
                    "key": key,
                    "raw_records": 0,
                    "expired_records": 0,
                    "keep_records": 0,
                    "rolled_up": 0,
                    "truncated": 0,
                    "error": str(exc),
                }
            )
    return {
        "persistence_enabled": True,
        "applied": True,
        "sources": results,
        "total_raw": summary["total_raw"],
        "total_expired": summary["total_expired"],
        "total_rolled_up": total_rolled,
        "total_truncated": total_truncated,
    }


# ── Rollup-aware read path ─────────────────────────────────────────


def read_rollups(
    source: str | None = None,
    granularity: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return the last ``limit`` rollup records (optionally filtered)."""
    rows: list[dict[str, Any]] = []
    for key in DEFAULT_POLICIES:
        if source is not None and key != source:
            continue
        _, rollup_path = SOURCE_PATHS[key]
        for record in _read_jsonl(rollup_path):
            if granularity is not None and record.get("granularity") != granularity:
                continue
            rows.append(record)
    if limit <= 0:
        return []
    return rows[-limit:]


def rollup_summary(limit: int = 200) -> dict[str, Any]:
    """Rollup record counts per source/granularity for the retention panel."""
    rows = read_rollups(limit=limit)
    per_source: dict[str, dict[str, Any]] = {}
    for row in rows:
        source = row.get("source") or "unknown"
        granularity = row.get("granularity") or "unknown"
        bucket = per_source.setdefault(
            source,
            {"source": source, "hourly": 0, "daily": 0, "records": 0},
        )
        bucket[granularity] = bucket.get(granularity, 0) + 1
        bucket["records"] += 1
    return {
        "persistence_enabled": True,
        "records": len(rows),
        "per_source": sorted(per_source.values(), key=lambda s: s["source"]),
    }


__all__ = [
    "DEFAULT_POLICIES",
    "GRANULARITIES",
    "SOURCE_PATHS",
    "apply_retention",
    "bucket_key",
    "load_policies",
    "read_rollups",
    "retention_summary",
    "rollup_summary",
    "telemetry_config_path",
]
