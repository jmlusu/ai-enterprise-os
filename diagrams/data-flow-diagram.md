# Data Flow Diagram

Data flow diagrams for the AI Enterprise OS. They describe **what data
moves where**, complementing the component view in
[`docs/architecture-diagram.md`](../docs/architecture-diagram.md).

## Notation

| Shape | Meaning |
|---|---|
| ⬭ Rounded box | **External entity** (source/sink outside the system) |
| ▭ Rectangle | **Process** (numbered; transforms data) |
| ⎘ Cylinder | **Data store** (persistent data at rest) |
| → Solid arrow | **Data flow** (labeled with the data being moved) |
| ⇢ Dashed arrow | Indirect / out-of-process interaction |

## Process & Store Index

| ID | Process | ID | Data store |
|---|---|---|---|
| 1 | CLI Dispatcher (Typer) | D1 | Config & Registry YAML (`config/*.yaml`, `company/*.yaml`) |
| 2 | Registry Engine (Loader → Parser → Validator → Resolver) | D2 | Templates (`templates/*.j2`) |
| 3 | Template Engine (Loader → Context → Renderer → Writer) | D3 | Generated Output (`generated/`, `reports/`, `dashboards/`) |
| 4 | Generator Engine (Planner → Renderer → Writer) | D4 | Memory Store (`memory/*.json`, `vector_index/*.npy`) |
| 5 | Company Generators (bootstrap/board/exec/dept/specialist/workflow/prompts/docs) | D5 | Event Store (`events/store.jsonl`, `dead_letter.jsonl`) |
| 6 | Validator Engine (YAML · Registry · Templates · Manifest · Output) | D6 | Runtime & Checkpoint State (`runtime/`, `checkpoints/`) |
| 7 | Graph Engine (NetworkX) | D7 | Audit Log (JSONL) |
| 8 | Event Bus (Pub/Sub · Router · Middleware · DLQ · Replay) | | |
| 9 | Memory Engine (6-type store · Search · Consolidation · Encryption) | | |
| 10 | Decision Engine (Approval · Risk · Policy · Routing) | | |
| 11 | Workflow Engine (State machine · Transitions) | | |
| 12 | Audit Engine (JSONL · Metrics · Sessions) | | |
| 13 | Runtime Engine — Kernel (Startup · Scheduler · Watchdog · Supervisor · Health) | | |
| 14 | Orchestration Engine — COO (Planner · Scheduler · Runner · Executor · Coordinator · Recovery) | | |

## Context Diagram (Level 0)

The system as a single process with its external entities.

```mermaid
flowchart LR
    subgraph SYS["AI Enterprise OS"]
        CORE(["AI Enterprise OS"])
    end

    OP(["E1. Operator / User"])
    OC(["E2. OpenCode AI<br/>(subprocess)"])
    AP(["E3. AI Providers<br/>Ollama · OpenAI · Anthropic · Gemini"])
    CI(["E4. GitHub Actions CI/CD"])

    OP -- "CLI commands, config edits" --> CORE
    CORE -- "CLI output, reports, dashboards" --> OP
    CORE -- "generation prompts" --> OC
    OC -- "generated artifacts" --> CORE
    CORE -- "model inference requests" --> AP
    AP -- "inference responses" --> CORE
    CORE -- "lint + validation gates" --> CI
```

## Level 1 — Build-Time Data Flow

The bootstrap/generation pipeline: configuration is read once, turned into an
immutable `CompanyRegistry`, and consumed by generators that produce artifacts
through templates and OpenCode runs, all guarded by the Validator Engine.

