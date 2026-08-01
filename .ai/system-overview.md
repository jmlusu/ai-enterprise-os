# System Overview

> **Purpose:** A high-level map of how the AI Enterprise OS works as a running
> system — the dual engine layers (runtime kernel + orchestration COO), the
> build-time pipeline, and how everything connects at runtime.

## Dual Engine Architecture

The system has two distinct "engine layers" that are easy to confuse:

```
                    ┌─────────────────────────────────────┐
                    │     Build-Time Engines              │
                    │  (CLI-driven, synchronous)          │
                    │                                     │
                    │  Registry → Bootstrap → Generator  │
                    │    → Validator → Graph             │
                    │                                     │
                    └──────────────┬──────────────────────┘
                                   │
                                   │ generates
                                   ▼
                    ┌─────────────────────────────────────┐
                    │     Run-Time Engines                │
                    │  (Runtime kernel — long-lived)      │
                    │                                     │
                    │  RuntimeEngine (kernel/facade)      │
                    │    ├── RuntimeLifecycle             │
                    │    ├── RuntimeConfiguration         │
                    │    ├── RuntimeStateStore            │
                    │    ├── JobScheduler                 │
                    │    ├── HeartbeatManager + Watchdog  │
                    │    ├── HealthMonitor + Metrics      │
                    │    ├── Supervisor + RecoveryManager │
                    │    └── StartupExecutor/ShutdownExec │
                    │                                     │
                    │  EventBus | Memory | Decision |     │
                    │  Workflow | Orchestration (COO) |   │
                    │  Audit | Graph                      │
                    └─────────────────────────────────────┘
```

### Build-Time

Triggered by `ai-company bootstrap` / `ai-company build` /
`ai-company generate <target>`. Reads YAML, renders templates
(Jinja2), optionally dispatches to OpenCode subprocess, then runs
the Validator Engine as a gate. Stateless — each invocation is fresh.

### Run-Time

Triggered by `ai-company runtime start`. Boots the kernel through a
**10-step declarative startup sequence** (`config/runtime/startup.yaml`),
then blocks in `main_loop()` until Ctrl-C. Background workers (heartbeat,
watchdog, scheduler, supervisor) keep engines alive and self-healing.

## Runtime Lifecycle

```
STARTING ──────────────────────────────────────
  │  1. load_constitution (config/company/*.yaml)
  │  2. load_project_state (runtime/runtime_state.json)
  │  3. load_configuration_registry (config/runtime/*.yaml)
  │  4. initialize_memory (MemoryEngine → registered as "memory")
  │  5. initialize_event_bus (EventBus → registered as "event_bus")
  │  6. initialize_decision_engine (DecisionEngine → "decision")
  │  7. initialize_workflow_engine (WorkflowManager → "workflow")
  │  8. initialize_orchestrator (OrchestrationEngine → "orchestration")
  │  9. start_runtime (start workers: event bus, scheduler, watchdog, supervisor, config jobs)
  │ 10. ready (mark RUNNING, publish runtime.started)
  ▼
RUNNING ───────────────────────────────────────
  │  main_loop: refresh metrics every loop_interval_seconds (1.0s)
  │  background workers: heartbeat (5s), watchdog (stale detection),
  │  scheduler (5s poll), supervisor (failure→restart→isolate)
  │  hot config reload: ai-company runtime reload
  ▼
STOPPING ────────────────────────────────────── (Ctrl-C or stop command)
  │  1. Stop scheduler (stop dispatching jobs)
  │  2. Stop watchdog (stop deadline enforcement)
  │  3. Stop supervisor (stop recovery loop)
  │  4. Stop registered engines / managed processes
  │  5. Persist final state → runtime/runtime_state.json
  │  6. Finalize (mark STOPPED, publish runtime.stopped)
  ▼
STOPPED  (or FAILED if a step raised)
```

**Phase state machine:** `STARTING → RUNNING ↔ DEGRADED → STOPPING → STOPPED`
(failure transitions: `STARTING → FAILED`, `RUNNING → DEGRADED`,
`DEGRADED → STOPPING`). Enforced by `RuntimeLifecycle` in
`runtime/lifecycle.py`.

## Engine Registry at Runtime

The RuntimeEngine maintains an engine registry (name → instance). Engines are
registered during startup and supervised by the Supervisor:

