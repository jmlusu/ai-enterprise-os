# Repository Map

> **Purpose:** File-by-file map of the repository. Read before navigating —
> it saves rediscovery. Update whenever files are added/removed/renamed.

## Source: `src/ai_company/`

### Entry Points

| File | Purpose |
|---|---|
| `__init__.py` | Package root |
| `__main__.py` | `python -m ai_company` entry |
| `cli/main.py` | Typer app `ai_company.cli.main:app` (frozen tree, ADR 0006) |
| `cli/command_map.py` | Command-map contract (CI integrity check) |
| `cli/render.py`, `cli/utils.py` | CLI rendering + utilities |
| `cli/groups/company_cli.py` | `bootstrap`, `build`, `generate`, `validate`, `doctor`, `targets`, `status` commands |
| `cli/groups/registry.py` | `registry list/show/verify` |
| `cli/groups/executive.py` | Executive subsystem |
| `cli/groups/memory.py` | `memory show/clear` |
| `cli/groups/graph.py` | `graph show/stats` |
| `cli/groups/report.py` | `report generate <type>` |
| `cli/groups/runtime.py` | `runtime start/stop/restart/status/reload/health/metrics/scheduler/supervisor` |
| `cli/groups/orchestration.py` | `orchestrate start/stop/status/plans/records/jobs/recover/rollback` |

### Build-Time Layer

| File | Purpose |
|---|---|
| `registry/loader.py` | Multi-file YAML loader |
| `registry/parser.py` | YAML → typed structures |
| `registry/registry.py` | `RegistryEngine` — loads to frozen `CompanyRegistry` (singleton at line 191) |
| `registry/resolver.py` | Cross-file reference resolution |
| `registry/validate.py` | Registry validation |
| `validator/engine.py` | `ValidatorEngine.validate_all()` — 5-target gate |
| `validator/reports.py` | Validation report model + summary |
| `validator/yaml_validator.py` | YAML syntax/existence/empty checks |
| `validator/registry_validator.py` | Cross-file consistency, department resolution |
| `validator/template_validator.py` | Jinja2 syntax, required templates |
| `validator/manifest_validator.py` | Manifest schema + business rules |
| `validator/output_validator.py` | Generated files exist/non-empty/unresolved `{{ }}` |
| `bootstrap/bootstrap.py` | Scaffold missing dirs + placeholders |
| `template_engine/loader.py` | `TemplateLoader` (file/string, format detect) |
| `template_engine/context.py` | `TemplateContext` (dot-path access) |
| `template_engine/renderer.py` | `Renderer` → format handlers |
| `template_engine/writer.py` | `Writer` (file/stdout) |
| `template_engine/handlers/` | `base.py`, `jinja_handler.py`, `python_handler.py` (`{key}`), `markdown_handler.py`, `json_handler.py`, `yaml_handler.py`, `_substitution.py` |

### Company Generators

| File | Purpose |
|---|---|
| `company/generator.py` | `CompanyGenerator` — orchestrates all generators |
| `company/models.py` | Generator models |
| `company/organization.py` | `generate_organization()` |
| `company/board_generator.py` | `generate_board()` |
| `company/executive_generator.py` | `generate_executives()` |
| `company/department_generator.py` | `generate_departments()` |
| `company/specialist_generator.py` | `generate_specialists()` |
| `company/workflow_generator.py` | `generate_workflows()` |
| `company/doc_generator.py` | `generate_docs()` |
| `company/prompt_generator.py` | `generate_prompts()` |
| `company/graph_exporter.py` | `generate_graph_export()` |
| `company/hierarchy.py`, `company/relationships.py`, `company/roles.py`, `company/reporting.py` | Org structure helpers |
| `generator/engine.py` | Build pipeline engine |
| `generator/planner.py` | Phase/target planning |
| `generator/renderer.py`, `generator/writer.py` | Render/write stages |
| `generator/context.py`, `generator/dependency.py` | Context + dependency resolution |
| `generator/manifest.py` | Build manifest |
| `generator/prompt_generator.py` | OpenCode prompt generation |

### Graphs

