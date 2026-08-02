# System Architecture

> **Purpose:** High-level architecture of the AI Enterprise OS. Read this
> before touching any subsystem. For the runtime wiring details, see
> `.ai/system-overview.md`.

## Architectural Style

**Layered, engine-oriented monolith with dual command centers.** The system
splits cleanly into two layers (build-time and run-time), each with its own
set of "engines", plus thin adapters (CLI, API, OpenCode) on top (ADR 0003).

```
                        ┌──────────────────────────────────────────┐
   Command Centers      │  CLI (Typer)   Dashboard API (FastAPI)   │
                        │  OpenCode / ai-company generate          │
                        └───────────────┬──────────────────────────┘
                                        │ thin adapters only (ADR 0003)
                        ┌───────────────▼──────────────────────────┐
   Shared Services      │  services/   (RuntimeFacade,             │
                        │               DashboardEventBridge)      │
                        └───────────────┬──────────────────────────┘
                                        │
   ┌────────────────────┴──────────────────────────────┐
   │               BUILD-TIME LAYER                    │
   │  registry/   → parse & validate company YAML      │
   │  validator/  → 5-target gate (YAML, registry,     │
   │                templates, manifest, output)       │
   │  bootstrap/  → scaffold repo structure            │
   │  company/    → generators (org, board, execs,     │
   │                departments, specialists, workflows)│
   │  generator/  → plan/render/write pipeline         │
   │  graph/      → NetworkX org/workflow graphs       │
   └────────────────────┬──────────────────────────────┘
                        │
   ┌────────────────────┴──────────────────────────────┐
   │                RUN-TIME LAYER                     │
   │  runtime/    → kernel: lifecycle, heartbeat,      │
   │                watchdog, supervisor, scheduler,   │
   │                recovery, health, metrics          │
   │  orchestration/ → COO: planner, executor,         │
   │                coordinator, scheduler, checkpoint,│
   │                recovery, rollback, monitoring     │
   │  events/     → pub/sub bus, router, dispatcher,   │
   │                replay, dead-letter, persistence   │
   │  memory/     → 6-type tiered store + search       │
   │  decision/   → approval/risk/policy/routing       │
   │  workflow/   → state machines + transitions       │
   │  audit/      → session, logger, metrics, JSONL    │
   │  backup/     → scheduled backups                  │
   │  providers/  → LLM providers (openai, anthropic,  │
   │                gemini, ollama, mock)              │
   └───────────────────────────────────────────────────┘
```

## Build-Time Layer (stateless)

Triggered per-command by `ai-company bootstrap|build|generate|validate`.
Reads YAML → renders Jinja2 templates → optionally dispatches to OpenCode
subprocess → Validator Engine gates the result.

| Engine | Module | Responsibility |
|---|---|---|
| Registry | `registry/` | Loader (multi-file YAML), parser, resolver (cross-file references), validation. Frozen `CompanyRegistry` result. |
| Validator | `validator/` | 5-target gate: YAML syntax, registry consistency, template syntax, manifest schema, generated output. `ValidatorEngine.validate_all()`. |
| Bootstrap | `bootstrap/` | Scaffolds missing dirs + placeholder files (`README.md.j2`, `doc_placeholder.md.j2`, `prompt_placeholder.md.j2`, `test_placeholder.py.j2`). |
| Company Generators | `company/` | Board, department, executive, specialist, workflow, doc, prompt, organization, hierarchy, relationships, roles, reporting, graph export. |
| Template Engine | `template_engine/` | `TemplateLoader`, `TemplateContext` (dot-path), `Renderer` with format handlers (Jinja2, Python `{key}`, Markdown, JSON, YAML), `Writer`. |
| Generator | `generator/` | Plan/render/write pipeline with dependency resolution. |
| Graph | `graph/` | NetworkX graphs: organization, workflow, projects, dependency, export, visualize. |

## Run-Time Layer (long-lived kernel)

Booted by `ai-company runtime start` through the 11-step declarative startup
sequence (`config/runtime/startup.yaml`). Runs background workers (heartbeat,
watchdog, scheduler, supervisor) until Ctrl-C.

| Engine | Module | Responsibility |
|---|---|---|
| RuntimeEngine (facade) | `runtime/engine.py` | Kernel facade; owns lifecycle, engine registry, state store. |
| RuntimeLifecycle | `runtime/lifecycle.py` | Phase state machine `STARTING → RUNNING ↔ DEGRADED → STOPPING → STOPPED`. |
| Startup/Shutdown | `runtime/startup.py`, `runtime/shutdown.py` | Declarative 11-step boot / 6-step stop. |
| Heartbeat + Watchdog | `runtime/heartbeat.py`, `runtime/watchdog.py` | 5s heartbeats; stale-detection. |
| Health + Metrics | `runtime/health.py`, `runtime/metrics.py` | Health reporting; `runtime.metrics` snapshot. |
| Supervisor + Recovery | `runtime/supervisor.py`, `runtime/recovery.py` | Per-engine restart → isolate (ADR 0007). |
| JobScheduler | `runtime/scheduler.py` | Cron/interval job dispatch. |
| CircuitBreaker | `runtime/circuit_breaker.py` | Failure thresholding for engine calls. |
| ProcessManager | `runtime/process_manager.py` | Managed external processes. |
| OrchestrationEngine | `orchestration/engine.py` | COO: plan → run → checkpoint → recover → record. |
| Coordinator | `orchestration/coordinator.py` | Holds all engine refs; dispatches by `task_type`. |
| EventBus | `events/bus.py` | Pub/sub with middleware, priority queue, router, dispatcher (thread pool), history, replay, JSONL persistence, dead-letter. |
| MemoryEngine | `memory/engine.py` | 6-type store, tiering (working/short/long/archive), search, snapshots, knowledge. |
| DecisionEngine | `decision/engine.py` | Approval matrix, risk matrix, policy, routing. |
| WorkflowManager | `workflow/` + `orchestrator/workflow.py` | State machines, transitions, loaders, validators. |
| Audit | `audit/` | Session tracking, JSONL log, metrics. |
| Backup | `backup/` | Scheduled backup of state. |