| Engine Name | Class | Module | Purpose |
|---|---|---|---|
| `memory` | `MemoryEngine` | `ai_company.memory.engine` | 6-type store, search, archive, snapshots |
| `event_bus` | `EventBus` | `ai_company.events.bus` | Pub/sub, routing, DLQ, replay |
| `decision` | `DecisionEngine` | `ai_company.decision.engine` | Approval, risk, policy, routing |
| `workflow` | `WorkflowManager` | `ai_company.orchestrator.workflow` | Workflow state machines |
| `orchestration` | `OrchestrationEngine` | `ai_company.orchestration.engine` | Pipeline planning → execution |

The **OrchestrationEngine** (COO) further wires a `Coordinator` that holds
references to all engines and dispatches pipeline tasks by `task_type`.

## Build-Time Pipeline (one command)

```
ai-company bootstrap
  │
  ├─ 1. BootstrapGenerator        ← config/company/company.yaml
  │     ├─ Create missing dirs (generated/, reports/, etc.)
  │     ├─ Render README.md.j2 → generated/README.md
  │     ├─ Render per-department READMEs
  │     ├─ Render doc placeholders
  │     ├─ Render prompt placeholders
  │     └─ Render test placeholders
  │
  ├─ 2. CompanyGenerator          ← company/*.yaml → CompanyRegistry
  │     ├─ generate_organization() → generated/organization.json + graph
  │     ├─ generate_board()      → generated/board.* + docs/BOARD*.md
  │     ├─ generate_executives() → generated/executives/*/
  │     ├─ generate_departments() → generated/departments/*/README.md
  │     ├─ generate_specialists() → generated/specialists/*/profile.md
  │     ├─ generate_workflows()  → generated/workflows/*/workflow.md
  │     ├─ generate_prompts()    → generated/prompts/
  │     ├─ generate_docs()       → generated/docs/
  │     └─ generate_graph_export() → generated/graph/
  │
  ├─ 3. ValidatorEngine           ← 5-target gate
  │     ├─ validate_yaml()         ← company/*.yaml syntax + existence + non-empty
  │     ├─ validate_registry()     ← cross-file consistency, department resolution
  │     ├─ validate_templates()    ← Jinja2 syntax, required templates present
  │     ├─ validate_manifest()     ← company.yaml: non-empty name, unique depts
  │     └─ validate_output()       ← generated/: files exist, non-empty, no {{ unresolved }}
  │
  └─ 4. CLI telemetry (JSONL)     ← runtime/cli_telemetry.jsonl (fail-open)
```

## Orchestration Pipeline Flow

When `ai-company orchestrate start <pipeline>` runs:

```
OrchestrationEngine.plan(name)
  → PipelinePlanner.get_pipeline(name)  ← config/orchestration/engine.yaml
  → PipelinePlanner.plan_from_pipeline()
  → OrchestrationPlan (id, pipeline, schedule_mode, ...)

OrchestrationEngine.start(plan)
  ├── If IMMEDIATE → run(plan) synchronously
  │     ├── PipelineRunner.run(plan)
  │     │     ├── For each stage in order:
  │     │     │   ├── sequential  → run tasks one-by-one
  │     │     │   ├── parallel    → ThreadPoolExecutor (max_workers)
  │     │     │   ├── conditional → run only if condition evaluates true
  │     │     │   └── For each task → TaskExecutor.execute()
  │     │     │         └── Coordinator.execute(task) → handler(task_type)
  │     │     └── CheckpointManager.snapshot() after task/stage (if configured)
  │     └── If FAILED + auto_recover → RecoveryManager.recover() → retry
  │           (up to max_recovery_attempts)
  │     └── StateStore.save_state(state) + record(ExecutionRecord)
  └── If SCHEDULED/RECURRING/DEPENDENCY → OrchestrationScheduler.register(plan)
        → background worker polls due_plans() every worker_interval_seconds
```

**Built-in pipelines:** `bootstrap` (registry→generation→validation→persistence/audit), `generation` (registry→parallel prompts/docs/graph→persistence/audit), `report` (registry→graph_build→report→audit).

## Event Bus Flow

