"""Read model engine — registers the SQLite derived read model on the runtime.

ADR 0004 (Accepted): the JSONL/JSON files are the source of truth; SQLite is a
rebuildable read projection for dashboard queries. The rebuild trigger was an
open decision (startup? watcher? CLI?) — **resolved: on startup**.

This engine is wired into ``config/runtime/startup.yaml`` as the
``initialize_read_model`` class step. Constructing it (which is exactly what
the startup sequence does) triggers a full rebuild of ``runtime/dashboard.db``
from the JSONL sources, so the projection is always fresh when the runtime
reaches RUNNING. ``restart()`` (supervisor recovery) also re-runs the rebuild;
``stop()`` closes the connection.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

from ai_company.readmodel.store import (
    DEFAULT_DB_RELATIVE_PATH,
    ReadModelStore,
)

__all__ = ["ReadModelEngine"]


def _default_events_path() -> Path:
    return Path("events") / "store.jsonl"


def _default_metrics_path() -> Path:
    return Path("runtime") / "metrics_history.jsonl"


def _default_provider_usage_path() -> Path:
    return Path("runtime") / "provider_usage.jsonl"


class ReadModelEngine(BaseModel):
    """Runtime engine exposing the SQLite derived read model (ADR 0004).

    Registered as the ``read_model`` engine by the startup sequence. The
    rebuild trigger is **on startup**: constructing the engine rebuilds the
    projection from the JSONL sources of truth.

    Args:
        db_path: SQLite database path. When it points at a directory (e.g.
            the runtime ``state_dir`` via the ``@state_dir`` startup marker),
            ``dashboard.db`` is appended.
        events_path: JSONL source for events (``events/store.jsonl``).
        metrics_path: JSONL source for runtime metrics snapshots.
        provider_usage_path: JSONL source for provider usage records.
    """

    db_path: Path = Field(default_factory=lambda: DEFAULT_DB_RELATIVE_PATH)
    events_path: Path = Field(default_factory=_default_events_path)
    metrics_path: Path = Field(default_factory=_default_metrics_path)
    provider_usage_path: Path = Field(default_factory=_default_provider_usage_path)

    _store: ReadModelStore | None = PrivateAttr(default=None)

    def model_post_init(self, __context: Any, /) -> None:
        if not self.db_path.suffix:
            # ``db_path`` is a directory (e.g. the runtime state_dir).
            self.db_path = self.db_path / "dashboard.db"
        self.rebuild()

    # ── lifecycle ───────────────────────────────────────────────────

    def rebuild(self) -> dict[str, Any]:
        """Rebuild the projection from the JSONL sources of truth."""
        store = ReadModelStore(db_path=self.db_path)
        store.rebuild(
            events_path=self.events_path,
            metrics_path=self.metrics_path,
            provider_usage_path=self.provider_usage_path,
        )
        self._store = store
        return store.stats()

    def start(self) -> None:
        """Ensure the store is open (no-op after construction-time rebuild)."""
        if self._store is None:
            self.rebuild()

    def stop(self) -> None:
        """Close the SQLite connection."""
        if self._store is not None:
            self._store.close()
            self._store = None

    def restart(self) -> None:
        """Rebuild the projection (used by the supervisor recovery factory)."""
        self.rebuild()

    def sync(self) -> dict[str, Any]:
        """Incrementally import JSONL rows appended since the last sync.

        The live-session companion to the startup rebuild: the dashboard
        telemetry ticker calls this on a cadence so reads are served from a
        projection that stays current without a full rebuild (ADR 0004).
        """
        store = self._store
        if store is None:
            return {"synced": False, "error": "read model store not open"}
        return store.sync_from_jsonl(
            events_path=self.events_path,
            metrics_path=self.metrics_path,
            provider_usage_path=self.provider_usage_path,
        )

    def health(self) -> dict[str, Any]:
        """Return a health probe result for the runtime HealthMonitor."""
        store = self._store
        if store is None:
            return {"status": "unhealthy", "error": "read model store not open"}
        try:
            stats = store.stats()
            rows = stats["events"] + stats["metrics_history"] + stats["provider_usage"]
            return {
                "status": "healthy",
                "schema_version": stats["schema_version"],
                "rebuilt_at": stats["rebuilt_at"],
                "rows": rows,
                "wal": stats["wal"],
            }
        except sqlite3.Error as exc:
            return {"status": "unhealthy", "error": f"store unavailable: {exc}"}

    # ── read passthroughs (ADR 0004 projection queries) ─────────────

    def recent_events(
        self, limit: int = 100, event_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Return the newest ``limit`` events (newest first), optionally filtered."""
        return self._require_store().recent_events(limit=limit, event_type=event_type)

    def event_counts_by_type(self) -> list[dict[str, Any]]:
        """Return event counts grouped by event type."""
        return self._require_store().event_counts_by_type()

    def metrics_summary(self, limit: int = 100) -> dict[str, Any]:
        """Return the dashboard-friendly metrics summary."""
        return self._require_store().metrics_summary(limit=limit)

    def provider_usage_by_model(self, limit: int = 500) -> dict[str, Any]:
        """Return provider usage aggregated by model."""
        return self._require_store().provider_usage_by_model(limit=limit)

    def stats(self) -> dict[str, Any]:
        """Return projection stats (row counts, WAL, rebuild time)."""
        return self._require_store().stats()

    def _require_store(self) -> ReadModelStore:
        if self._store is None:
            raise RuntimeError("Read model store is not open — runtime not started")
        return self._store
