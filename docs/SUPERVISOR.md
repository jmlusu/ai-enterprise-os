# Supervisor & Recovery

The supervisor owns the failure-detection and recovery loop for the
runtime: heartbeats detect stale components, the health monitor detects
unhealthy engines, the watchdog enforces task deadlines, and recovery
policies decide what to do — restart, reload state, isolate, or escalate.

Sources: `src/ai_company/runtime/supervisor.py`, `recovery.py`,
`watchdog.py`, `heartbeat.py`; config: `config/runtime/recovery.yaml`,
`heartbeat.yaml`, `monitoring.yaml`.

## Failure Pipeline

```
HeartbeatManager (stale component)
        │
        ▼
HealthMonitor (unhealthy engine) ──► Supervisor.on_failure(name, reason)
        │                                    │
        ▼                                    ▼
Watchdog (deadline overrun)         RecoveryManager.recover(name, reason)
                                           │
                                           ▼
                                RecoveryPolicy actions (in order):
                                restart → reload_state → isolate → escalate
```

- The first **successful** concrete action ends the sequence
  (`escalate` alone does not).
- If recovery returns `success=False`, the supervisor **isolates** the
  component (stops monitoring it) and calls `on_engine_failed`.
- A failed component with **no matching policy** is still counted as an
  attempt and isolated, preventing recovery loops.
- `runtime.component_failed` is published on the event bus for every
  failure.

## Recovery Policies

`config/runtime/recovery.yaml`:

```yaml
recovery:
  enabled: true
  default_max_attempts: 3
  backoff_base_seconds: 1.0
  backoff_multiplier: 2.0
  max_backoff_seconds: 60.0
  restart_engines: true
  restart_processes: true
  reload_state: true

  policies:
    engine:
      max_attempts: 3
      actions: ["restart", "reload_state", "isolate"]
    process:
      max_attempts: 2
      actions: ["restart", "isolate"]
```

Policy resolution: exact component-name match first, then a trailing-`*`
wildcard match. A policy without `max_attempts` inherits
`default_max_attempts`; once attempts exceed the cap, recovery reports
`Max attempts (...) exceeded` and the supervisor isolates the component.

| Action | Effect |
|---|---|
| `restart` | Restart via the `ProcessManager` process record, a registered factory, or `component_factory` |
| `reload_state` | Re-run the component factory (state reload) |
| `isolate` | Stop the process (if managed) and mark the component isolated |
| `escalate` | Publish `runtime.component_failed` on the event bus |

## Isolation

- `supervisor.isolate(name, reason)` — removes the component from heartbeat
  and health monitoring and records it as isolated.
- `supervisor.unisolate(name)` — re-admits the component and resets its
  recovery attempts.
- Failures for isolated components are logged and ignored.

## Watchdog

`Watchdog` enforces two things on a periodic thread:

1. **Heartbeat staleness** — components whose last beat is older than
   `heartbeat.timeout_seconds` accumulate consecutive misses; after
   `missed_beats_before_failure` misses, `heartbeat_timeout` is reported.
2. **Task deadlines** — `track_task(id, deadline_seconds)` / `untrack_task`
   manage deadline enforcement; overruns are reported as
   `deadline_exceeded` and the task is untracked.

`Supervisor.check_once(now=...)` is the deterministic single-pass entry
point used by tests and the loop thread.

## Monitoring Config

`config/runtime/monitoring.yaml` controls `check_interval_seconds`,
event publishing, audit records, and memory-record persistence for
observability.

## Testing

- `tests/unit/runtime/test_supervisor.py` (11 tests) — failure flow,
  isolation, callbacks, snapshots
- `tests/unit/runtime/test_recovery.py` (10 tests) — policy matching,
  max-attempts gating, actions, snapshots
- `tests/unit/runtime/test_watchdog.py` (8 tests) — deadlines, heartbeat
  forwarding, start/stop
- `tests/unit/runtime/test_heartbeat.py` (10 tests) — staleness,
  consecutive misses, callbacks
- `tests/integration/test_runtime_restart.py::test_engine_failure_flow_through_supervisor`
