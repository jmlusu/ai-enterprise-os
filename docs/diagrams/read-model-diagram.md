# Read Model Diagram (ADR 0004)

The JSONL/JSON files are the **source of truth**; `runtime/dashboard.db` is a
**derived, rebuildable SQLite (WAL) projection** for dashboard reads. Rebuild
trigger: **on startup** — the `initialize_read_model` boot step constructs
`ReadModelEngine`, which drops and re-imports every table. Live sessions stay
current via the watermark-based incremental sync driven by the telemetry
ticker. Because the projection is derived, any rebuild is safe (no data loss).

```mermaid
flowchart TB
    subgraph SRC["Sources of truth (append-only JSONL)"]
        E["events/store.jsonl"]
        M["runtime/metrics_history.jsonl"]
        U["runtime/provider_usage.jsonl"]
    end

    BOOT["config/runtime/startup.yaml — step 9<br/>initialize_read_model (11-step boot)"]
    ENGINE["ReadModelEngine (engine 'read_model')<br/>construct → rebuild · restart() → rebuild<br/>stop() → close connection"]
    STORE["ReadModelStore<br/>sqlite3.connect(check_same_thread=False)<br/>PRAGMA journal_mode=WAL · schema v1"]

    subgraph TBL["runtime/dashboard.db (SQLite WAL)"]
        META["meta<br/>schema_version · rebuilt_at · sync watermarks<br/>(sync_offset_events/metrics/provider_usage) · last_sync_at"]
        TEVENTS["events<br/>event_id PK · timestamp · event_type ·<br/>source · status · payload (indexes on ts/type)"]
        TMETRICS["metrics_history<br/>timestamp · snapshot (index on ts)"]
        TUSAGE["provider_usage<br/>timestamp · provider · model · prompt/completion/<br/>total_tokens · latency_seconds · ok · error<br/>(index on model)"]
    end

    subgraph WRITE["Write paths"]
        REBUILD["rebuild()<br/>DROP + re-import all tables<br/>seed watermarks at EOF<br/>one transaction (rollback keeps prior projection)"]
        SYNC["sync_from_jsonl()<br/>watermark per source → parse bytes since offset<br/>events deduped (INSERT OR IGNORE) · rows + watermarks<br/>commit in one transaction · missing/truncated stream →<br/>full re-import (drop its rows first)"]
    end

    subgraph DRIVE["Sync drivers"]
        TICKER["serve telemetry ticker (30s)<br/>facade.metrics_persist → sync_read_model<br/>single writer"]
        FACADE["RuntimeFacade reads<br/>store-first · JSONL fallback (fail-open)"]
    end

    subgraph READS["Reads (ReadModelEngine passthroughs)"]
        R1["recent_events(limit, event_type)"]
        R2["event_counts_by_type()"]
        R3["metrics_snapshots / metrics_summary(limit)"]
        R4["provider_usage_by_model(limit)"]
        R5["stats() — rows · WAL · rebuilt_at · last_sync_at"]
    end

    subgraph API["API / dashboard"]
        A_EV["/api/events · health · pulse"]
        A_MET["/telemetry KPI + Model Usage panels"]
        A_H["health probe — guards sqlite3.Error<br/>(unhealthy, never crashes)"]
    end

    SRC --> REBUILD
    SRC --> SYNC
    BOOT --> ENGINE
    ENGINE --> REBUILD
    REBUILD --> STORE
    SYNC --> STORE
    STORE --> META
    STORE --> TEVENTS
    STORE --> TMETRICS
    STORE --> TUSAGE
    TICKER --> SYNC
    FACADE --> TICKER
    STORE --> READS
    READS --> API
    FACADE --> API
    API --> A_EV
    API --> A_MET
    API --> A_H
    META --> R5

    classDef src fill:#1a4a6a,stroke:#3498db,stroke-width:2px,color:#fff
    classDef eng fill:#6e2c00,stroke:#e67e22,stroke-width:2px,color:#fff
    classDef db fill:#0e4d45,stroke:#1abc9c,stroke-width:2px,color:#fff
    classDef drive fill:#5b2c6f,stroke:#9b59b6,stroke-width:2px,color:#fff
    classDef read fill:#17202a,stroke:#7f8c8d,stroke-width:2px,color:#fff

    class E,M,U src
    class BOOT,ENGINE,STORE eng
    class META,TEVENTS,TMETRICS,TUSAGE db
    class REBUILD,SYNC drive
    class TICKER,FACADE drive
    class R1,R2,R3,R4,R5 read
    class A_EV,A_MET,A_H read
```

## Contract details

| Concern | Behavior |
|---|---|
| **Rebuild trigger** | On startup (`initialize_read_model` boot step) and on `restart()` (supervisor recovery). `stop()` closes the connection. |
| **Incremental sync** | Watermarks stored in `meta` are byte offsets at the last import; appends are whole lines so the tail decodes cleanly. Events deduped by `event_id`; metrics/provider rows carry no natural key so the watermark guarantees exactly-once import. Rows + watermarks commit in **one transaction** — a crash mid-sync rolls back both (no duplicates). |
| **Truncation/rotation** | A source that is missing, truncated, or never synced triggers a full re-import of that stream (its projection rows are dropped first) — the store always mirrors its source. |
| **WAL mode** | Concurrent dashboard reads while the runtime keeps appending JSONL. |
| **Connection threading** | `check_same_thread=False` — rebuilt on the startup thread, probed from supervisor/health threads, queried from FastAPI worker threads. |
| **Fail-open reads** | `RuntimeFacade` prefers the store but falls back to the JSONL sources when the engine is absent or the store read fails (`persistence_enabled` preserved in the envelope). |
| **Health** | `ReadModelEngine.health()` wraps `store.stats()` in `try/except sqlite3.Error` → `{"status": "unhealthy", "error": "store unavailable: ..."}` (Sprint 5.4 T5 defense-in-depth). |
| **Rebuild safety** | All DDL + inserts run inside one transaction; a failed import rolls back, leaving the previous projection intact. |

## References

- `docs/adr/0004-sqlite-derived-read-model.md` — decision + consequences
- `src/ai_company/readmodel/store.py` — `ReadModelStore`, `_SCHEMA_SQL`,
  `rebuild()`, `sync_from_jsonl()`
- `src/ai_company/readmodel/engine.py` — `ReadModelEngine` + read passthroughs
- `config/runtime/startup.yaml` — step 9 `initialize_read_model`
- `docs/STARTUP_SEQUENCE.md` — boot step tables
