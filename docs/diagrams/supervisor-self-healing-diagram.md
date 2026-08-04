# Supervisor Self-Healing State Machine

The supervisor owns the runtime failure-detection and recovery loop:
**restart before isolate** (ADR 0007). Heartbeats/staleness, health checks,
and watchdog deadlines funnel into `Supervisor.on_failure`, recovery policies
decide the action sequence, and isolation produces operator-visible alerts
(Sprint 5.4 T3) that resolve on re-admission.

```mermaid
flowchart LR
    subgraph DETECT["Failure detection (background workers)"]
        HB["HeartbeatManager<br/>stale component → heartbeat_timeout"]
        HM["HealthMonitor<br/>unhealthy / degraded engine"]
        WD["Watchdog<br/>task deadline overrun → deadline_exceeded"]
    end

    SUP["Supervisor.on_failure(name, reason)<br/>check_once() = deterministic single pass"]
    REC["RecoveryManager.recover(name, reason)<br/>attempts + backoff (1s · x2 · cap 60s)"]

    subgraph POLICY["RecoveryPolicy actions (config/runtime/recovery.yaml)"]
        A1["restart<br/>(ProcessManager record · factory ·<br/>component_factory)"]
        A2["reload_state<br/>(re-run component factory)"]
        A3["isolate<br/>(stop managed process, mark isolated)"]
        A4["escalate<br/>(publish runtime.component_failed)"]
    end

    subgraph ISOLATE["Isolation (ADR 0007 / T3)"]
        ISO["isolate(name, reason)<br/>remove from heartbeat + health monitoring"]
        ALERT_OPEN["runtime.engine_isolated event<br/>+ record_alert_open(component, reason,<br/>attempts, source) → runtime/alerts.jsonl"]
    end

    UNISO["unisolate(name)<br/>re-admit · reset attempts<br/>runtime.engine_unisolated event<br/>+ record_alert_resolved(component)"]
    EVT["runtime.component_failed published<br/>for every failure"]

    HB --> SUP
    HM --> SUP
    WD --> SUP
    SUP --> EVT
    SUP --> REC
    REC -->|"first success ends sequence<br/>(escalate alone does not)"| POLICY
    REC -->|"no success / attempts exceeded<br/>(Max attempts exceeded)"| ISOLATE
    A3 --> ISOLATE
    A4 --> EVT
    REC -->|"recovered → back to monitoring"| HM
    ISO --> ALERT_OPEN
    ALERT_OPEN --> UNISO
    UNISO -->|"re-admitted"| HM

    classDef detect fill:#1a4a6a,stroke:#3498db,stroke-width:2px,color:#fff
    classDef core fill:#6e2c00,stroke:#e67e22,stroke-width:2px,color:#fff
    classDef policy fill:#0e4d45,stroke:#1abc9c,stroke-width:2px,color:#fff
    classDef isol fill:#641e16,stroke:#e74c3c,stroke-width:2px,color:#fff

    class HB,HM,WD detect
    class SUP,REC core
    class A1,A2,A3,A4 policy
    class ISO,ALERT_OPEN,UNISO,EVT isol
```

## Supervisor component state machine

A component is a registered engine or managed process. Policies match exact
name first, then trailing-`*` wildcard; a policy without `max_attempts`
inherits `default_max_attempts` (engine 3, process 2).

```mermaid
stateDiagram-v2
    [*] --> MONITORED
    MONITORED --> FAILURE_DETECTED: heartbeat stall / unhealthy / deadline
    FAILURE_DETECTED --> RECOVERING: on_failure → recover()
    RECOVERING --> MONITORED: concrete action succeeded (restart / reload_state)
    RECOVERING --> RECOVERING: retry with backoff (attempts < max)
    RECOVERING --> ISOLATED: attempts exceeded · no matching policy<br/>recovery success=False
    ISOLATED --> ALERT_OPEN: isolate() → engine_isolated + record_alert_open
    ALERT_OPEN --> ALERT_OPEN: repeated isolates collapse<br/>(latest record per component wins)
    ALERT_OPEN --> MONITORED: unisolate() → engine_unisolated +<br/>record_alert_resolved (alert cleared)
    FAILURE_DETECTED --> ISOLATED: isolate() direct (e.g. no policy)
    ISOLATED --> [*]: component stopped
```

## Alert lifecycle (no-spam contract)

`telemetry/alerts.py::alerts_summary` derives the open-alert set from
`runtime/alerts.jsonl` — the **latest record per component wins**. A component
is open only while its most recent record is `open`; recovery or un-isolation
writes a `resolved` record that supersedes it, so one isolated component yields
exactly one open alert until resolved. Corrupt/missing lines are skipped;
every write is fail-open.

## References

- `docs/SUPERVISOR.md` — failure pipeline, policies, isolation, watchdog
- `docs/RECOVERY.md` — recovery strategies and semantics
- `docs/adr/0007-supervisor-self-healing-restart-before-isolate.md`
- `src/ai_company/runtime/` — `supervisor.py`, `recovery.py`, `watchdog.py`,
  `heartbeat.py`
- `src/ai_company/telemetry/alerts.py` — alert log + summary
- `config/runtime/recovery.yaml`, `heartbeat.yaml`, `monitoring.yaml`