## Shared Services Layer (ADR 0003)

Business logic lives exactly once; surfaces are thin adapters.

| Surface | Adapter | Notes |
|---|---|---|
| CLI | `cli/` (Typer) | Frozen command tree; command map integrity checked in CI (ADR 0006). |
| Dashboard API | `api/app.py` | FastAPI + WebSocket; loopback-only; security headers; `run_in_threadpool` bridge (ADR 0002, 0009). |
| Runtime bridge | `services/runtime_facade.py` | `RuntimeFacade` — stable JSON-ready surface over `RuntimeEngine`. |
| Event bridge | `services/dashboard_events.py` | `DashboardEventBridge` — EventBus subscriber → per-WebSocket asyncio queue. |
| OpenCode | `prompts/opencode/*.md` + `generate` CLI | Dispatches phases to OpenCode subprocess. |

## Design Patterns

| Pattern | Where | Why |
|---|---|---|
| **Facade** | `RuntimeFacade`, `RuntimeEngine` | Stabilize one API over a complex subsystem. |
| **Strategy** | `template_engine/handlers/`, `providers/` | Pluggable format handlers / LLM providers. |
| **Registry** | `registry/`, `events/registry.py`, `providers/registry.py` | Single source of truth lookups. |
| **Observer / Pub-Sub** | `events/bus.py` | Decoupled event flow; replay + DLQ. |
| **State Machine** | `runtime/lifecycle.py`, `workflow/state_machine.py` | Enforced phase transitions. |
| **Coordinator** | `orchestration/coordinator.py` | Central dispatch by `task_type`; engines never call each other. |
| **Declarative Config** | `config/**/*.yaml` | Pipelines, schedules, startup steps, policies live in YAML. |
| **Recovery / Retry** | `runtime/recovery.py`, `orchestration/recovery.py` | Self-healing before isolation. |
| **Frozen Models** | `models/company.py` | Immutable registry via Pydantic `frozen=True`. |

## Data Flow (primary paths)

### 1. Company generation
```
company/*.yaml ──► RegistryEngine.load() ──► frozen CompanyRegistry
      ──► generators ──► generated/ (314 artifacts)
      ──► ValidatorEngine.validate_all() ──► report (gate)
```

### 2. Runtime boot
```
ai-company runtime start
  ──► StartupExecutor.run(config/runtime/startup.yaml)
      11 steps: constitution → state → config → memory → event_bus
               → decision → workflow → orchestration → read model → start workers → ready
  ──► main_loop() (1s refresh) with background workers
```

### 3. Orchestration
```
ai-company orchestrate start <pipeline>
  ──► OrchestrationEngine.plan() ──► OrchestrationPlan
  ──► run(plan): stages (sequential/parallel/conditional) → tasks
  ──► Coordinator.execute(task) → handler by task_type
  ──► CheckpointManager.snapshot() → StateStore → ExecutionRecord
  ──► on failure: RecoveryManager (max_recovery_attempts) → retry
```

### 4. Event flow
```
Publisher.publish(event)
  ──► MiddlewarePipeline (logging, validation, metrics)
  ──► PriorityProcessor ──► Router ──► Dispatcher (thread pool, 4 workers)
  ──► subscribers; failures → DeadLetterQueue
  ──► EventHistory + EventPersistence (JSONL)
  replay: bus.replay(ReplayRequest(since, limit), handler)
```

### 5. Dashboard API (committed, Phase 1 wave 1)
```
ai-company serve → uvicorn on 127.0.0.1:8000
  REST: GET /api/health|status|metrics|engines|events
  WS:   /api/ws?since=<iso> → replay + live push
  Bridge: run_in_threadpool(RuntimeFacade methods)
          DashboardEventBridge → asyncio.Queue → WebSocket
```

## Key Invariants

1. **Registry is frozen** — `CompanyRegistry` `ConfigDict(frozen=True)`.
2. **Config is declarative** — no hardcoded pipeline/schedule/recovery logic.
3. **Engines never call each other** — Coordinator dispatches by `task_type`.
4. **Generated output is ephemeral** — `generated/`, `memory/`, `runtime/`,
   `events/`, `reports/`, `dashboards/` are gitignored.
5. **CLI is fail-open** — telemetry/event persistence failures never break the
   user command.
6. **Supervisor restarts before isolating** (ADR 0007).
7. **Loopback-only dashboard** — Host-header allowlist; non-loopback requires
   the Phase 2 write-auth scheme (ADR 0009, 0010 — **shipped Wave 2a
   2026-08-01**: bearer token + CSRF + `audit.write`, fail-closed non-loopback,
   optional `--require-loopback-token`).

## Cross-Cutting Concerns

| Concern | Mechanism |
|---|---|
| Typing | mypy `--strict` (selective error-code disables documented in `pyproject.toml`). |
| Linting/Format | ruff; 14 intentional ignores with rationale. |
| Validation | Pydantic v2 everywhere; ValidatorEngine as build gate. |
| Security | Loopback-only API, security headers, `detect-private-key` hook, `uv audit`. |
| CI | `.github/workflows/ci.yml` — lint, mypy, tests (Windows matrix), integrity gate, `uv audit`. |
| State | `.ai-company/state/current_sprint.yaml` — read first, update last (constitution). |
| Knowledge | `.ai/` — this directory: single source of truth for agents. |