```
Publisher.publish(event)
  1. MiddlewarePipeline.execute(event)
     ├── LoggingMiddleware  ← logs event
     ├── ValidationMiddleware ← validates structure
     └── MetricsMiddleware  ← records publish count
  2. PriorityProcessor.enqueue(event)  ← priority-ordered queue
  3. Router.route_event(event) → matching Subscribers
  4. Dispatcher.dispatch(event, subscribers)
     ├── ThreadPoolExecutor (max_workers=4)
     ├── Per-subscriber result recorded
     └── Failed deliveries → DeadLetterQueue
  5. EventHistory.record_publish(event)
  6. EventPersistence.persist(event)  ← events/store.jsonl
```

**Replay:** `bus.replay(ReplayRequest(since, limit), handler)` iterates the
JSONL store from the given timestamp, calling the handler for each event.
The dashboard WebSocket uses this for reconnect — clients send `?since=<iso>`
and get a replay + live stream.

## Memory Engine — Tiered Storage

```
Working Memory (InMemoryStore, max 100 entries)
    │
    ▼
Short-Term (events/short_term/store.jsonl)
    │
    ▼
Long-Term (memory/long_term/store.jsonl)
    │
    ▼
Archived (memory/long_term/archive/ — orphans of the above)
```

- **Save** writes to working + short_term stores.
- **Tier management** (triggered by scheduler job): working → long_term
  (importance ≥ 0.7), long_term → archived (importance < 0.05 or expired).
- **Snapshots** capture point-in-time state for rollback.
- **Knowledge base** (`memory/knowledge.json`) derives extracted knowledge
  from memory entries.
- **Retention policy** auto-archives/purges per config.

## API Layer (Dashboard v1 — COMMITTED, Phase 1 wave 1)

```
ai-company serve  ← 127.0.0.1:8000  (committed b6d5a26)
  │
  ├── RuntimeFacade (services/runtime_facade.py)
  │     └── wraps RuntimeEngine + EventBus via threadpool (async↔sync bridge)
  │
  ├── DashboardEventBridge (services/dashboard_events.py)
  │     └── EventBus subscriber → asyncio.Queue per WebSocket client
  │
  └── FastAPI app (api/app.py)
        ├── REST: GET /, /api/health, /api/status, /api/metrics, /api/engines, /api/events
        ├── WS:   /api/ws (replay from ?since=<iso> then live push)
        └── _SecurityMiddleware (loopback-only Host check, security headers)
```

**Contract (ADR 0002/0009):** read-only. Write endpoints arrive in Phase 2
with bearer-token auth, CSRF headers, and mandatory write audit (ADR 0010).
Loopback hosts only: `127.0.0.1`, `localhost`, `::1`, `[::1]` — DNS-rebinding
defense. Every runtime call goes through `run_in_threadpool` — runtime locks
are never held on the event loop.

## Key Invariants

1. **Registry is frozen** — `CompanyRegistry` uses `ConfigDict(frozen=True)`.
2. **Config is declarative** — pipelines, recovery policies, scheduler jobs,
   startup steps, and engine configs all live in YAML (no hardcoded logic).
3. **Engines don't call each other** — the Coordinator dispatches by task_type.
4. **Generated output is ephemeral** — `generated/`, `memory/`, `runtime/`,
   `events/`, `reports/`, `dashboards/` are all gitignored.
5. **CLI is fail-open** — telemetry, event bus, and event bus publishing
   never crash the CLI if persistence fails.
6. **Supervisor restarts before isolating** — engines get up to
   `recovery.yaml` max attempts with restart before isolation (ADR 0007).

## Related Docs

- `.ai/architecture.md` — subsystem responsibilities and data flow summary
- `.ai/repo-map.md` — file-by-file map of every module
- `diagrams/data-flow-diagram.md` — process & data-store index (Level 0/1/2)
- `docs/EXECUTION_MODEL.md` — orchestration plan/schedule/run/recovery
- `docs/STARTUP_SEQUENCE.md` — 10-step boot / 6-step shutdown
- `docs/RUNTIME_ENGINE.md` — kernel module map, job catalog
- `docs/PIPELINES.md` — task types, stage modes, built-in pipelines
- `docs/OPERATIONS_RUNBOOK.md` — daily operations, troubleshooting
- `docs/CHECKPOINTS.md` — checkpoint save/restore mechanics
- `docs/RECOVERY.md` — recovery strategies and policies
