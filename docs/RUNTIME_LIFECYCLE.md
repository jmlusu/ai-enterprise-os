# Runtime Lifecycle & Persisted State

## Phase State Machine

`RuntimeLifecycle` (`src/ai_company/runtime/lifecycle.py`) enforces the
runtime phase transitions:

```
created → starting → running → stopping → stopped
   │                      │
   └──→ failed            └──→ failed
```

Transitions are validated; invalid ones raise
`InvalidRuntimeTransitionError`. `force()` bypasses validation and is used
when recovering persisted state from disk.

| Phase | Meaning |
|---|---|
| `created` | Engine instantiated, not started |
| `starting` | Startup sequence in progress |
| `running` | All engines initialized, workers started |
| `stopping` | Shutdown sequence in progress |
| `stopped` | Clean shutdown complete |
| `failed` | Startup or shutdown raised `StartupError` / `ShutdownError` |

## Persisted RuntimeState

`RuntimeStateStore` (`src/ai_company/runtime/state.py`) persists runtime
state to `runtime/runtime_state.json` (configurable via
`runtime.state_dir`) and optionally mirrors it into the Memory Engine under
the `global` namespace, tagged `runtime`.

The state model (`RuntimeState`) tracks:

- `phase`, `started_at`, `stopped_at`, `last_saved_at`
- active entity lists: `active_pipelines`, `active_workflows`,
  `active_decisions`, `active_meetings`, `active_projects`, `active_agents`
- `processes` (name → `RuntimeProcess`)
- `metadata` (engine records under `metadata.engines`)

### Boot-time recovery

`RuntimeEngine.start()` **recovers persisted state before any phase save**
— otherwise the `STARTING`-phase save would clobber the on-disk state with
an empty snapshot. The startup step `load_project_state` then re-loads it
into the running context. If `recover_persisted_state: false` is set in
`startup.yaml`, recovery is skipped.

### Mutations

```python
runtime.state_store.add_active("pipelines", "p_123")  # appends + saves
runtime.state_store.remove_active("pipelines", "p_123")  # removes + saves
runtime.state_store.set_phase(RuntimePhase.RUNNING)
runtime.state_store.set_process(RuntimeProcess(name="worker", status="running"))
runtime.state_store.set_engine(EngineState(name="memory"))
```

Every mutation persists when `runtime.persist_state: true` (default).
`load()` falls back to fresh defaults when nothing is on disk and tolerates
a missing/corrupt file (logging a warning).

## Engine Lifecycle

Each registered engine has an `EngineState` (`registered → running →
stopped/failed/degraded`) tracked alongside its phase:

- `register_engine(...)` → `REGISTERED` (also registers health probe +
  heartbeat monitor + dependency-graph node)
- `_start_registered_engines()` (during the `start_runtime` startup step)
  invokes `start()` on engines whose signature takes no required
  parameters; engines requiring positional args (or lacking `start()`) are
  marked `RUNNING`/healthy without being started
- `unregister_engine(...)` removes the engine from health monitoring,
  heartbeats, and the dependency graph

## Engine State Records

`engine_states()` returns persisted `EngineState` records (surviving
restarts through `state_store.set_engine`). The `runtime status` CLI shows
per-engine `running/registered/stopped` plus health.

## Status Snapshot

`runtime.status()` returns a `RuntimeStatus` with `name`, `version`,
`phase`, `uptime_seconds`, engine states, processes, and active-entity
counts — the same data surfaced by `ai-company runtime status`.
