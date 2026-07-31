# Health Monitoring & Metrics

The runtime monitors itself at three levels: per-engine **heartbeats**
(liveness), proactive **health probes** (including system resources), and a
**watchdog** (deadlines). Counters, gauges, and timers feed the metrics
snapshot, and the diagnostic collector assembles the full report.

Sources: `src/ai_company/runtime/health.py`, `heartbeat.py`, `watchdog.py`,
`metrics.py`, `diagnostics.py`; config: `config/runtime/health.yaml`,
`heartbeat.yaml`, `monitoring.yaml`, `diagnostics.yaml`.

## Health Monitor

`HealthMonitor.check_all()` probes every registered engine plus a `system`
check, producing `HealthCheck` records with a `latency_ms`:

| Status | Meaning |
|---|---|
| `HEALTHY` | Probe succeeded within `health.engine_timeout_seconds` |
| `DEGRADED` | System threshold exceeded: `cpu_percent_high`, `memory_percent_high`, `queue_size_warn`, `error_rate_high` |
| `UNHEALTHY` | Probe failed, raised, or timed out |

```yaml
health:
  enabled: true
  check_interval_seconds: 5.0
  engine_timeout_seconds: 5.0
  cpu_percent_high: 80.0
  memory_percent_high: 80.0
  queue_size_warn: 100
  error_rate_high: 0.2
```

A healthy boot reports **6 healthy checks** (memory, event_bus, decision,
workflow, orchestration, system).

## Heartbeats

Every registered engine gets a heartbeat monitor (`heartbeat.interval_seconds`).
A component whose last beat is older than `timeout_seconds` is stale; after
`missed_beats_before_failure` consecutive misses the watchdog reports
`heartbeat_timeout` and the supervisor starts recovery.

```yaml
heartbeat:
  enabled: true
  interval_seconds: 5.0
  timeout_seconds: 15.0
  missed_beats_before_failure: 3
  check_interval_seconds: 1.0
```

`manager.beat(component, status=..., payload=...)` records a beat and resets
consecutive misses. `manager.check(now=...)` returns `(component, reason)`
failures for the current pass.

## Watchdog

`Watchdog` (`watchdog.py`) combines heartbeat checks with task-deadline
enforcement on a periodic thread (`monitoring.check_interval_seconds`):

- `track_task(task_id, deadline_seconds)` / `untrack_task(task_id)`
- overruns surface as `("task_id", "deadline_exceeded")` and the task is
  untracked after reporting
- `watchdog_enabled: false` disables the loop

## Metrics

`MetricsRegistry` (`metrics.py`) is a thread-safe store of:

- **Counters** — `increment("starts")`, `decrement(...)`; e.g. `starts`,
  `restarts`, `stops`, `recoveries`, `errors`
- **Gauges** — `set_gauge(name, value)`; dicts are stored as-is (e.g.
  `queue_sizes = {"pending": 5}`)
- **Timers** — context-manager timers for probe latency

`RuntimeEngine.metrics()` returns a `RuntimeMetrics` snapshot with
`active_engines`, `engine_healthy`, `engine_degraded`, `engine_unhealthy`,
`queue_sizes`, counters, and error rates. The main loop
(`main_loop()`) refreshes gauges on its cadence
(`runtime.loop_interval_seconds`).

## Diagnostics

`runtime.diagnostics()` assembles a `DiagnosticReport`:

- `phase`, `uptime_seconds`
- `engines` (5) and `health_checks` (6)
- `config_sections` (8) with **checksums** — each section's content is
  hashed so `ai-company runtime reload` can report what actually changed
- `warnings`, `errors`, `recommendations`

`diagnostics.yaml` controls what the collector includes.

## CLI

```
ai-company runtime health        # per-engine probes + system (latency ms)
ai-company runtime metrics       # counters, gauges, queue sizes, error rate
ai-company runtime diagnostics   # full report incl. config checksums
```

All three boot a fresh runtime, take the snapshot, and stop it in
`finally`.

## Testing

- `tests/unit/runtime/test_health.py` (11 tests) — probes, thresholds, system check
- `tests/unit/runtime/test_heartbeat.py` (10 tests) — staleness, misses, callbacks
- `tests/unit/runtime/test_watchdog.py` (8 tests) — deadlines, forwarding
- `tests/unit/runtime/test_metrics.py` (8 tests) — counters, dict gauges, timers