| File | Purpose |
|---|---|
| `graph/organization.py` | NetworkX org graph |
| `graph/workflow.py` | Workflow graph |
| `graph/projects.py` | Project graph |
| `graph/dependency.py` | Dependency graph |
| `graph/export.py` | Graph export (JSON etc.) |
| `graph/visualize.py` | Visualization |

### Run-Time Layer — Kernel (`runtime/`)

| File | Purpose |
|---|---|
| `runtime/engine.py` | `RuntimeEngine` facade + engine registry |
| `runtime/runtime.py` | `create_runtime()`, runtime wiring |
| `runtime/lifecycle.py` | Phase state machine (`STARTING/RUNNING/DEGRADED/STOPPING/STOPPED`) |
| `runtime/startup.py` | `StartupExecutor` — declarative 10-step boot |
| `runtime/shutdown.py` | `ShutdownExecutor` — 6-step stop |
| `runtime/state.py` | `RuntimeStateStore` → `runtime/runtime_state.json` |
| `runtime/configuration.py` | `RuntimeConfiguration` from `config/runtime/*.yaml` |
| `runtime/scheduler.py` | `JobScheduler` (cron/interval) |
| `runtime/heartbeat.py` | `HeartbeatManager` (5s) |
| `runtime/watchdog.py` | Stale detection |
| `runtime/health.py` | `HealthMonitor` |
| `runtime/metrics.py` | Metrics snapshot (1s refresh in main_loop) |
| `runtime/supervisor.py` | `Supervisor` — restart → isolate (ADR 0007) |
| `runtime/recovery.py` | `RecoveryManager` — per-engine restart factories |
| `runtime/circuit_breaker.py` | `CircuitBreaker` (sorted import before `configuration` — I001) |
| `runtime/process_manager.py` | `ProcessManager` — external processes |
| `runtime/diagnostics.py` | Diagnostics |
| `runtime/models.py` | Runtime data models |

### Run-Time Layer — COO (`orchestration/`)

| File | Purpose |
|---|---|
| `orchestration/engine.py` | `OrchestrationEngine` — plan → run → recover → record |
| `orchestration/planner.py` | `PipelinePlanner` — pipeline → plan |
| `orchestration/pipeline.py` | Pipeline definitions (stages, modes) |
| `orchestration/coordinator.py` | Holds all engine refs; dispatches by `task_type` |
| `orchestration/executor.py` | `TaskExecutor` — runs tasks via Coordinator |
| `orchestration/scheduler.py` | `OrchestrationScheduler` — due_plans polling |
| `orchestration/checkpoint.py` | `CheckpointManager` — snapshots |
| `orchestration/state.py` | `StateStore` + `ExecutionRecord` |
| `orchestration/recovery.py` | `RecoveryManager` — auto_recover retries |
| `orchestration/rollback.py` | Rollback support |
| `orchestration/monitoring.py`, `orchestration/health.py`, `orchestration/metrics.py` | Observability |
| `orchestration/notifications.py` | Notifications |
| `orchestration/dependencies.py` | Pipeline dependencies |
| `orchestration/config.py` | Orchestration config |
| `orchestration/models.py` | Plan/Stage/Task models |
| `orchestration/exceptions.py` | Orchestration exceptions |
| `orchestration/lifecycle.py` | Pipeline lifecycle |
| `orchestrator/` | Legacy-origin orchestrator (engine, executor, router, scheduler, state, workflow) — superseded by `orchestration/` |

### Run-Time Layer — Engines

