# Dual Command-Center Architecture Diagram

Target operating model (from `docs/dashboard/initiative.md` §1, §3):
**OpenCode desktop = the workshop; Dashboard = the boardroom + NOC;
CLI = the API-compatible shell underneath both.** All three are thin adapters
over the shared `services/` layer (ADR 0003) — business logic lives exactly once.

```mermaid
flowchart TB
    subgraph SURFACES["Operator Surfaces (thin adapters — ADR 0003)"]
        OC["OpenCode desktop<br/>workshop: delegate + author<br/>session bridge (P1) · telemetry-on-close (P2)<br/>action telemetry = D5 numerator (P5)"]
        WEB["GUI Dashboard (browser)<br/>boardroom + NOC: see + decide<br/>Jinja2 + htmx v1 (Svelte 5 in Phase 4)"]
        CLI["CLI (Typer)<br/>automation / power-user shell<br/>frozen command tree (ADR 0006)<br/>subprocess: ai-company generate"]
    end

    subgraph CORE["ai-company serve — in-process core (127.0.0.1)"]
        API["FastAPI + uvicorn (no uvloop)<br/>api/ routers — thin adapters only<br/>REST + WebSocket · write guard (ADR 0010)<br/>~19 read + ~20+ guarded write endpoints"]
        SVC["services/ — THE single source of truth<br/>RuntimeFacade · StatusService · DeepLinks<br/>GenerateRunner + GenerateDispatch<br/>DashboardEventBridge (shared by CLI + API)"]
        ENGINES["RuntimeEngine + EventBus (in-process)<br/>engines untouched (ADR 0005)"]
        TELE["SQLite (WAL) telemetry store<br/>runtime/dashboard.db — derived from<br/>JSONL source of truth (ADR 0004)"]
    end

    subgraph EXT["External / Out-of-process"]
        OCAPP["opencode:// desktop app"]
    end

    %% Surfaces → core
    WEB <-->|"REST + WS (loopback)"| API
    API --> SVC
    CLI --> SVC
    SVC --> ENGINES
    SVC --> TELE
    ENGINES --> TELE

    %% OpenCode desktop flows
    OC -->|"HTTP (loopback): session telemetry, review submit"| API
    OC -->|"opencode://new-session deep link (P3)"| OCAPP
    WEB -.->|"Continue in OpenCode (P3)"| OCAPP
    API -.->|"review_link → /decisions?focus= (P4)"| WEB
    SVC -->|"opencode subprocess dispatch"| OCAPP

    classDef surf fill:#4a235a,stroke:#9b59b6,stroke-width:2px,color:#fff
    classDef core fill:#6e2c00,stroke:#e67e22,stroke-width:2px,color:#fff
    classDef svc fill:#6e2c00,stroke:#e67e22,stroke-width:2px,color:#fff
    classDef ext fill:#17202a,stroke:#7f8c8d,stroke-width:2px,color:#fff

    class OC,WEB,CLI surf
    class API,SVC,ENGINES,TELE core
    class OCAPP ext
```

## Reading guide

| Element | Meaning |
|---|---|
| 🟣 **Surfaces** | The three operator surfaces. CLI is frozen (ADR 0006); every new feature back-ports a CLI command. |
| 🟠 **Core** | The `ai-company serve` process: FastAPI is a transport adapter; all business logic is in `services/` (ADR 0003) over the existing engines (ADR 0005). |
| Solid lines | In-process / HTTP loopback calls between the core and its surfaces. |
| Dashed lines | Deep links / out-of-process desktop dispatch (`opencode://` scheme, HTTP to the loopback API). |

## Anti-drift guarantees

1. **Services layer is the single surface** (ADR 0003) — CLI, API, and desktop
   contain no business logic; parity matrix `docs/dashboard/parity-matrix-v0.md`
   tracks which service each surface exposes.
2. **CLI is frozen** (ADR 0006) — `integrity/check_cli_surface.py` gates
   removal/rename in CI; the command map is an enforced contract.
3. **Engines stay untouched** (ADR 0005) — all new behaviour lands in
   `services/`, never in the kernel.
4. **Write auth** (ADR 0010) — every mutation from any surface flows through
   the shared `WriteGuard` (see `write-auth-flow-diagram.md`).
5. **R3 parity rule** — every new read/write surface ships its golden parity
   test (CLI output == API JSON) in the same change.
