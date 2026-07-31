# Checkpoints

Checkpoints snapshot pipeline execution state so a run can be resumed after
interruption and so recovery has a known-good point to fall back to. They
are managed by `CheckpointManager`
(`src/ai_company/orchestration/checkpoint.py`).

## What a Checkpoint Contains

| Field | Content |
|---|---|
| `id` | Unique checkpoint id (`chk_...`) |
| `pipeline_id` | Pipeline the snapshot belongs to |
| `plan_id` | Plan being executed |
| `stage_index` / `task_index` | Resume position (task-level when `interval_tasks` allows, else stage-level) |
| `state` | Deep copy of `ExecutionState`: status, task statuses, task results, stage results, error |
| `context` | Execution context snapshot (`checkpoints.include_context`) |
| `created_at` | Timestamp (used for deterministic ordering) |

## Persistence

| Setting | Default | Meaning |
|---|---|---|
| `persist_to_memory` | true | Snapshots stored via the Memory Engine (`orchestration` namespace) so they survive engine restarts |
| `persist_to_disk` | false | Also write JSON files under `checkpoints/` (`disk_path`) |
| `max_checkpoints_per_pipeline` | 10 | Cap; oldest snapshots are pruned (0 = unlimited) |

When a Memory Engine is not available, the manager falls back to in-process
storage and logs the degradation.

## When Checkpoints Are Created

With `checkpoints.enabled`:

- `auto_checkpoint_on_task_completed: true` — snapshot after each task
  (throttled by `interval_tasks`, default every task).
- `auto_checkpoint_on_stage_completed: true` — snapshot at each stage
  boundary.

Checkpoints capture **in-flight** state: the snapshot at a stage boundary
records `PipelineStatus.RUNNING` with all completed tasks/statuses. The
final `COMPLETED` transition happens after the last stage's checkpoint, so
the latest checkpoint for a finished run is the last in-flight snapshot.

## Ordering

`_sort_key = (created_at, stage_index, task_index)` makes `latest()` and
`list_for()` deterministic even when several checkpoints share a timestamp.

## API

| Method | Purpose |
|---|---|
| `create(plan, state, stage_index, task_index=None, context=None)` | Write a snapshot |
| `restore(checkpoint_id)` | Load a snapshot by id |
| `latest(pipeline_id)` | Most recent snapshot for a pipeline |
| `list_for(pipeline_id)` / `all()` | List snapshots (newest first) |
| `delete(checkpoint_id)` / `clear(pipeline_id)` | Remove snapshots |

## Resume Semantics

`engine.resume(plan_id, checkpoint_id=None)` restores the latest (or named)
checkpoint and re-runs from `stage_index`:

- Tasks already `COMPLETED` keep their recorded results (`include_task_results`).
- The resumed runner executes from the stored position; `PENDING` tasks run,
  `FAILED` tasks are re-run (subject to `recovery.keep_recovered_tasks`).

## Notes

- `engine.checkpoints(pipeline_id)` is keyed by **pipeline id**, not plan id.
- Disk persistence writes one JSON file per checkpoint; memory persistence
  stores the same payload in the Memory Engine for durable recovery.