| File | Purpose |
|---|---|
| `events/bus.py` | `EventBus` — pub/sub facade |
| `events/publisher.py` | `Publisher` + middleware pipeline |
| `events/router.py` | `Router` — subscriber matching |
| `events/dispatcher.py` | `Dispatcher` — thread pool (4 workers) |
| `events/subscriber.py` | `Subscriber` model |
| `events/middleware.py` | Logging/Validation/Metrics middleware |
| `events/priorities.py` | `PriorityProcessor` |
| `events/history.py` | `EventHistory` |
| `events/persistence.py` | JSONL persistence (`events/store.jsonl`) |
| `events/dead_letter.py` | `DeadLetterQueue` (`events/dead_letter.jsonl`) |
| `events/replay.py` | `ReplayRequest` + replay iteration |
| `events/filters.py` | Event filters |
| `events/registry.py` | Event type registry (from `config/events/event_registry.yaml`) |
| `events/models.py` | `Event` model |
| `events/config.py`, `events/exceptions.py`, `events/metrics.py` | Support |
| `memory/engine.py` | `MemoryEngine` — 6-type store, tiering, search, snapshots, knowledge |
| `memory/store.py` | InMemoryStore + JSONL stores |
| `memory/search.py`, `memory/retrieval.py` | Search/retrieval |
| `memory/embedding.py` | Embeddings |
| `memory/summary.py`, `memory/knowledge.py` | Summaries + knowledge base |
| `memory/snapshot.py`, `memory/archive.py` | Snapshots + archive |
| `memory/models.py` | Memory models |
| `decision/engine.py` | `DecisionEngine` — approval/risk/policy/routing |
| `decision/approval.py`, `decision/risk.py`, `decision/policy.py`, `decision/routing.py`, `decision/matrix.py` | Decision subsystems |
| `decision/models.py`, `decision/history.py` | Models + history |
| `workflow/state_machine.py` | Workflow state machines |
| `workflow/transitions.py`, `workflow/validators.py` | Transitions + validation |
| `workflow/loader.py`, `workflow/registry.py` | Workflow loading |
| `workflow/models.py`, `workflow/context.py`, `workflow/exceptions.py` | Support |

### Cross-Cutting

| File | Purpose |
|---|---|
| `services/runtime_facade.py` | `RuntimeFacade` — shared stable surface (ADR 0003) |
| `services/dashboard_events.py` | `DashboardEventBridge` — EventBus → asyncio queue |
| `api/app.py` | FastAPI app — read-only REST + WS (ADR 0002/0009), loopback-only |
| `telemetry/cli.py` | CLI invocation telemetry (fail-open JSONL) |
| `audit/` | session, logger, jsonl, events, metrics |
| `backup/` | `backup/backup.py` + `__main__.py` |
| `providers/` | base, factory, registry, openai, anthropic, gemini, ollama, mock |
| `agents/sync.py` | `AgentSyncEngine` — persona sync to OpenCode |
| `agents/slug_map.py` | `AgentSlugIndex` — deterministic slugs |
| `agents/template.py` | Agent template rendering |
| `agents/__main__.py` | `python -m ai_company.agents sync` (argparse) |
| `models/company.py` | `CompanyRegistry` (frozen) + company models |
| `utils/console.py` | Rich console helpers |

## Data: `config/`

| Tree | Files |
|---|---|
| `config/company/` | company.yaml (manifest), governance, strategy, budget, kpis, vision, culture, policies |
| `config/board/` | board.yaml, charters, committees, meetings, voting |
| `config/departments/` | template.yaml |
| `config/executives/` | template.yaml |
| `config/specialists/` | template.yaml |
| `config/workflows/` | budget_approval, hire_employee, incident_response, sprint_planning, template, workflow_registry |
| `config/decision/` | approval_matrix, decision_tree, risk_matrix |
| `config/events/` | event_pipeline, event_registry |
| `config/memory/` | memory.yaml |
| `config/orchestration/` | engine, scheduler, recovery, retries, checkpoints, dependencies, monitoring, notifications |
| `config/runtime/` | runtime, startup, scheduler, heartbeat, health, monitoring, recovery, diagnostics |

## Personas: `company/`

| File | Purpose |
|---|---|
| `company/company.yaml` | Company identity |
| `company/executives.yaml` | 13 executive personas (source of truth) |
| `company/specialists.yaml` | 17 specialist personas |
| `company/board.yaml` | 5 board personas |
| `company/departments.yaml` | Departments |
| `company/workflows.yaml` | Workflows |
| `company/policies.yaml` | Policies |

## Prompts & Templates