```mermaid
flowchart LR
    OP(["E1. Operator / User"])
    OC(["E2. OpenCode AI<br/>(subprocess)"])

    P1["1. CLI Dispatcher<br/>(Typer)"]
    P2["2. Registry Engine<br/>Loader → Parser<br/>Validator → Resolver"]
    P3["3. Template Engine<br/>Loader → Context<br/>Renderer → Writer"]
    P4["4. Generator Engine<br/>Planner → Renderer → Writer"]
    P5["5. Company Generators<br/>Bootstrap · Board · Executives<br/>Departments · Specialists<br/>Workflows · Prompts · Docs"]
    P6["6. Validator Engine"]
    P7["7. Graph Engine<br/>(NetworkX)"]

    D1[("D1. Config & Registry YAML<br/>config/company/company.yaml<br/>company/*.yaml · config/{events,<br/>decision,memory,orchestration,runtime}")]
    D2[("D2. Templates<br/>templates/*.j2")]
    D3[("D3. Generated Output<br/>generated/ · reports/<br/>dashboards/")]

    OP -- "ai-company <command>" --> P1

    P1 -- "load / verify request" --> P2
    D1 -- "raw YAML" --> P2
    P2 -- "CompanyRegistry (frozen)" --> P4
    P2 -- "CompanyRegistry" --> P5
    P2 -- "CompanyRegistry" --> P7

    P1 -- "render request" --> P3
    D2 -- "templates" --> P3
    P3 -- "rendered files" --> D3

    P1 -- "generate <target>" --> P4
    P4 -- "generation dispatch" --> P5
    P5 -- "AI prompts / OpenCode run" --> OC
    OC -- "generated artifacts" --> P5
    P5 -- "artifacts" --> D3

    P1 -- "validate request" --> P6
    D1 -- "config snapshot" --> P6
    D2 -- "templates" --> P6
    D3 -- "generated output" --> P6
    P6 -- "validation report" --> P1

    P4 -- "graph build request" --> P7
    P7 -- "org graph exports" --> D3
```

## Level 1 — Runtime Data Flow

The kernel boots the engines, the Event Bus carries lifecycle signals, the
COO layer dispatches tasks to the engines, and every engine persists to its
own store and reports to memory/audit.

```mermaid
flowchart LR
    OP(["E1. Operator / User"])
    OC(["E2. OpenCode AI<br/>(subprocess)"])
    AP(["E3. AI Providers"])

    P2["2. Registry Engine"]
    P4["4. Generator Engine"]
    P6["6. Validator Engine"]
    P7["7. Graph Engine"]

    P8["8. Event Bus<br/>Pub/Sub · Router · Middleware<br/>DLQ · Replay · Priorities"]
    P9["9. Memory Engine<br/>6-type store · Search<br/>Consolidation · Encryption"]
    P10["10. Decision Engine<br/>Approval · Risk · Policy"]
    P11["11. Workflow Engine<br/>State machine"]
    P12["12. Audit Engine<br/>JSONL · Metrics · Sessions"]
    P13["13. Runtime Engine (Kernel)<br/>Startup · Scheduler · Watchdog<br/>Supervisor · Heartbeat · Health"]
    P14["14. Orchestration Engine (COO)<br/>Planner · Scheduler · Runner<br/>Executor · Coordinator · Recovery"]

    D1[("D1. Config & Registry YAML")]
    D3[("D3. Generated Output")]
    D4[("D4. Memory Store<br/>memory/*.json<br/>vector_index/*.npy")]
    D5[("D5. Event Store<br/>store.jsonl · dead_letter.jsonl")]
    D6[("D6. Runtime & Checkpoint State<br/>runtime/runtime_state.json<br/>checkpoints/")]
    D7[("D7. Audit Log (JSONL)")]

    OP -- "runtime start/stop/status/reload" --> P13
    OP -- "orchestrate plan/start/resume/retry" --> P14

    P13 -- "recover + persist state" --> D6
    D6 -- "persisted RuntimeState" --> P13
    P13 -- "state mirror" --> P9
    P13 -- "runtime.* events" --> P8
    P13 -- "scheduled jobs (cron/recurring)" --> P14
    P13 -- "boot-time registry load" --> P2

    P14 -- "pipeline.* / task.* events" --> P8
    P14 -- "checkpoints (save/restore)" --> D6
    P14 -- "execution history" --> P9
    P14 -- "audit records" --> P12

    P14 -- "task: load_registry" --> P2
    P14 -- "task: generate" --> P4
    P14 -- "task: validate" --> P6
    P14 -- "task: graph_build / report" --> P7
    P14 -- "task: event_publish" --> P8
    P14 -- "task: memory_save/search" --> P9
    P14 -- "task: decision" --> P10
    P14 -- "task: workflow" --> P11
    P14 -- "task: audit_record" --> P12

    P4 -- "AI prompts" --> OC
    P4 -- "model calls" --> AP
    AP -- "inference responses" --> P4

    P8 -- "persist events" --> D5
    P8 -- "dead letters" --> D5
    P8 -- "replay / audit feed" --> P12

    P9 -- "read / write entries" --> D4
    P10 -- "approved resolutions (knowledge)" --> P9
    P11 -- "task outcomes (episodic)" --> P9

    P12 -- "write records" --> D7
    P7 -- "graph exports" --> D3
    P2 -- "reads" --> D1
```

