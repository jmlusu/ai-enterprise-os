# Runtime Boot / Shutdown Lifecycle Diagram

Source of truth: `src/ai_company/runtime/lifecycle.py` (phase machine),
`config/runtime/startup.yaml` (11 boot steps), `src/ai_company/runtime/startup.py`,
`src/ai_company/runtime/shutdown.py` (6 stop steps, dependency-safe reverse order).

## Phase State Machine

`RuntimeLifecycle` validates every transition; illegal ones raise
`InvalidRuntimeTransitionError`. `force()` bypasses validation (used when
recovering persisted state). Source: `RUNTIME_TRANSITIONS` in `lifecycle.py`.

```mermaid
stateDiagram-v2
    [*] --> STOPPED
    STOPPED --> STARTING: start(reason) — recover persisted state first
    STARTING --> RUNNING: ready step → mark_ready()
    STARTING --> STOPPING: abort during boot
    STARTING --> FAILED: StartupError (continue_on_error: false)
    RUNNING --> DEGRADED: engine health DEGRADED
    RUNNING --> RECOVERING: supervisor recovery loop started
    RUNNING --> STOPPING: stop(reason)
    RUNNING --> FAILED: unrecoverable error
    DEGRADED --> RUNNING: health restored
    DEGRADED --> RECOVERING: supervisor recovery loop started
    DEGRADED --> STOPPING: stop(reason)
    DEGRADED --> FAILED: unrecoverable error
    RECOVERING --> RUNNING: recovered
    RECOVERING --> DEGRADED: still degraded
    RECOVERING --> STOPPING: stop(reason)
    STOPPING --> STOPPED: shutdown finalize → mark_stopped()
    STOPPING --> FAILED: ShutdownError (force: false)
    FAILED --> STARTING: restart()
    FAILED --> STOPPED
    STOPPED --> STOPPED: force() recovery of persisted state
```

`restart(reason)` = `stop()` then `start()`; publishes `runtime.restarted`.

## Boot Sequence (11 steps)

Declared in `config/runtime/startup.yaml`; executed by `StartupExecutor.run()`.
Steps whose engine is already registered are **reused**, not re-created.

```mermaid
flowchart TB
    S0["ai-company runtime start"]
    S1["1 · load_constitution<br/>config/company/*.yaml → engine constitution"]
    S2["2 · load_project_state<br/>recover persisted RuntimeState (boot-time recovery<br/>runs BEFORE the STARTING-phase save — otherwise<br/>the save clobbers the on-disk state)"]
    S3["3 · load_configuration_registry<br/>load runtime config sections (9)"]
    S4["4 · initialize_memory<br/>MemoryEngine → engine 'memory'"]
    S5["5 · initialize_event_bus<br/>EventBus → engine 'event_bus'"]
    S6["6 · initialize_decision_engine<br/>DecisionEngine → engine 'decision'"]
    S7["7 · initialize_workflow_engine<br/>WorkflowManager → engine 'workflow'"]
    S8["8 · initialize_orchestrator<br/>OrchestrationEngine (COO) → 'orchestration'<br/>wired to @event_bus"]
    S9["9 · initialize_read_model<br/>ReadModelEngine → 'read_model'<br/>REBUILD runtime/dashboard.db (SQLite WAL)<br/>from JSONL sources (ADR 0004)"]
    S10["10 · start_runtime<br/>start background workers: heartbeat sender,<br/>scheduler, watchdog, supervisor, metrics"]
    S11["11 · ready<br/>mark RUNNING · persist set_started<br/>publish runtime.started"]

    S0 --> S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7 --> S8 --> S9 --> S10 --> S11
```

Failure handling: `continue_on_error: false` (default) — first failed step raises
`StartupError`, runtime transitions to `failed`, publishes
`runtime.component_failed`. With `continue_on_error: true` remaining steps run
and the sequence is marked failed but the engine stays inspectable.

## Shutdown Sequence (6 steps)

Executed by `ShutdownExecutor` in dependency-safe order. **Critical ordering
constraint (Sprint 5.4 T5 fix):** workers stop *before* engines, so no
monitoring thread probes a component mid-teardown (previously the supervisor /
health monitor probed the read-model engine's closed SQLite connection and
segfaulted).

```mermaid
flowchart TB
    D0["RuntimeEngine.stop(reason) · publish runtime.stopping"]
    D1["1 · notify<br/>notify listeners shutdown is beginning"]
    D2["2 · stop_workers<br/>stop heartbeat_sender → scheduler → watchdog → supervisor<br/>(BEFORE engines — Sprint 5.4 T5 segfault fix)"]
    D3["3 · stop_engines<br/>reverse-topological order (dependency graph)<br/>dependents stop before their dependencies"]
    D4["4 · stop_processes<br/>ProcessManager.stop_all()"]
    D5["5 · save_state<br/>persist final state: phase STOPPED, stopped_at"]
    D6["6 · finalize<br/>mark_stopped() · publish runtime.stopped"]

    D0 --> D1 --> D2 --> D3 --> D4 --> D5 --> D6
```

With `force: true` a failed step does not abort the sequence; the final
`ShutdownSequence.success` reflects whether every step completed.

## Worker Set

| Worker | Responsibility |
|---|---|
| `heartbeat_sender` | 5s heartbeats; drives liveness of registered engines |
| `watchdog` | Stale-deadline enforcement → routes failures to the supervisor |
| `scheduler` | One-time / recurring / cron job dispatch (e.g. retention 3600s, memory consolidation) |
| `supervisor` | Recovery loop: restart-before-isolate (ADR 0007); publishes `runtime.engine_isolated` / `runtime.engine_unisolated` + open/resolved alerts |
| `metrics` | 30s persistence ticker → `runtime/metrics_history.jsonl` + read-model sync (single writer) |

## References

- `docs/STARTUP_SEQUENCE.md` — step tables, parameter markers, failure handling
- `docs/RUNTIME_LIFECYCLE.md` — persisted `RuntimeState`, engine lifecycle, status snapshot
- `docs/RECOVERY.md` — supervisor / recovery / isolate semantics
- `src/ai_company/runtime/shutdown.py` — shutdown step implementations