| Path | Purpose |
|---|---|
| `prompts/opencode/01_bootstrap_generator.md` … `08_constitution_loader.md` | OpenCode prompt library for `generate <target>` |
| `templates/README.md.j2` | Root README template |
| `templates/department_README.md.j2` | Department README |
| `templates/doc_placeholder.md.j2` | Doc placeholder |
| `templates/prompt_placeholder.md.j2` | Prompt placeholder |
| `templates/test_placeholder.py.j2` | Test placeholder |
| `templates/opencode/agents/architect.md` | Chief Architect agent (project scope) |
| `templates/opencode/agents/builder.md` | Lead Builder agent (project scope) |
| `templates/opencode/package.json`, `README.md` | OpenCode scaffolding |

## OpenCode Agents (`.opencode/agents/`)

| Agent | Purpose |
|---|---|
| `architect.md` | Architecture agent used by `generate` targets (ADR 0006; model `opencode/north-mini-code-free`, mode primary) |
| `builder.md` | Lead builder agent |

## Docs (`docs/`)

| File | Purpose |
|---|---|
| `adr/0001-0010-*.md` | Architectural decision records (see `.ai/decisions.md`) |
| `architecture.md`, `architecture-diagram.md` | Architecture overview + diagram |
| `STARTUP_SEQUENCE.md` | 10-step boot / 6-step shutdown |
| `RUNTIME_ENGINE.md` | Kernel module map, job catalog |
| `RUNTIME_LIFECYCLE.md` | Lifecycle state machine |
| `SUPERVISOR.md` | Supervisor/recovery detail |
| `EXECUTION_MODEL.md` | Orchestration plan/schedule/run/recovery |
| `ORCHESTRATION_ENGINE.md` | COO engine detail |
| `PIPELINES.md` | Task types, stage modes, built-in pipelines |
| `CHECKPOINTS.md` | Checkpoint save/restore |
| `RECOVERY.md` | Recovery strategies |
| `HEALTH_MONITORING.md` | Health/metrics |
| `OPERATIONS_RUNBOOK.md` | Daily ops + troubleshooting |
| `USER_GUIDE.md`, `EXECUTIVE_TEAM_GUIDE.md` | Guides |
| `OPENCODE_PROMPTS_GUIDE.md` | Prompt library guide |
| `memory-engine-design.md` | Memory engine design |

## Tests (`tests/`)

| File | Covers |
|---|---|
| `conftest.py` | Shared fixtures |
| `test_cli.py` | CLI commands |
| `test_command_map_integrity.py` | ADR 0006 contract |
| `test_registry.py` | Registry engine |
| `test_validator_engine.py` | 5-target validator |
| `test_bootstrap.py` | Bootstrap |
| `test_template_engine.py` | Template engine |
| `test_company_generator.py`, `test_board_generator.py`, `test_executive_generator.py`, `test_department_generator.py`, `test_specialist_generator.py`, `test_workflow_generator.py`, `test_doc_generator.py`, `test_prompt_generator.py`, `test_graph_exporter.py` | Generators |
| `test_generator_context.py` | Generator context |
| `test_executive.py` | Executive subsystem |
| `test_agents_sync.py` | Persona sync engine |
| `test_prompt_library.py` | Prompt library |
| `test_technical.py` | Technical checks |
| `tests/golden/` | Golden outputs |

## File Relationships (key paths)

| From | To | Why |
|---|---|---|
| `opencode.json` agent defs | `prompts/opencode/*.md` | `generate` dispatch (CI-validated, ADR 0006) |
| `config/orchestration/engine.yaml` | `orchestration/planner.py` | Pipeline definitions |
| `config/runtime/startup.yaml` | `runtime/startup.py` | Declarative boot |
| `company/*.yaml` | `agents/sync.py` → `~/.config/opencode/agents/` | Persona sync |
| `company/*.yaml` | `registry/registry.py` → `company/*generator.py` → `generated/` | Generation pipeline |
| `config/events/event_registry.yaml` | `events/registry.py` | Event schemas |
| `services/runtime_facade.py` | `api/app.py`, `cli/groups/runtime.py` | Shared runtime surface (ADR 0003) |
