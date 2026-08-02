"""SQLite (WAL) derived read model over the JSONL sources of truth.

Implements ADR 0004: the JSONL/JSON files (``events/store.jsonl``,
``runtime/metrics_history.jsonl``, ``runtime/provider_usage.jsonl``) remain
the source of truth; ``runtime/dashboard.db`` is a **rebuildable projection**
that the dashboard can query without re-parsing JSONL. WAL mode lets the
runtime keep appending JSONL while the projection is read concurrently.

The rebuild trigger is **on startup** (the decided option): the runtime's
``initialize_read_model`` startup step constructs
:class:`~ai_company.readmodel.engine.ReadModelEngine`, which calls
:meth:`ReadModelStore.rebuild` to drop and re-import every table from the
JSONL sources. Because the projection is derived, any rebuild is safe — no
data loss risk (ADR 0004 consequences).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

logger = logging.getLogger(__name__)

DEFAULT_DB_RELATIVE_PATH = Path("runtime") / "dashboard.db"
SCHEMA_VERSION = "1"

# Schema for the derived read model. Tables are dropped and re-imported on
# every rebuild; ``meta`` records when/from-what the projection was built.
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id   TEXT PRIMARY KEY,
    timestamp  TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT '',
    payload    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS metrics_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    snapshot  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_usage (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT NOT NULL,
    provider          TEXT NOT NULL DEFAULT '',
    model             TEXT NOT NULL DEFAULT '',
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    latency_seconds   REAL,
    ok                INTEGER NOT NULL DEFAULT 1,
    error             TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_provider_usage_model ON provider_usage(model);
"""


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file into a list of dicts, skipping corrupt lines."""
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
                    logger.debug("Skipping corrupt JSONL line in %s", path)
    except OSError as exc:
        logger.debug("Read failed for %s: %s", path, exc)
        return []
    return records


class ReadModelStore:
    """A rebuildable SQLite projection for dashboard reads (ADR 0004).

    Args:
        db_path: SQLite database path (WAL mode is enabled on open).
        auto_connect: Open the connection in the constructor. ``False``
            is useful when the caller wants to rebuild in a transaction
            without a lingering handle.
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_RELATIVE_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_schema()

    # ── schema ──────────────────────────────────────────────────────

    def _create_schema(self) -> None:
        self.conn.executescript(_SCHEMA_SQL)

    def _is_wal(self) -> bool:
        row = self.conn.execute("PRAGMA journal_mode").fetchone()
        return bool(row) and str(row[0]).lower() == "wal"

    # ── rebuild (the startup trigger) ───────────────────────────────

    def rebuild(
        self,
        events_path: str | Path = Path("events") / "store.jsonl",
        metrics_path: str | Path = Path("runtime") / "metrics_history.jsonl",
        provider_usage_path: str | Path = Path("runtime") / "provider_usage.jsonl",
    ) -> dict[str, Any]:
        """Drop and re-import every table from the JSONL sources of truth.

        Returns a stats dict (row counts + rebuild timestamp) so callers can
        log or surface the outcome. Runs inside one transaction: a failed
        import rolls back, leaving the previous projection intact.
        """
        events_path_p = Path(events_path)
        metrics_path_p = Path(metrics_path)
        provider_usage_path_p = Path(provider_usage_path)

        event_rows = self._parse_event_records(_read_jsonl(events_path_p))
        metric_rows = [
            (r.get("timestamp", ""), json.dumps(r.get("snapshot", {}), default=str))
            for r in _read_jsonl(metrics_path_p)
        ]
        usage_rows = [
            self._parse_provider_usage(r) for r in _read_jsonl(provider_usage_path_p)
        ]

        rebuilt_at = _utcnow_iso()
        with self.conn:
            self.conn.executescript(
                "DROP TABLE IF EXISTS events;"
                "DROP TABLE IF EXISTS metrics_history;"
                "DROP TABLE IF EXISTS provider_usage;"
                "DROP TABLE IF EXISTS meta;"
            )
            self._create_schema()
            self.conn.executemany(
                "INSERT INTO events "
                "(event_id, timestamp, event_type, source, status, payload) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                event_rows,
            )
            self.conn.executemany(
                "INSERT INTO metrics_history (timestamp, snapshot) VALUES (?, ?)",
                metric_rows,
            )
            self.conn.executemany(
                "INSERT INTO provider_usage "
                "(timestamp, provider, model, prompt_tokens, completion_tokens, "
                "total_tokens, latency_seconds, ok, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                usage_rows,
            )
            self.conn.executemany(
                "INSERT INTO meta (key, value) VALUES (?, ?)",
                [
                    ("schema_version", SCHEMA_VERSION),
                    ("rebuilt_at", rebuilt_at),
                    ("events_path", str(events_path_p)),
                    ("metrics_path", str(metrics_path_p)),
                    ("provider_usage_path", str(provider_usage_path_p)),
                    ("events_count", str(len(event_rows))),
                    ("metrics_count", str(len(metric_rows))),
                    ("provider_usage_count", str(len(usage_rows))),
                ],
            )
        logger.info(
            "Read model rebuilt: %d events, %d metrics, %d usage rows",
            len(event_rows),
            len(metric_rows),
            len(usage_rows),
        )
        return {
            "rebuilt_at": rebuilt_at,
            "events": len(event_rows),
            "metrics_history": len(metric_rows),
            "provider_usage": len(usage_rows),
        }

    @staticmethod
    def _parse_event_records(
        records: list[dict[str, Any]],
    ) -> list[tuple[str, str, str, str, str, str]]:
        """Convert raw event-store records to insertion tuples.

        The event store writes ``event.model_dump(mode="json")`` records
        (plus a ``_type`` discriminator); envelope records are skipped.
        """
        rows: list[tuple[str, str, str, str, str, str]] = []
        for record in records:
            if record.get("_type") == "envelope":
                continue
            metadata = record.get("metadata") or {}
            rows.append(
                (
                    str(metadata.get("event_id") or record.get("event_id") or ""),
                    str(metadata.get("timestamp") or record.get("timestamp") or ""),
                    str(
                        metadata.get("event_type")
                        or record.get("event_type")
                        or "unknown"
                    ),
                    str(metadata.get("source") or record.get("source") or ""),
                    str(metadata.get("status") or record.get("status") or ""),
                    json.dumps(record.get("payload") or {}, default=str),
                )
            )
        return rows

    @staticmethod
    def _parse_provider_usage(
        record: dict[str, Any],
    ) -> tuple[str, str, str, int, int, int, float | None, int, str]:
        usage = record.get("usage") or {}
        prompt = int(usage.get("prompt_tokens", 0) or 0)
        completion = int(usage.get("completion_tokens", 0) or 0)
        total = int(usage.get("total_tokens", 0) or (prompt + completion))
        latency = record.get("latency_seconds")
        return (
            str(record.get("timestamp", "")),
            str(record.get("provider", "")),
            str(record.get("model", "")),
            prompt,
            completion,
            total,
            float(latency) if latency is not None else None,
            1 if record.get("ok", True) else 0,
            str(record.get("error", "")),
        )

    # ── reads ───────────────────────────────────────────────────────

    def recent_events(
        self, limit: int = 100, event_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Return the newest ``limit`` events (newest first), optionally filtered."""
        query = (
            "SELECT event_id, timestamp, event_type, source, status, payload "
            "FROM events"
        )
        params: list[Any] = []
        if event_type:
            query += " WHERE event_type = ?"
            params.append(event_type)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [
            {
                "event_id": r["event_id"],
                "timestamp": r["timestamp"],
                "event_type": r["event_type"],
                "source": r["source"],
                "status": r["status"],
                "payload": json.loads(r["payload"] or "{}"),
            }
            for r in rows
        ]

    def event_counts_by_type(self) -> list[dict[str, Any]]:
        """Return event counts grouped by event type (most frequent first)."""
        rows = self.conn.execute(
            "SELECT event_type, COUNT(*) AS count FROM events "
            "GROUP BY event_type ORDER BY count DESC, event_type"
        ).fetchall()
        return [{"event_type": r["event_type"], "count": r["count"]} for r in rows]

    def metrics_snapshots(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return the last ``limit`` persisted metrics snapshots (oldest first)."""
        rows = self.conn.execute(
            "SELECT timestamp, snapshot FROM metrics_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"timestamp": r["timestamp"], "snapshot": json.loads(r["snapshot"])}
            for r in reversed(rows)
        ]

    def metrics_summary(self, limit: int = 100) -> dict[str, Any]:
        """Dashboard-friendly summary mirroring ``telemetry.metrics.metrics_summary``."""
        records = self.metrics_snapshots(limit=limit)
        if not records:
            return {
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
        return {
            "samples": len(records),
            "latest": latest_record,
            "first_timestamp": records[0].get("timestamp"),
            "last_timestamp": latest_record.get("timestamp"),
            "trend": {
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
            },
        }

    def provider_usage_by_model(self, limit: int = 500) -> dict[str, Any]:
        """Aggregate usage by model, mirroring ``telemetry.provider.provider_usage_summary``."""
        rows = self.conn.execute(
            "SELECT timestamp, provider, model, prompt_tokens, completion_tokens, "
            "total_tokens, latency_seconds, ok, error FROM provider_usage "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            return {
                "records": 0,
                "models": [],
                "totals": {
                    "requests": 0,
                    "successes": 0,
                    "errors": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }
        by_model: dict[str, dict[str, Any]] = {}
        totals: dict[str, Any] = {
            "requests": 0,
            "successes": 0,
            "errors": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        for row in rows:
            model = row["model"] or "(unknown)"
            ok = bool(row["ok"])
            prompt = int(row["prompt_tokens"])
            completion = int(row["completion_tokens"])
            total = int(row["total_tokens"])
            latency = row["latency_seconds"]
            entry = by_model.setdefault(
                model,
                {
                    "model": model,
                    "requests": 0,
                    "successes": 0,
                    "errors": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "latency_sum": 0.0,
                    "latency_count": 0,
                },
            )
            entry["requests"] += 1
            if ok:
                entry["successes"] += 1
            else:
                entry["errors"] += 1
            entry["prompt_tokens"] += prompt
            entry["completion_tokens"] += completion
            entry["total_tokens"] += total
            if latency is not None:
                entry["latency_sum"] += float(latency)
                entry["latency_count"] += 1

            totals["requests"] += 1
            if ok:
                totals["successes"] += 1
            else:
                totals["errors"] += 1
            totals["prompt_tokens"] += prompt
            totals["completion_tokens"] += completion
            totals["total_tokens"] += total

        models = sorted(
            by_model.values(), key=lambda m: m["total_tokens"], reverse=True
        )
        for entry in models:
            entry["avg_latency_seconds"] = (
                round(entry["latency_sum"] / entry["latency_count"], 4)
                if entry["latency_count"]
                else None
            )
            del entry["latency_sum"]
            del entry["latency_count"]
        return {"records": len(rows), "models": models, "totals": totals}

    def meta(self) -> dict[str, str]:
        """Return the projection metadata (schema version, rebuild time, counts)."""
        rows = self.conn.execute("SELECT key, value FROM meta").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def stats(self) -> dict[str, Any]:
        """Return table counts + rebuild metadata for health/observability."""
        meta = self.meta()
        events = self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        metrics = self.conn.execute("SELECT COUNT(*) FROM metrics_history").fetchone()[
            0
        ]
        usage = self.conn.execute("SELECT COUNT(*) FROM provider_usage").fetchone()[0]
        return {
            "db_path": str(self.db_path),
            "wal": self._is_wal(),
            "schema_version": meta.get("schema_version"),
            "rebuilt_at": meta.get("rebuilt_at"),
            "events": events,
            "metrics_history": metrics,
            "provider_usage": usage,
        }

    def close(self) -> None:
        """Close the SQLite connection (no-op when already closed)."""
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


__all__ = [
    "DEFAULT_DB_RELATIVE_PATH",
    "SCHEMA_VERSION",
    "ReadModelStore",
    "read_jsonl",
]


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Public helper: read a JSONL file into a list of dicts (fail-open)."""
    return _read_jsonl(Path(path))