## Level 2 — Orchestration Task Execution

Detail of process 14: how a pipeline plan is scheduled, executed task-by-task,
and dispatched to the engines through the Coordinator.

```mermaid
flowchart LR
    OP(["E1. Operator / User"])

    P14["14. Orchestration Engine (COO)"]
    P141["14.1 PipelinePlanner"]
    P142["14.2 OrchestrationScheduler"]
    P143["14.3 PipelineRunner"]
    P144["14.4 TaskExecutor"]
    P145["14.5 Coordinator"]
    P146["14.6 RecoveryManager<br/>checkpoint → rollback → retry"]

    D1[("D1. Config & Registry YAML<br/>config/orchestration/*.yaml<br/>pipeline catalog")]
    D4[("D4. Memory Store")]
    D6[("D6. Runtime & Checkpoint State")]
    D7[("D7. Audit Log (JSONL)")]

    P2["2. Registry Engine"]
    P4["4. Generator Engine"]
    P6["6. Validator Engine"]
    P7["7. Graph Engine"]
    P8["8. Event Bus"]
    P9["9. Memory Engine"]
    P10["10. Decision Engine"]
    P11["11. Workflow Engine"]
    P12["12. Audit Engine"]

    OP -- "plan / start / resume / retry / rollback" --> P14

    P14 --> P141
    P14 --> P142
    P14 --> P143

    P141 -- "pipeline lookup" --> D1
    D1 -- "Pipeline (stages/tasks)" --> P141
    P142 -- "due plan" --> P143
    P143 -- "stages → tasks" --> P144
    P143 -- "checkpoint after task/stage" --> D6
    P143 -- "rollback on failure" --> P146
    P146 -- "recovered plan" --> P143

    P144 -- "task with params" --> P145

    P145 -- "load_registry" --> P2
    P145 -- "generate" --> P4
    P145 -- "validate" --> P6
    P145 -- "graph_build / report" --> P7
    P145 -- "event_publish" --> P8
    P145 -- "memory_save / memory_search" --> P9
    P145 -- "decision" --> P10
    P145 -- "workflow" --> P11
    P145 -- "audit_record" --> P12

    P9 -- "read / write" --> D4
    P12 -- "write records" --> D7
    P8 -- "lifecycle events" --> P12
    P14 -- "execution records" --> P9
```

## Key Flows

| # | Flow | Path | Data |
|---|---|---|---|
| F1 | Configuration load | D1 → 2 | Raw YAML → frozen `CompanyRegistry` |
| F2 | Generation | D2 → 3 → D3, 4 → 5 → E2 → D3 | Templates + registry → rendered artifacts |
| F3 | Validation gate | 6 ← (D1, D2, D3) → 1 | Reports gate CLI / CI |
| F4 | Runtime boot | D6 → 13 → (8, 9, 10, 11, 14) | Persisted state + engine initialization |
| F5 | Orchestration | 14 → Coordinator → engines | Pipeline tasks dispatched by `task_type` |
| F6 | Observability | 14/13 → 8 → D5 → 12 → D7 | Events → store → audit log |
| F7 | Memory lifecycle | 9 → D4, 14 → 9 → D6 | Entries, history, checkpoints |

## Sources

- `docs/architecture.md` — subsystem responsibilities
- `docs/architecture-diagram.md` — component diagram
- `docs/PIPELINES.md` — task types, stage modes, built-in pipelines
- `docs/EXECUTION_MODEL.md` — plan → schedule → run → recovery
- `docs/STARTUP_SEQUENCE.md` — runtime boot steps
- `docs/ORCHESTRATION_ENGINE.md` — COO coordinator wiring
- `docs/memory-engine-design.md` — memory taxonomy and persistence
- `config/events/event_pipeline.yaml` — event bus pipeline
