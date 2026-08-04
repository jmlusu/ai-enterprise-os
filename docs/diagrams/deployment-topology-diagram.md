# Deployment Topology

Single-machine deployment. The runtime kernel boots **in-process** on the
dashboard API server (loopback-only, ADR 0002); the CLI is the same wheel; the
OpenCode desktop session is a separate process that talks to the dashboard over
`http://127.0.0.1:8000`. Artifacts are files under the repo root
(`runtime/`, `events/`, `memory/`, `generated/`). CI runs quality gates on
ubuntu + windows (Windows-first project, risk R10).

```mermaid
flowchart TB
    subgraph MACHINE["Single machine (localhost)"]
        subgraph APPS["Operator surfaces"]
            CLI["CLI: ai-company (Typer)<br/>uv-run from .venv"]
            DASH["Dashboard server: ai-company serve<br/>uvicorn · 127.0.0.1:8000 (loopback-only)<br/>security headers · scoped CSP · WS /api/ws"]
            DESK["OpenCode desktop session<br/>opencode:// deep links · .opencode/ plugins<br/>submit-for-review → POST /api/review/submit"]
        end

        subgraph KERNEL["Runtime kernel (in-process)"]
            RUNTIME["RuntimeEngine (phase machine)<br/>11-step boot · supervisor · health watchdog"]
            BUS["EventBus + read model<br/>(SQLite WAL dashboard.db)"]
            ENGINES["RegistryEngine · MemoryEngine ·<br/>OrchestrationEngine · DecisionEngine<br/>ValidatorEngine · GenerateRunner"]
            CONFIG["config/runtime/*.yaml<br/>startup · scheduler · model_fallback · telemetry"]
        end

        subgraph STORE["State & artifacts (files)"]
            JSONL["events/store.jsonl · dead_letter.jsonl<br/>runtime/audit.jsonl · alerts.jsonl ·<br/>cli/session/action_telemetry.jsonl ·<br/>metrics_history.jsonl · decisions.jsonl ·<br/>generate_runs.jsonl · generate_logs/"]
            SQLITE["runtime/dashboard.db (SQLite WAL)<br/>derived read model — rebuildable (ADR 0004)"]
            MEM["memory/store.jsonl (long/short-term)"]
            GEN["generated/ artifacts"]
        end

        OLLAMA["ollama serve (local models)<br/>ollama/llama3.1:8b — fallback (D9)"]
        OPENCODE_BIN["opencode binary on PATH<br/>primary generate provider (ADR 0006)"]
    end

    subgraph CI["CI / CD (GitHub Actions)"]
        LINT["lint (ubuntu + windows)<br/>ruff · format · uv audit ·<br/>command-map + CLI-surface gates"]
        TYPE["type-check (ubuntu + windows)<br/>mypy --strict"]
        TEST["test (ubuntu) + test-windows<br/>pytest full suite"]
        VALIDATE["validate<br/>ai-company build → validate"]
        BUILD["build (main push)<br/>uv build → dist/ artifact"]
        BACKUP["nightly-backup (cron 02:00 UTC)<br/>python -m ai_company.backup → backups/"]
        RELEASE["release (v* tag)<br/>uv build → PyPI + GitHub Release"]
    end

    CLI --> RUNTIME
    CLI --> OPENCODE_BIN
    DASH --> RUNTIME
    DESK -- "http://127.0.0.1:8000" --> DASH
    DASH --> KERNEL
    RUNTIME --> CONFIG
    RUNTIME --> ENGINES
    RUNTIME --> BUS
    ENGINES --> OLLAMA
    ENGINES --> OPENCODE_BIN
    BUS --> JSONL
    BUS --> SQLITE
    ENGINES --> MEM
    ENGINES --> GEN

    MACHINE -- "push/pull-request to main" --> LINT
    LINT --> TYPE
    TYPE --> TEST
    TEST --> VALIDATE
    VALIDATE --> BUILD
    MACHINE -. "scheduled backup" .-> BACKUP
    MACHINE -. "tag v*" .-> RELEASE

    classDef app fill:#17202a,stroke:#7f8c8d,stroke-width:2px,color:#fff
    classDef kernel fill:#1a4a6a,stroke:#3498db,stroke-width:2px,color:#fff
    classDef store fill:#0e4d45,stroke:#1abc9c,stroke-width:2px,color:#fff
    classDef ext fill:#5b2c6f,stroke:#9b59b6,stroke-width:2px,color:#fff
    classDef ci fill:#6e2c00,stroke:#e67e22,stroke-width:2px,color:#fff

    class CLI,DASH,DESK app
    class RUNTIME,BUS,ENGINES,CONFIG kernel
    class JSONL,SQLITE,MEM,GEN store
    class OLLAMA,OPENCODE_BIN ext
    class LINT,TYPE,TEST,VALIDATE,BUILD,BACKUP,RELEASE ci
```

## What runs where

| Process | Runtime | Bind / surface | Notes |
|---|---|---|---|
| Dashboard API (`ai-company serve`) | `uvicorn` (no uvloop — Windows-safe, ADR 0002) | `127.0.0.1:8000` | Host-guard rejects non-loopback (R9); scoped CSP; WS `/api/ws` |
| Runtime kernel | In-process threads | — | `RuntimeEngine` phase machine; engines + workers run inside the server |
| CLI (`ai-company`) | Typer app | stdio | Frozen surface (ADR 0006); thin adapter over `services/` (ADR 0003) |
| OpenCode desktop | External process | `opencode://` scheme + HTTP loopback | Deep links both directions (P3/P4); session telemetry plugin |
| `ollama` | External process | local | Fallback provider for generate dispatch (R4/D9); optional |
| `opencode` binary | External process | `PATH` | Primary generate provider (frozen CLI contract) |

## Data flow & durability

- JSONL/JSON files are the **source of truth**; `runtime/dashboard.db` is a
  derived, rebuildable SQLite (WAL) projection (ADR 0004) — safe to delete.
- Every write path is append-only and fail-open; read surfaces prefer the read
  model and fall back to JSONL.
- Single-machine by design (`.ai-company/` machine-local, gitignored; no
  distributed agents). CI artifacts are the only cloud-resident copies.

## CI gates (ADR 0006 / R8 / R10)

- **Windows-first:** lint + type-check + full test suite run on both
  `ubuntu-latest` and `windows-latest` (fail-fast disabled).
- **Frozen CLI:** `integrity/check_command_map` and `integrity/check_cli_surface`
  fail on any removal/rename/signature change (additive drift accepted with
  `--update` and committed).
- **Quality bar:** full pytest suite, ruff, mypy `--strict`, format check,
  `uv audit`, lockfile check must all be green before `build` runs on main.

## References

- `.github/workflows/ci.yml` — lint/type-check/test/test-windows/validate/build
- `.github/workflows/nightly-backup.yml` — scheduled backup bundle
- `.github/workflows/release.yml` — tagged PyPI + GitHub Release
- `src/ai_company/api/app.py` — `create_app`, loopback host guard, CSP
- `src/ai_company/runtime/` — `RuntimeEngine`, boot/shutdown, supervisor
- `src/ai_company/services/runtime_facade.py` — shared surface wiring (ADR 0003)
- `pyproject.toml` — Python 3.12-only, `hatchling` wheel, `uv` deps
