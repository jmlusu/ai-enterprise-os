# Orchestration Engine

**Role:** The COO layer of the AI Enterprise OS. The Orchestration Engine
(`src/ai_company/orchestration/`) plans, schedules, executes, checkpoints,
and recovers company pipelines by **coordinating the existing engines** —
Registry, Generator, Validator, Workflow, Decision, Memory, Event Bus, and
Audit. It never implements business logic itself; every action is delegated
to a registered engine through the Coordinator.

## Design Principles

1. **Configuration-driven.** Pipelines and engine behavior live in
   `config/orchestration/*.yaml`, not in code.
2. **No business logic.** The engine orchestrates; engines execute.
3. **Durability by default.** Every run is checkpointed and recorded in
   memory/history so interrupted pipelines can be resumed or recovered.
4. **Observable.** Every lifecycle transition publishes `pipeline.*` and
   `task.*` events on the Event Bus and writes audit records.

## Package Layout

| Module | Responsibility |
|---|---|
| `engine.py` | `OrchestrationEngine` facade — plan, run, resume, retry, rollback, status, health, history, checkpoints, auto-recovery |
| `coordinator.py` | `Coordinator` — dispatches tasks to registered engines via default handlers |
| `planner.py` | `PipelinePlanner` — resolves pipeline definitions from config and built-ins |
| `pipeline.py` | `PipelineRunner` — executes a plan stage-by-stage, task-by-task |
| `executor.py` | `TaskExecutor` — runs a single task through the coordinator |
| `scheduler.py` | `OrchestrationScheduler` — immediate/scheduled/recurring/dependency due-plan computation + background worker |
| `dependencies.py` | Dependency resolution (topological/layered, condition evaluation) |
| `lifecycle.py` | State-machine rules for task and pipeline transitions |
| `state.py` | `ExecutionStateStore` — live state and history, persisted to Memory |
| `checkpoint.py` | `CheckpointManager` — snapshots of pipeline progress |
| `rollback.py` | `RollbackManager` — undo handlers keyed by task/action |
| `recovery.py` | `RecoveryManager` — checkpoint-first / rollback-then-retry / retry-only strategies |
| `metrics.py` | `MetricsCollector` — per-run and cumulative counters |
| `health.py` | `HealthChecker` — probes every coordinated engine |
| `monitoring.py` / `notifications.py` | Observability + event/audit/memory lifecycle notification wiring |
| `models.py` / `exceptions.py` / `config.py` | Pydantic models, error types, YAML config loading |

## Configuration

All configuration lives in `config/orchestration/`:

| File | Purpose |
|---|---|
| `engine.yaml` | Engine identity, concurrency, history persistence, **declarative pipeline catalog** |
| `scheduler.yaml` | Schedule modes, worker interval, recurring/dependency defaults |
| `dependencies.yaml` | Topological resolution, parallel caps, condition engine |
| `retries.yaml` | Default task retry policy (backoff, retryable errors) |
| `checkpoints.yaml` | Checkpoint on/off, disk/memory persistence, per-pipeline cap |
| `monitoring.yaml` | Metrics, event publishing, history retention |
| `notifications.yaml` | Event Bus / Memory / Audit lifecycle channels |
| `recovery.yaml` | Strategy, attempt limits, action sequence |

## Orchestration Flow

```
config/orchestration/engine.yaml ──▶ PipelinePlanner ──▶ Pipeline (stages/tasks)
                                                              │
request ──▶ OrchestrationEngine.plan() ──▶ OrchestrationPlan   │
                     │                                        ▼
                     ├─▶ run() ──▶ PipelineRunner ──▶ stages ──▶ tasks
                     │              │  │  │                 │
                     │              │  │  └─▶ TaskExecutor ──▶ Coordinator
                     │              │  │         │              │
                     │              │  └─▶ checkpoint           ├─ registry
                     │              └─▶ notify/events           ├─ generator
                     ├─▶ scheduler (scheduled/recurring)       ├─ validator
                     └─▶ recovery/rollback on failure          ├─ memory
                                                               ├─ audit
                                                               └─ ...
```

## Public API

| Method | Purpose |
|---|---|
| `plan(name=..., yaml_path=..., data=...)` | Create an `OrchestrationPlan` from a catalog pipeline, a YAML file, or an inline pipeline dict |
| `list_pipelines()` / `list_plans()` | Catalog and plan listings |
| `start(plan)` | Immediate plans run synchronously; others are registered with the scheduler |
| `run(plan, context, checkpoint)` | Execute synchronously, with auto-recovery loop |
| `resume(plan_id, checkpoint_id)` | Resume from latest/named checkpoint |
| `retry(plan_id)` / `rollback(plan_id, reason)` | Re-run a plan; execute registered rollback handlers |
| `status(plan_id)` / `engine_status()` | `EngineStatus` view (running latch, health, metrics, message) |
| `health()` | Per-engine health probes |
| `history(plan_id)` | Execution records (from Memory) |
| `checkpoints(pipeline_id)` | Checkpoint snapshots for a pipeline |
| `register_engine(name, engine)` / `register_handler(task_type, fn)` | Extend the coordinator |
| `start_scheduler()` / `stop_scheduler()` / `close()` | Background worker lifecycle |

## CLI

The `orchestrate` group (`ai-company orchestrate`) exposes the engine:

| Command | Purpose |
|---|---|
| `orchestrate plan <name>` | Show a pipeline's structure |
| `orchestrate start <name>` | Start a pipeline (immediate = synchronous run) |
| `orchestrate status <plan-id>` | Show plan state |
| `orchestrate resume <plan-id>` | Resume from the latest checkpoint |
| `orchestrate retry <plan-id>` | Re-run a failed plan |
| `orchestrate rollback <plan-id>` | Execute rollback handlers |
| `orchestrate history [plan-id]` | List execution records |

## Events

The engine publishes lifecycle events on the Event Bus
(`pipeline.*`, `task.*` domains — see `config/events/event_registry.yaml`):

| Event | Meaning |
|---|---|
| `pipeline.started` / `pipeline.completed` | Run began / finished successfully |
| `pipeline.failed` / `pipeline.cancelled` | Run failed / cancelled |
| `pipeline.recovered` | Run recovered via recovery strategy |
| `task.started` / `task.completed` | Task began / finished |
| `task.failed` / `task.skipped` | Task failed / skipped |

Pipeline events carry `plan_id`, `pipeline`, `status`, and `stage` in their
payload; all events of one run share a `correlation_id`.
