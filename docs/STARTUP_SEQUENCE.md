# Startup & Shutdown Sequences

Both sequences are declarative: `config/runtime/startup.yaml` lists the
ordered boot steps, and the shutdown executor derives its steps from the
same dependency graph in reverse order. Executors live in
`src/ai_company/runtime/startup.py` and `shutdown.py`.

## Startup Steps (11)

`StartupExecutor.run()` executes every step in order and records a
`StartupSequence` with per-step status (`running → completed/failed`),
duration, and reuse flag.

| # | Step | Target | Effect |
|---|---|---|---|
| 1 | `load_constitution` | internal | Load `config/company/*.yaml` into `engine.constitution` |
| 2 | `load_project_state` | internal | Recover persisted `RuntimeState` from disk/memory |
| 3 | `load_configuration_registry` | internal | Load runtime config sections |
| 4 | `initialize_memory` | class | Instantiate `MemoryEngine`, register as `memory` |
| 5 | `initialize_event_bus` | class | Instantiate `EventBus`, register as `event_bus` |
| 6 | `initialize_decision_engine` | class | Instantiate `DecisionEngine`, register as `decision` |
| 7 | `initialize_workflow_engine` | class | Instantiate `WorkflowManager`, register as `workflow` |
| 8 | `initialize_orchestrator` | class | Instantiate `OrchestrationEngine`, register as `orchestration` |
| 9 | `initialize_read_model` | class | Instantiate `ReadModelEngine`, register as `read_model`; rebuild `runtime/dashboard.db` from the JSONL sources (ADR 0004 — rebuild trigger is **startup**) |
| 10 | `start_runtime` | internal | Start workers: event bus, registered engines, scheduler, watchdog, supervisor, config jobs |
| 11 | `ready` | internal | Mark the runtime `RUNNING`, persist `set_started`, publish `runtime.started` |

## Step Types

### Internal targets

- `load_constitution` — `config/company/*.yaml` → `engine.constitution`
- `load_project_state` — `state_store.load()` (skips gracefully when the
  store returns `None` — first boot with no state file)
- `load_configuration` — runtime config registry
- `start_runtime` — `engine.start_workers()`
- `ready` — `engine.mark_ready()`

### Class steps

A step with `module` + `class` + optional `engine` + `params` instantiates
the engine via `importlib` and registers it:

```yaml
- name: "initialize_memory"
  module: "ai_company.memory.engine"
  class: "MemoryEngine"
  engine: "memory"
  params: {}
```

If the target engine name is already registered, the existing instance is
reused (`reused: true`) rather than re-created. The engine name defaults to
the step name minus the `initialize_` prefix.

### Parameter markers

`params` values prefixed with `@` are resolved against the engine:

| Marker | Resolves to |
|---|---|
| `@state_dir` | `state_store.state_dir` |
| `@config:<section>` | `runtime_config.section(<section>)` |
| `@engine:<name>` | a registered engine instance |
| `@event_bus` | `engine.event_bus` |
| `@runtime_config` | `engine.runtime_config` |
| `@runtime` | the engine itself |

## Failure Handling

- `continue_on_error: false` (default) — the first failed step raises
  `StartupError`, the runtime transitions to `failed`, and
  `runtime.component_failed` is published.
- `continue_on_error: true` — remaining steps run; the sequence is marked
  failed but the engine can still be inspected.

## Shutdown Sequence

`ShutdownExecutor` (`shutdown.py`) stops the runtime in dependency-safe
order:

1. Stop the scheduler (stop dispatching jobs).
2. Stop the watchdog (stop deadline enforcement).
3. Stop the supervisor (stop recovery loop).
4. Stop registered engines / managed processes.
5. Persist final state (`set_stopped()` or `save()`).
6. Finalize (`mark_stopped()` publishes `runtime.stopped`).

`RuntimeEngine.stop(reason=...)` drives this and returns the final
`RuntimeStatus`; `restart(reason=...)` calls `stop()` then `start()` and
publishes `runtime.restarted`.
