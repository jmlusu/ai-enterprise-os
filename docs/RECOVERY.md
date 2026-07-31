# Recovery

Recovery returns a failed or interrupted pipeline run to a known-good state.
It is driven by `RecoveryManager`
(`src/ai_company/orchestration/recovery.py`) with configuration from
`config/orchestration/recovery.yaml`.

## Strategy

The recovery strategy selects which actions may run and their order:

| Strategy | Action sequence |
|---|---|
| `checkpoint_first` (default) | `checkpoint_restore` → `rollback` → `retry` |
| `rollback_then_retry` | `rollback` → `retry` |
| `retry_only` | `retry` |

The `action_sequence` in config is respected when `strategy` does not
override it.

| Action | Effect |
|---|---|
| `checkpoint_restore` | Resume from the latest checkpoint (`restore_latest_checkpoint: true`) |
| `rollback` | Invoke registered rollback handlers for failed/completed tasks via `RollbackManager` |
| `retry` | Re-run failed tasks (`retry_failed_tasks: true`) |

## Configuration

```yaml
recovery:
  enabled: true
  auto_recover: false              # auto-recover on failure (or wait for CLI)
  strategy: "checkpoint_first"
  max_recovery_attempts: 3
  restore_latest_checkpoint: true
  rollback_on_unrecoverable: true  # rollback when retries are exhausted
  retry_failed_tasks: true
  keep_recovered_tasks: true       # preserve successful task outputs
```

## Trigger Paths

### Automatic

When `auto_recover: true`, `engine.run()` loops after a `FAILED` result:
`recover(plan, state, reason, undo_func=engine._undo)` is called up to
`max_recovery_attempts` times; each successful recovery resumes from the
restored checkpoint. The recovered run publishes `pipeline.recovered` and
records `state.recovered_from`.

### Manual

When `auto_recover: false` (default), a failed plan stays `FAILED` for
operator action:

- `ai-company orchestrate resume <plan-id>` — resume from the latest checkpoint.
- `ai-company orchestrate retry <plan-id>` — re-run the plan.
- `ai-company orchestrate rollback <plan-id>` — execute rollback handlers.
- `engine.recovery.recover(plan, state, reason, undo_func=...)` — run a
  recovery sequence programmatically; returns `(RecoveryResult, checkpoint)`
  where `RecoveryResult.success` is `True` only when an action was taken or a
  checkpoint restored.

## Rollback

`RollbackManager` registers undo handlers keyed by task id and action
(`register_handler(task_id, action, fn)`). The engine ships one built-in
undo action: `memory.delete` (removes a memory entry by `memory_id`).
Unknown actions log a warning and continue — rollback is best-effort.

## Outcome & Semantics

- `RecoveryResult.success` defaults to `False` and is set to `True` only
  when at least one action was taken or a checkpoint restored.
- `RecoveryError` is raised when recovery is disabled
  (`recovery.enabled: false`) or no action is available.
- Recovery relies on checkpoints: `recovery.restore_latest_checkpoint`
  plus `checkpoints.persist_to_memory` give durable recovery across engine
  restarts.

## Sequence Diagram

```
FAILED plan
   │
   ▼
RecoveryManager.recover(plan, state, reason, undo_func)
   │  strategy = checkpoint_first
   ├─▶ checkpoint_restore ──▶ latest checkpoint found? ──yes──▶ resume point
   │                                │no
   ├─▶ rollback ──▶ handlers for failed tasks (undo side effects)
   ├─▶ retry ──▶ re-run failed tasks
   ▼
(RecoveryResult, checkpoint) ──▶ engine resumes execution
```
