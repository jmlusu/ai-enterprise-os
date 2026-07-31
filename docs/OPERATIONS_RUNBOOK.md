# Operations Runbook

Operating the Enterprise Runtime Engine from the CLI. All commands live in
the `ai-company runtime` group (8 subcommands):

```
ai-company runtime --help

  start        Boot the runtime and run it in the foreground (Ctrl-C to stop)
  stop         Gracefully shut down the runtime
  restart      Stop, then boot the runtime again
  status       Show runtime lifecycle, engines, processes, and active counts
  health       Run health probes against every engine and the system
  metrics      Show runtime metrics: counters, gauges, queues, error rates
  diagnostics  Produce a full diagnostic report (engines, health, config checksums)
  reload       Hot-reload runtime configuration (restarts jobs, reapplies sections)
```

## Daily Operations

### Start the company

```powershell
ai-company runtime start
```

Boots the 10-step startup sequence, prints the boot summary (startup
success, engines, scheduled jobs), then **blocks** in the main loop until
Ctrl-C. Inspect in a second terminal while it runs:

```powershell
ai-company runtime status
```

Expect `Phase: running`, 5 engines healthy, 5 scheduled jobs.

### Stop / restart

```powershell
ai-company runtime stop
ai-company runtime restart
```

`stop` runs the shutdown sequence (scheduler → watchdog → supervisor →
engines → state persist → finalize) and persists `runtime_state.json`.

### Health check

```powershell
ai-company runtime health
```

6 healthy checks (5 engines + system) on a normal boot. Any
`UNHEALTHY`/`DEGRADED` entry means the supervisor will try to recover that
component; failures without a recovery path end isolated.

### Metrics

```powershell
ai-company runtime metrics
```

Shows counters (starts/restarts/stops/recoveries/errors), gauges, and
queue sizes (`pending: 5` with 5 scheduled jobs queued).

### Diagnostics

```powershell
ai-company runtime diagnostics
```

Full report: phase, engines, health, 8 config sections with checksums,
warnings, errors, recommendations.

### Hot reload

```powershell
ai-company runtime reload
```

Re-reads all 8 YAML configs and prints the sections whose checksum
changed. Scheduler jobs are unregistered and re-registered from
`scheduler.yaml`; other sections are re-applied where supported.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `Startup failed at step ...` | A startup step raised; the runtime transitions to `failed`. Check the step name in the error, fix config, re-run `start` |
| `Component X isolated` in logs | Recovery failed (no policy, no restart mechanism, attempts exhausted). `supervisor.unisolate` re-admits after fixing the cause |
| `Max attempts (...) exceeded` | `recovery.yaml` policy cap hit; component isolated to stop recovery loops |
| `Could not recover runtime state from disk` | `runtime/runtime_state.json` missing/corrupt; runtime starts fresh (warning is informational). Delete the file to reset state |
| `EventBus not started` noise | The event bus only publishes when running; runtime events degrade to local dispatch — expected during shutdown |
| State not recovered across boots | Verify `runtime.persist_state: true` and `startup.recover_persisted_state: true`; state lives in `runtime/runtime_state.json` |

## State File

Persisted state: `runtime/runtime_state.json` (gitignored). It holds the
phase, active-entity lists, processes, and engine records. Deleting it
while the runtime is stopped performs a clean state reset.

## Config Reference

All runtime configuration lives in `config/runtime/`:

| File | Section | Controls |
|---|---|---|
| `runtime.yaml` | `runtime` | identity, `state_dir`, persistence, loop cadence |
| `startup.yaml` | `startup` | ordered startup steps |
| `scheduler.yaml` | `scheduler` | job catalog, worker cadence |
| `heartbeat.yaml` | `heartbeat` | liveness thresholds |
| `monitoring.yaml` | `monitoring` | observability switches |
| `health.yaml` | `health` | probe + system thresholds |
| `recovery.yaml` | `recovery` | recovery policies |
| `diagnostics.yaml` | `diagnostics` | report assembly |

## Related Docs

- [RUNTIME_ENGINE](RUNTIME_ENGINE.md) — kernel overview, module map, engines, jobs
- [RUNTIME_LIFECYCLE](RUNTIME_LIFECYCLE.md) — phase machine, persisted state
- [STARTUP_SEQUENCE](STARTUP_SEQUENCE.md) — boot/shutdown steps
- [SUPERVISOR](SUPERVISOR.md) — failure detection, recovery, isolation
- [HEALTH_MONITORING](HEALTH_MONITORING.md) — probes, heartbeats, metrics, diagnostics
