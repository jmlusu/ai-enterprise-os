"""SQLite (WAL) derived read model — ADR 0004.

A rebuildable projection over the JSONL sources of truth
(``events/store.jsonl``, ``runtime/metrics_history.jsonl``,
``runtime/provider_usage.jsonl``) stored in ``runtime/dashboard.db``. The
rebuild trigger is **on startup**: the runtime's ``initialize_read_model``
startup step constructs :class:`~ai_company.readmodel.engine.ReadModelEngine`,
which rebuilds the projection before the runtime reaches RUNNING.

Public API:
- :class:`ai_company.readmodel.store.ReadModelStore` — the SQLite store
  (schema, rebuild, reads)
- :class:`ai_company.readmodel.engine.ReadModelEngine` — the runtime engine
  registered as ``read_model`` on startup
"""

from ai_company.readmodel.engine import ReadModelEngine
from ai_company.readmodel.store import (
    DEFAULT_DB_RELATIVE_PATH,
    SCHEMA_VERSION,
    ReadModelStore,
    read_jsonl,
)

__all__ = [
    "DEFAULT_DB_RELATIVE_PATH",
    "SCHEMA_VERSION",
    "ReadModelEngine",
    "ReadModelStore",
    "read_jsonl",
]
