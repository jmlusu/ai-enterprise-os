# Execution Model

This document describes how an `OrchestrationPlan` moves from planning to
execution: scheduling, the run lifecycle, parallelism, retries, and events.

## Planning

`OrchestrationEngine.plan(name)` resolves a pipeline from the catalog
(config first, built-ins as fallback) and wraps it in an `OrchestrationPlan`
with a unique id, `ScheduleMode` (default `immediate`), and optional
`scheduled_at`, `interval_seconds`, `max_runs`, and `depends_on` fields.

`start(plan)` branches on the schedule mode:

- **immediate** → executed synchronously via `run()`; returns `ExecutionRecord`.
- **scheduled / recurring / dependency** → registered with the scheduler;
  returns the plan unchanged.

## Schedule Modes

| Mode | Runs when | Config |
|---|---|---|
| `immediate` | As soon as started (once) | default; `scheduler.default_mode` |
| `scheduled` | `now >= scheduled_at` (once) | `scheduled_at` or `scheduler.default_delay_seconds` |
| `recurring` | Every `interval_seconds`, up to `max_runs` | defaults in `scheduler.recurring` |
| `dependency` | After every plan in `depends_on` completes | `scheduler.dependency.default_timeout_seconds`, `fail_on_missing_dependency` |

The `OrchestrationScheduler` computes due plans with `due_plans(now)`,
records execution with `mark_run(plan, now)` (clock-injectable for
deterministic testing), and can run a background worker thread
(`start()`, `stop()`) that polls every `scheduler.worker_interval_seconds`
and invokes the `on_due` callback. `run_once()` returns due plans without
marking them run — the consumer marks them.

## Run Lifecycle

```
PENDING ──▶ RUNNING ──▶ COMPLETED
              │  ▲
              ▼  │ recovery
            FAILED ──▶ RECOVERING ──▶ COMPLETED
              │
           CANCELLED
```

Transition rules are enforced by `lifecycle.py` (`TASK_TRANSITIONS`,
`PIPELINE_TRANSITIONS`); invalid transitions raise
`InvalidTransitionError`. Task state is derived from results
(`TaskStatus.PENDING / RUNNING / COMPLETED / FAILED / SKIPPED`).

`run()` executes synchronously:

1. `_mark_active()` — latches `engine_status().running` and `started_at`.
2. `scheduler.mark_run(plan)` — advances run bookkeeping.
3. `PipelineRunner.run(plan, context, checkpoint)` — executes stages in
   order; parallel stages submit tasks to a `ThreadPoolExecutor` capped by
   `engine.max_workers` / `dependencies.max_parallel_tasks`.
4. On failure, an **auto-recovery loop** runs when
   `recovery.auto_recover: true` (up to `recovery.max_recovery_attempts`);
   otherwise the plan stays `FAILED` for manual `resume` / `retry` /
   `rollback` via CLI or API.

## Task Execution & Retries

Each task is executed by `TaskExecutor` through the Coordinator:

- Handler selected by `task.task_type`; missing handler → `TaskExecutionError`.
- Per-task retry policy: `task.retry.max_retries` if declared, else
  `retries.default_max_retries` with exponential backoff
  (`backoff_base_seconds * backoff_multiplier^attempt`, capped at
  `max_backoff_seconds`, plus `jitter`). Only `retries.retryable_errors`
  are retried.
- Per-task timeout: `retries.timeout_seconds` (default 3600).

## Checkpointing During a Run

With `checkpoints.auto_checkpoint_on_task_completed` /
`auto_checkpoint_on_stage_completed` enabled, the runner snapshots state
after each task/stage boundary (see `docs/CHECKPOINTS.md`). Checkpoints
carry the stage/task index so a resume can skip completed work.

## Events & Notifications

Lifecycle transitions emit events through `notifications.py`:

| Channel | Output |
|---|---|
| Event Bus | `pipeline.*` and `task.*` events (payload: plan_id, pipeline, status, stage; correlation_id links a run) |
| Memory | lifecycle records in `monitoring.history_namespace` (`orchestration`) |
| Audit | audit records per run |

`monitoring.record_history` keeps execution records for `engine.history()`.

## Error Handling

| Error | Raised when |
|---|---|
| `PipelineNotFoundError` / `PlanNotFoundError` | Unknown pipeline/plan reference |
| `InvalidTransitionError` | Illegal state transition |
| `TaskExecutionError` | Task handler failed (retryable) |
| `CheckpointError` | Checkpoint save/restore failed |
| `RecoveryError` | Recovery disabled or impossible |
| `CycleError` / `DependencyError` | Cyclic/missing dependency graph (`dependencies.yaml` policies) |

## Failure Paths

1. **Task fails, retries exhausted** → task `FAILED` → stage fails → pipeline
   `FAILED` → recovery (auto or manual).
2. **Engine not registered / handler missing** → `EngineNotReadyError` →
   pipeline `FAILED`.
3. **Interruption (crash)** → no final state; resume from the latest
   checkpoint restores progress.
