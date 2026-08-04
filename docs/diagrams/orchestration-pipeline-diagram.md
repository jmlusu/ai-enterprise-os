# Orchestration / COO Pipeline Diagram

The Orchestration Engine (`src/ai_company/orchestration/`) is the COO layer:
it plans, schedules, executes, checkpoints, and recovers company pipelines by
**coordinating the existing engines** — it never implements business logic.
Configuration-driven from `config/orchestration/*.yaml`.

```mermaid
flowchart TB
    REQ["Operator request<br/>CLI: ai-company orchestrate start &lt;name&gt;<br/>API: POST /api/orchestrate/start<br/>scheduler: scheduled / recurring"]

    subgraph ORCH["OrchestrationEngine (facade)"]
        PLAN["plan(name | yaml_path | inline)<br/>PipelinePlanner → OrchestrationPlan<br/>(stages → tasks, dependency resolution)"]
        RUN["run(plan, context, checkpoint)<br/>auto-recovery loop"]
        SCHED["OrchestrationScheduler<br/>immediate · scheduled · recurring<br/>dependency due-plan computation"]
        RESUME["resume(plan_id, checkpoint_id)"]
        RETRY["retry(plan_id) — re-run"]
        ROLLBACK["rollback(plan_id, reason)"]
        STATUS["status · health · history · checkpoints"]
    end

    subgraph RUNNER["PipelineRunner + TaskExecutor"]
        STAGES["execute plan stage-by-stage<br/>sequential / parallel / conditional"]
        TASKS["task dispatch (dependency-ready)"]
        EXEC["TaskExecutor — one task<br/>via Coordinator"]
        CHECK["CheckpointManager<br/>snapshot progress (disk + memory)"]
        STATE["ExecutionStateStore<br/>live state + history → Memory"]
    end

    subgraph COORD["Coordinator (task dispatch → engines)"]
        C_REG["registry"]
        C_GEN["generator"]
        C_VAL["validator"]
        C_WF["workflow"]
        C_DEC["decision"]
        C_MEM["memory"]
        C_GRAPH["graph"]
        C_EV["event bus"]
        C_AUDIT["audit"]
    end

    subgraph RECOVERY["RecoveryManager (on failure)"]
        STRAT["strategy:<br/>checkpoint_first (default)<br/>rollback_then_retry · retry_only"]
        A1["checkpoint_restore<br/>(resume from latest)"]
        A2["rollback<br/>(RollbackManager undo handlers)"]
        A3["retry<br/>(re-run failed tasks)"]
        AUTO["auto_recover loop ≤ max_recovery_attempts<br/>else FAILED → operator action"]
    end

    subgraph OBS["Observability"]
        EVENTS["Event Bus: pipeline.* task.*<br/>correlation_id per run"]
        METRICS["MetricsCollector · HealthChecker<br/>notifications → audit + memory"]
    end

    REQ --> PLAN
    REQ --> SCHED
    PLAN --> RUN
    SCHED --> RUN
    RUN --> STAGES
    STAGES --> TASKS
    TASKS --> EXEC
    EXEC --> CHECK
    CHECK --> STATE
    EXEC --> COORD
    COORD --> C_REG
    COORD --> C_GEN
    COORD --> C_VAL
    COORD --> C_WF
    COORD --> C_DEC
    COORD --> C_MEM
    COORD --> C_GRAPH
    COORD --> C_EV
    COORD --> C_AUDIT

    RUN -.->|on FAILED| RECOVERY
    RECOVERY --> A1
    RECOVERY --> A2
    RECOVERY --> A3
    A1 -->|"recovered → resume"| RUN
    A2 --> A3
    A3 -->|"recovered"| RUN
    RECOVERY -->|"exhausted → FAILED"| RETRY
    RESUME --> RUN
    RETRY --> RUN
    ROLLBACK --> A2

    RUN --> EVENTS
    COORD --> EVENTS
    RECOVERY --> EVENTS
    RUN --> METRICS
    CHECK --> STATE

    classDef facade fill:#6e2c00,stroke:#e67e22,stroke-width:2px,color:#fff
    classDef runner fill:#1a4a6a,stroke:#3498db,stroke-width:2px,color:#fff
    classDef coord fill:#0e4d45,stroke:#1abc9c,stroke-width:2px,color:#fff
    classDef recovery fill:#641e16,stroke:#e74c3c,stroke-width:2px,color:#fff
    classDef obs fill:#17202a,stroke:#7f8c8d,stroke-width:2px,color:#fff

    class PLAN,RUN,SCHED,RESUME,RETRY,ROLLBACK,STATUS facade
    class STAGES,TASKS,EXEC,CHECK,STATE runner
    class C_REG,C_GEN,C_VAL,C_WF,C_DEC,C_MEM,C_GRAPH,C_EV,C_AUDIT coord
    class STRAT,A1,A2,A3,AUTO recovery
    class EVENTS,METRICS obs
```

## Pipeline state machine

From `src/ai_company/orchestration/lifecycle.py` (`PIPELINE_TRANSITIONS`):

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> SCHEDULED
    PENDING --> RUNNING
    PENDING --> CANCELLED
    SCHEDULED --> RUNNING
    SCHEDULED --> CANCELLED
    RUNNING --> COMPLETED
    RUNNING --> FAILED
    RUNNING --> PAUSED
    RUNNING --> RECOVERING
    PAUSED --> RUNNING
    PAUSED --> RECOVERING
    PAUSED --> CANCELLED
    RECOVERING --> RUNNING
    RECOVERING --> FAILED
    RECOVERING --> PAUSED
    FAILED --> RUNNING: retry / resume
    FAILED --> CANCELLED
    COMPLETED --> [*]
    CANCELLED --> [*]
```

## Task state machine

From `TASK_TRANSITIONS`:

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> READY
    PENDING --> RUNNING
    PENDING --> SKIPPED
    PENDING --> CANCELLED
    READY --> RUNNING
    READY --> SKIPPED
    READY --> CANCELLED
    RUNNING --> COMPLETED
    RUNNING --> FAILED
    RUNNING --> SKIPPED
    RUNNING --> CANCELLED
    FAILED --> READY: retry / resume
    FAILED --> CANCELLED
    COMPLETED --> [*]
    SKIPPED --> [*]
    CANCELLED --> [*]
```

## References

- `docs/ORCHESTRATION_ENGINE.md` — full public API + event catalog
- `docs/RECOVERY.md` — strategies, action sequence, semantics
- `src/ai_company/orchestration/` — engine, coordinator, planner, pipeline,
  executor, scheduler, checkpoint, rollback, recovery, lifecycle
- `config/orchestration/*.yaml` — engine, scheduler, dependencies, retries,
  checkpoints, recovery, monitoring, notifications
