# Runtime Engine

The Enterprise Runtime Engine is the kernel / OS layer of the AI Company.
It boots the company, initializes all engines, supervises agent lifecycles,
monitors health, recovers from failures, schedules recurring work, executes
autonomous workflows, maintains persisted state, coordinates shutdown, and
supports hot configuration reload.

Source lives in `src/ai_company/runtime/`; configuration in
`config/runtime/*.yaml`; tests in `tests/unit/runtime/` and
`tests/integration/test_runtime_boot.py` / `test_runtime_restart.py`.

## Module Map

| Module | Responsibility |
|---|---|
| `models.py` | Data contracts: state, heartbeats, health, jobs, recovery, metrics, startup/shutdown sequences |
| `configuration.py` | YAML-driven runtime configuration (+ hot reload with checksums) |
| `lifecycle.py` | Runtime phase state machine (`created → starting → running → stopping → stopped`) |
| `dependency_graph.py` | Engine start/stop ordering and cycle detection |
| `state.py` | Persisted runtime state (JSON + memory mirror) — see [RUNTIME_LIFECYCLE](RUNTIME_LIFECYCLE.md) |
| `process_manager.py` | Managed runtime processes (threads or external pids) |
| `heartbeat.py` | Component liveness tracking — see [HEALTH_MONITORING](HEALTH_MONITORING.md) |
| `watchdog.py` | Stale-component and task-deadline enforcement — see [HEALTH_MONITORING](HEALTH_MONITORING.md) |
| `scheduler.py` | Recurring / cron / one-time / event-triggered jobs |
| `health.py` | Engine probes + system resource checks — see [HEALTH_MONITORING](HEALTH_MONITORING.md) |
| `metrics.py` | Counters, gauges, timers |
| `diagnostics.py` | `DiagnosticReport` assembly (engines, health, config checksums) |
| `supervisor.py` | Failure detection + recovery coordination — see [SUPERVISOR](SUPERVISOR.md) |
| `recovery.py` | Recovery policy execution — see [SUPERVISOR](SUPERVISOR.md) |
| `startup.py` | Startup sequence executor — see [STARTUP_SEQUENCE](STARTUP_SEQUENCE.md) |
| `shutdown.py` | Shutdown sequence executor — see [STARTUP_SEQUENCE](STARTUP_SEQUENCE.md) |
| `engine.py` | `RuntimeEngine` facade wiring everything together |
| `runtime.py` | Entry points: `create_runtime()` and `main_loop()` |

## Boot Lifecycle

`RuntimeEngine.start()` runs a **10-step startup sequence** (see
[STARTUP_SEQUENCE](STARTUP_SEQUENCE.md)): load the constitution, recover
persisted state, load configuration, initialize the five engines (memory,
event_bus, decision, workflow, orchestration), start background workers
(scheduler, watchdog, supervisor, heartbeats), and mark the runtime
`RUNNING`.

Engines register under canonical names. `register_engine` auto-binds
`self.memory_engine` (name `"memory"`) and `self.event_bus` (name
`"event_bus"`) when they were not passed to the constructor.

```python
from ai_company.runtime import create_runtime

runtime = create_runtime(config_dir="config")
status = runtime.start()  # boots the company
print(status.phase)  # RuntimePhase.RUNNING
runtime.stop(reason="manual")
```

## Registered Engines (5)

| Engine | Module | Role |
|---|---|---|
| `memory` | `ai_company.memory.engine.MemoryEngine` | Long-term memory (state mirroring, consolidation) |
| `event_bus` | `ai_company.events.bus.EventBus` | Runtime event publishing (`runtime.*` types) |
| `decision` | `ai_company.decision.engine.DecisionEngine` | Decision-making |
| `workflow` | `ai_company.orchestrator.workflow.WorkflowManager` | Workflow execution |
| `orchestration` | `ai_company.orchestration.engine.OrchestrationEngine` | Pipeline orchestration (COO) |

## Scheduled Jobs (5)

| Job | Kind | Handler |
|---|---|---|
| Daily executive briefing | `cron 0 7 * * *` | `event_publish` |
| Weekly KPI report | `cron 0 9 * * 1` | `orchestrate_pipeline` |
| Monthly board meeting | `cron 0 10 1 * *` | `event_publish` |
| Quarterly strategy review | `cron 0 11 1 1,4,7,10 *` | `event_publish` |
| Continuous memory consolidation | `recurring` (3600s) | `memory_consolidation` |

The `orchestrate_pipeline` handler checks `orchestration.list_pipelines()`
before planning a run and passes the `OrchestrationPlan` object (not a plan
id) to `orchestration.run(plan)` — jobs for missing catalog pipelines are
logged and skipped.

## Configuration

All sections live in `config/runtime/` and are hot-reloadable:

```
runtime.yaml      name/version/state_dir/persistence/loop cadence
startup.yaml      ordered startup steps
scheduler.yaml    job catalog + worker cadence
heartbeat.yaml    liveness thresholds
monitoring.yaml   metrics/audit/memory-record switches
health.yaml       health thresholds (cpu/memory/queue/error-rate)
recovery.yaml     recovery policies (engine, process)
diagnostics.yaml  report assembly options
```

`ai-company runtime reload` re-reads the YAML files, compares config
checksums, and returns the list of changed sections. Jobs registered from
`scheduler.yaml` are unregistered and re-registered on reload.

## Events

The runtime publishes `runtime.*` events on the event bus (when running):
`runtime.started`, `runtime.stopped`, `runtime.restarted`,
`runtime.reloaded`, `runtime.degraded`, `runtime.state_recovered`,
`runtime.job_executed`, `runtime.component_failed`, and friends — see
`RUNTIME_EVENT_TYPES` in `runtime/models.py`. Local handlers can subscribe
via `runtime.register_handler(event_type, fn)`; publishing degrades
gracefully when the bus is not running.
