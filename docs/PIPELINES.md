# Pipelines

A **pipeline** is a declarative, versioned sequence of stages. Each stage
declares an execution mode and a list of tasks; each task names the engine
that owns it plus parameters. Pipelines are defined in
`config/orchestration/engine.yaml` under `pipelines:` and loaded by the
`PipelinePlanner`.

## Structure

```yaml
pipelines:
  <pipeline-id>:
    description: "..."
    version: "1.0"
    stages:
      - id: "<stage-id>"
        name: "Human readable"
        mode: "sequential"        # sequential | parallel | conditional
        tasks:
          - id: "<task-id>"
            name: "Human readable"
            task_type: "<handler>"   # dispatch key for the Coordinator
            engine: "<engine-name>"  # coordinated engine (informational)
            params: { ... }          # handler-specific parameters
```

## Built-in Pipelines

### `bootstrap` — full company bootstrap

Registry load → full generation → validation → parallel persistence/audit.

| Stage | Mode | Tasks |
|---|---|---|
| `registry` | sequential | `load_registry` (action: load) |
| `generation` | sequential | `generate_all` (target: all) |
| `validation` | sequential | `validate` (action: all) |
| `persistence` | parallel | `save_memory` (memory_type: company), `audit_bootstrap` (event_type: bootstrap) |

### `generation` — regenerate artifacts

Registry load → parallel prompt/docs/graph generation → persistence/audit.

| Stage | Mode | Tasks |
|---|---|---|
| `registry` | sequential | `load_registry` |
| `generation` | parallel | `generate_prompts`, `generate_docs`, `generate_graph` |
| `persistence` | sequential | `save_memory`, `audit_generation` |

### `report` — reporting-structure analysis

Registry load → graph build + reporting analysis → audit.

| Stage | Mode | Tasks |
|---|---|---|
| `registry` | sequential | `load_registry` |
| `analysis` | sequential | `graph_build` (action: build), `report` (action: analyse) |
| `audit` | sequential | `audit_report` (event_type: report) |

## Task Handlers

Tasks are dispatched by `task_type` to the Coordinator's default handlers
(any of which can be overridden with `register_handler`):

| task_type | Engine used | Params | Result keys |
|---|---|---|---|
| `load_registry` | registry | `action` | `success`, `executives`, `departments`, `specialists`, `workflows`, `warnings` |
| `generate` | generator | `target` (all/board/executives/departments/specialists/workflows/prompts/docs/graph/org) | `success`, `target` + generator summary |
| `validate` | validator | `action` | `success`, `summary` |
| `memory_save` | memory | `content`, `memory_type` (default system), `namespace` (default global), `tags`, `source`, `metadata` | `success`, `memory_id` |
| `memory_search` | memory | `query`, `namespace`, `limit` | `success`, `count`, `ids` |
| `audit_record` | audit | `event_type`, `engine`, `module`, `action`, `result`, `error`, `metadata` | `success`, `audit_event` |
| `decision` | decision | `title`, `description`, `requester`, `tags` (or none → statistics) | `success`, `decision_id` / `statistics` |
| `workflow` | workflow | `name` (or none → list) | `success`, `workflow` + `steps` / `count` + `workflows` |
| `graph_build` | graph (OrganizationGenerator) | `action` | `success`, `nodes`, `edges`, `max_depth`, `orphans`, `cycles`, `warnings` |
| `report` | reporting (OrganizationGenerator) | `action` | `success`, `nodes`, `edges`, `max_depth`, `span_of_control`, `orphans`, `cycles`, `warnings` |
| `event_publish` | event bus | `event_type`, `payload`, `source` | `success` |
| `noop` | — | — | `success` |

## Stage Modes

| Mode | Behavior |
|---|---|
| `sequential` | Tasks run one after another; a failure fails the stage |
| `parallel` | Tasks run concurrently, capped by `dependencies.max_parallel_tasks` |
| `conditional` | Tasks with a `condition` (dotted path over task results, e.g. `load_registry.success == true`) run only when it evaluates true; otherwise they are skipped |

## Task Results

Task outputs are recorded in `ExecutionState.task_results[task_id]` and are
referenceable by later conditions and recovery. Checkpoints snapshot results
when `checkpoints.include_task_results` is enabled.

## Adding a Pipeline

1. Add a `<pipeline-id>` block under `pipelines:` in
   `config/orchestration/engine.yaml`.
2. Reuse existing `task_type`s (prefer composition over new handlers).
3. For a new capability, register a handler:
   `engine.register_handler("my_task_type", my_handler)`.
4. Verify with `ai-company orchestrate plan <pipeline-id>`.

Planner merge semantics: config-declared pipelines override same-named
built-ins; built-ins are only used as fallbacks when the config omits a name
(`planner.config_pipelines()` / `planner.builtin_pipelines()`).
