# AI Enterprise OS — User Guide

How to install, run, and operate the AI Enterprise OS. The system is a
local, Python-based operating system for AI agent companies: it manages a
company registry (YAML data), generates organizational artifacts, persists
agent memory, orchestrates declarative pipelines, and boots a supervised
runtime that keeps every engine healthy.

Three things are operated here:

1. **The `ai-company` CLI** — the primary operator interface (build,
   validate, memory, graph, orchestrate, runtime).
2. **The web dashboard** — a browser UI served by `ai-company serve`
   (http://127.0.0.1:8000/) for health, telemetry, generate, decisions,
   and guarded operator actions. See
   [docs/DASHBOARD_GUIDE.md](DASHBOARD_GUIDE.md).
3. **Opencode** — the coding agent used to dispatch generation phases
   (`ai-company generate <target>`) and to run coding sessions against the
   project (agents, constitution loading, prompt library).

---

## 1. Overview

| Layer | Component | Purpose |
|---|---|---|
| Kernel | Enterprise Runtime Engine | Boot, supervise, recover, schedule, persist state |
| COO | Orchestration Engine | Plan/run/resume/retry/rollback declarative pipelines |
| Data | Registry Engine | Load & validate company YAML into an in-memory graph |
| Org | Company Generator | Build board, executives, departments, specialists, workflows, docs |
| Memory | Memory Engine | Long-term memory: save, search, snapshot, archive, retention |
| Reasoning | Decision Engine | Decisions with risk scoring, approvals, escalation |
| Workflow | Workflow Manager | Executable workflow steps |
| Ops | Validator Engine | 5-target validation (YAML, registry, templates, manifest, output) |
| Ext | Opencode | Dispatch phase generation; coding sessions |

Source lives in `src/ai_company/`; the full architecture is in
[docs/architecture.md](architecture.md) and
[docs/RUNTIME_ENGINE.md](RUNTIME_ENGINE.md).

---

## 2. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.12 | Project enforces `requires-python = ">=3.12"` |
| [uv](https://docs.astral.sh/uv/) | latest | Dependency sync + run environment |
| Opencode | latest | Required by `ai-company doctor`, `generate`, and agent sessions |
| LLM backend | — | Local models via Ollama (see `opencode.json`) or a cloud provider |

### 2.1 Install uv

```powershell
powershell -c "irm https://get.uv.io/install.ps1 | iex"
```

### 2.2 Sync dependencies

```powershell
uv sync --group dev
```

`--group dev` installs the dev toolchain (pytest, mypy, ruff, pre-commit)
used by the quality gates below.

### 2.3 Verify the environment

```powershell
uv run ai-company doctor
```

Expect `All checks passed. Environment is healthy.` — it confirms
`company/company.yaml` exists and `opencode` is on `PATH`. The same check
is baked into CI (`validate` job).

> **Models.** `opencode.json` at the repo root configures the agents
> (`build`, `plan`, `explore`, `general`) to use Ollama models, e.g.
> `ollama/llama3.1:8b`. Ensure Ollama is running (`http://localhost:11434`)
> and the models are pulled if you use those agents. Generation targets map
> to `opencode/north-mini-code-free` in
> `src/ai_company/cli/command_map.yaml` — edit that file to change models
> per target.

---

## 3. Project Layout

```
company/            # Company registry — source-of-truth YAML data
config/             # Configuration (non-registry)
  company/          #   manifest, vision, strategy, governance, kpis, budgets...
  runtime/          #   runtime engine config (8 YAML files)
  orchestration/    #   pipeline catalog + engine behavior (8 YAML files)
  memory/           #   memory engine config
  decision/         #   decision engine config
  events/           #   event registry
  ...               #   board, departments, executives, specialists, workflows
prompts/opencode/   # OpenCode prompt files used by `ai-company generate`
templates/          # Jinja2 templates for generated artifacts
generated/          # Generated output (gitignored)
memory/             # Memory engine store (store.jsonl, gitignored)
runtime/            # Persisted runtime state (runtime_state.json, gitignored)
src/ai_company/     # Package source
tests/              # Unit + integration + e2e tests
docs/               # Design and ops documentation
scripts/            # Utility scripts (e.g. readiness assessment)
```

---

## 4. First-Time Bootstrap

Two paths produce the full company artifact set.

### 4.1 Offline (templates + registry only, no LLM needed)

```powershell
uv run ai-company build
```

Runs the bootstrap scaffold, generates every artifact from the templates
and registry data, then runs the full Validator Engine. Output ends with
`Build complete.`

### 4.2 LLM-assisted (Opencode dispatch)

```powershell
uv run ai-company bootstrap        # scaffold + generate from registry
uv run ai-company generate company # dispatch org generation to Opencode
```

`generate` renders the target's prompt file through the template engine
(writing `.ai-company/.tmp_rendered_prompt.md`) and streams an Opencode run
with the mapped agent and model. See [§8 Opencode Integration](#8-opencode-integration).

### 4.3 What "complete" looks like

After bootstrap, the Validator Engine reports:

```
Validator Engine [PASSED]  17 checks, 0 errors, 0 warnings across 5 target(s)
  PASS yaml:registry
  PASS registry
  PASS templates
  PASS manifest
  PASS generated_output
```

---

## 5. CLI Command Reference

```
ai-company [OPTIONS] COMMAND [ARGS]...

  bootstrap  Scaffold the project structure and generate the full company.
  build      Build all generated artifacts from templates and registry data.
  generate   Dispatch a phase to OpenCode using its mapped prompt file.
  validate   Validate company registry data and configuration files.
  doctor     Diagnose environment and configuration issues.
  targets    List available generate targets.
  status     Show current system status overview.
  company    Company organization commands — generate, validate, report, board
  exec       Executive team commands — list, show, org-chart, agent
  registry   Manage the company registry (YAML data)
  memory     Persistent memory engine operations
  graph      Query and export the company graph
  report     Generate reports from registry and state data
  orchestrate  Enterprise Orchestration Engine (COO pipelines)
  runtime    Enterprise Runtime Engine (boot & supervision)
```

### 5.1 Top-level commands

| Command | What it does |
|---|---|
| `ai-company bootstrap` | Scaffold the repo structure + generate all artifacts + validate |
| `ai-company build` | Rebuild generated artifacts from templates/registry + validate |
| `ai-company generate <target>` | Dispatch a phase to Opencode (see §8) |
| `ai-company validate` | Run the full Validator Engine (exit code 1 on failure) |
| `ai-company doctor` | Check environment: company.yaml, opencode, Python |
| `ai-company targets` | List valid `generate` targets |
| `ai-company status` | Registry file count, generated artifact count, opencode availability |

### 5.2 `company` group — org generation

| Command | What it does |
|---|---|
| `company generate` | Build the full organization hierarchy + write `generated/*` artifacts |
| `company validate` | Verify the registry can produce a valid organization |
| `company report` | Summary report of the current organization |
| `company board_generate` / `board_validate` / `board_report` | Board governance artifacts |
| `company exec_generate` / `exec_validate` | Executive artifact packages |
| `company dept_generate` / `dept_validate` | Department artifacts |
| `company specialist_generate` / `specialist_validate` | Specialist agent artifacts |
| `company workflow_generate` / `workflow_validate` | Workflow artifacts |
| `company prompt_generate` / `prompt_validate` | Prompt library artifacts |
| `company docs_generate` / `doc_validate` | Documentation artifacts |

Artifacts land under `generated/` (e.g. `organization.json`,
`docs/ORGANIZATION.md`, `board.yaml`, `executives/*/executive.yaml`,
`departments/*/README.md`, `specialists/*/profile.md`,
`workflows/*/workflow.md`, `prompts/*.md`).

### 5.3 `exec` group — executive team

| Command | What it does |
|---|---|
| `exec list` | List executives with title, department, KPIs, status dot |
| `exec show <name>` | Full profile: reports-to, budget, KPIs, direct reports, agent config |
| `exec org_chart` | Print + write a Mermaid org chart to `generated/org_chart.md` |
| `exec agent <name>` | Generate and print the full agent prompt for an executive |

### 5.4 `registry` group

| Command | What it does |
|---|---|
| `registry list` | Vision, departments+roles, board, executives, policies, specialists, workflows |
| `registry show <name>` | Details for `vision`, `departments`, `board`, `executives`, `policies`, `specialists`, `workflows` |
| `registry verify` | Load every YAML file and confirm consistency |

### 5.5 `memory` group

| Command | What it does |
|---|---|
| `memory save <content> [--type --namespace --tags --source --importance --parent]` | Store a memory entry (JSON or plain text) |
| `memory get <id>` | Retrieve one entry with full metadata |
| `memory update <id>` | Update content/tags/importance (versioning) |
| `memory delete <id>` | Delete an entry |
| `memory search <query> [--type --namespace --tags --limit --min-importance --include-archived --json]` | Semantic/keyword search |
| `memory list [--type --namespace --limit]` | List entries |
| `memory archive <id>` / `unarchive <id>` | Archive / restore an entry |
| `memory archive_old <days>` | Archive entries older than N days |
| `memory purge` | Permanently delete archived memories |
| `memory snapshot <name>` / `snapshots` / `restore <snapshot-id>` | Point-in-time backup & restore |
| `memory show` / `stats` | Summary / detailed statistics |
| `memory clear` | Wipe ALL memories (interactive confirm) |
| `memory export <path>` | Export all memories to JSON |
| `memory apply_retention` | Run the configured retention policy (archive/purge) |

Storage defaults to `memory/store.jsonl` unless
`config/memory/memory.yaml` exists (it is used when present).

### 5.6 `graph` group

| Command | What it does |
|---|---|
| `graph show` | Print the company graph: vision, departments → roles, board, edge count |
| `graph stats` | Nodes, edges, density, unresolved references |
| `graph export` | Write Mermaid diagram + enriched JSON to `generated/` |

### 5.7 `report` group

| Command | What it does |
|---|---|
| `report generate summary` | Company-level summary (depts, roles, board, workflows) |
| `report generate detailed` | Vision, every department+role, board, executives, workflows |
| `report generate health` | Validator Engine pass/fail per target |

---

## 6. Orchestration (COO pipelines)

Pipelines are declarative, versioned stage/task sequences defined in
`config/orchestration/engine.yaml`. The Orchestration Engine coordinates
the other engines (registry, generator, validator, memory, audit, ...); it
never implements business logic itself.

### 6.1 Built-in pipelines

| Pipeline | Stages |
|---|---|
| `bootstrap` | registry → generation → validation → parallel persistence/audit |
| `generation` | registry → parallel prompt/docs/graph generation → persistence/audit |
| `report` | registry → graph build + reporting analysis → audit |

### 6.2 CLI reference

| Command | What it does |
|---|---|
| `orchestrate plan <pipeline> [--file --schedule-mode --interval --max-runs]` | Create a plan without executing it; prints the plan id |
| `orchestrate start <pipeline>` | Start a plan; immediate plans run synchronously and print task metrics |
| `orchestrate status [plan-id]` | Engine status + optional plan execution state |
| `orchestrate resume <plan-id> [--checkpoint-id]` | Resume a failed/interrupted plan from its latest checkpoint |
| `orchestrate retry <plan-id>` | Re-run a failed plan from scratch |
| `orchestrate rollback <plan-id> [--reason]` | Execute registered undo handlers in reverse order |
| `orchestrate history [plan-id] [--limit]` | Execution history (from Memory) |

Example — run the full bootstrap pipeline:

```powershell
uv run ai-company orchestrate start bootstrap
```

Example — plan only (no execution), then check it:

```powershell
uv run ai-company orchestrate plan bootstrap
uv run ai-company orchestrate status <plan-id>
```

Schedule modes: `immediate` (default, synchronous), `scheduled` (once at a
time), `recurring` (every `--interval` seconds up to `--max-runs`),
`dependency` (after listed plans complete). Non-immediate plans register
with the in-process scheduler.

### 6.3 Recovery on failure

Default behavior (`recovery.auto_recover: false`) leaves a failed plan
`FAILED` for manual action:

- `orchestrate resume <plan-id>` — restore latest checkpoint, continue.
- `orchestrate retry <plan-id>` — fresh run.
- `orchestrate rollback <plan-id>` — undo completed side effects.

Set `auto_recover: true` in `config/orchestration/recovery.yaml` to run the
`checkpoint_first → rollback → retry` strategy automatically (capped by
`max_recovery_attempts`). See [docs/RECOVERY.md](RECOVERY.md) and
[docs/CHECKPOINTS.md](CHECKPOINTS.md).

---

## 7. Runtime Engine (daily operations)

The runtime is the kernel. It boots the 5 engines, runs 5 scheduled jobs,
monitors health, supervises recovery, and persists state.

### 7.1 Start the company

```powershell
uv run ai-company runtime start
```

Runs the 11-step startup sequence, prints the boot summary (phase, startup
success, engines, scheduled jobs), then **blocks** in the foreground.
Stop with Ctrl-C (triggers a graceful shutdown).

### 7.2 Inspect in a second terminal

```powershell
ai-company runtime status
```

Expected on a normal boot:

```
Runtime Status:
  Name: AI Enterprise Runtime (v1.0)
  Phase: running
  Engines (5): memory, event_bus, decision, workflow, orchestration
  Scheduled jobs: 5
```

Note: `runtime status` (and `health`/`metrics`/`diagnostics`/`reload`) boot
a fresh runtime for the check and shut it down in `finally`, so they can be
run without a foreground `start`.

### 7.3 Stop / restart

```powershell
ai-company runtime stop              # graceful shutdown sequence
ai-company runtime restart           # stop, then boot again
```

`stop` runs scheduler → watchdog → supervisor → engines → state persist →
finalize, and writes `runtime/runtime_state.json`.

### 7.4 Health

```powershell
ai-company runtime health
```

6 healthy checks on a normal boot (memory, event_bus, decision, workflow,
orchestration, system). `DEGRADED` means a system threshold was crossed
(CPU/memory/queue/error rate); `UNHEALTHY` means a probe failed — the
supervisor attempts recovery.

### 7.5 Metrics

```powershell
ai-company runtime metrics
```

CPU/memory, active/healthy/failed engines, heartbeat misses, error rate,
job counters, queue sizes, timers.

### 7.6 Diagnostics

```powershell
ai-company runtime diagnostics
```

Full report: phase, uptime, engines, health checks, 8 config sections with
checksums, warnings, errors, recommendations.

### 7.7 Hot reload

```powershell
ai-company runtime reload
```

Re-reads all 8 runtime YAML configs and reports changed sections by
checksum. Scheduler jobs are re-registered from `scheduler.yaml`; other
sections are re-applied where supported — no reboot needed for most config
changes.

### 7.8 Scheduled jobs (run automatically while `start` is alive)

| Job | Schedule | Kind |
|---|---|---|
| Daily executive briefing | `cron 0 7 * * *` | event publish |
| Weekly KPI report | `cron 0 9 * * 1` | orchestrate pipeline |
| Monthly board meeting | `cron 0 10 1 * *` | event publish |
| Quarterly strategy review | `cron 0 11 1 1,4,7,10 *` | event publish |
| Continuous memory consolidation | every 3600s | memory consolidation |

### 7.9 Runtime configuration

All runtime config lives in `config/runtime/` and is hot-reloadable:

| File | Controls |
|---|---|
| `runtime.yaml` | identity, state_dir, persistence, loop cadence, concurrency |
| `startup.yaml` | ordered startup steps |
| `scheduler.yaml` | job catalog, worker cadence |
| `heartbeat.yaml` | liveness thresholds |
| `monitoring.yaml` | observability switches |
| `health.yaml` | probe + system thresholds |
| `recovery.yaml` | recovery policies (engine/process) |
| `diagnostics.yaml` | report assembly |

See [docs/OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md),
[docs/STARTUP_SEQUENCE.md](STARTUP_SEQUENCE.md), and
[docs/HEALTH_MONITORING.md](HEALTH_MONITORING.md).

---

## 8. Opencode Integration

### 8.1 `ai-company generate <target>` flow

1. Resolve the target in `src/ai_company/cli/command_map.yaml`.
2. Render the target's prompt file (`prompts/opencode/*.md`) through the
   template engine with the company manifest context →
   `.ai-company/.tmp_rendered_prompt.md`.
3. Invoke Opencode:

   ```
   opencode run --file <rendered prompt> --agent <agent> --model <model> \
     "Execute the attached prompt against the current company registry."
   ```

4. Stream output to the console; exit code is propagated.

Use `--dry-run` to print the command without executing it:

```powershell
uv run ai-company generate exec --dry-run
```

### 8.2 Targets

| Target | Generates |
|---|---|
| `bootstrap` | Initial repository structure |
| `registry` | In-memory company graph from YAML |
| `company` | Full organization hierarchy + artifacts |
| `board` | Board governance artifacts |
| `exec` | Executive artifact packages |
| `dept` | Department artifacts |
| `specialist` | Specialist agent artifacts |
| `workflow` | Workflow artifacts |
| `prompt` | Prompt library artifacts |
| `docs` | Documentation artifacts |
| `graph` | Organizational graphs |

List at runtime: `ai-company targets`.

### 8.3 Agents

Custom agents live in `.opencode/agents/`:

| Agent | Role |
|---|---|
| `architect` | Chief Architect — designs robust, scalable architectures |
| `builder` | Lead Builder — writes production-ready, executable Python |

The agents' LLM backends are configured in `opencode.json`
(`agent.<name>.model`). Generation targets override the agent/model per
target in `command_map.yaml`.

### 8.4 Constitution loader

`prompts/opencode/08_constitution_loader.md` instructs every OpenCode
session to begin by loading `.ai-company/constitution` and `.ai-company/state`
(current sprint, milestone, architecture status, technical debt, next
actions, project health) before implementation, and to update the state,
dashboard, changelog, sprint, technical debt, and release notes at the end
of the session. Keep `.ai-company/state/` current as part of your operating
routine when working through Opencode.

### 8.5 Hands-on coding with Opencode

The repo is Opencode-native: `opencode.json` and `.opencode/agents/` are
present, `doctor` verifies the `opencode` binary, and `generate` drives it.
You can also open the project directly:

```powershell
opencode        # interactive session in this directory
opencode run "<task>"  # one-shot
```

When you ask an agent to modify code, tell it to finish by running the
quality gates in [§9](#9-quality-gates) so CI stays green.

---

## 9. Quality Gates

Run these before every push; they mirror the CI workflow exactly.

```powershell
uv run --group dev ruff check            # lint
uv run --group dev ruff format --check   # formatting
uv run --group dev mypy src              # strict type-check
uv run --group dev pytest                # unit + integration + e2e
uv run ai-company build                  # regenerate artifacts
uv run ai-company validate               # registry/config/manifest/output validation
uv lock --check                          # lockfile freshness
```

Pre-commit hooks (`.pre-commit-config.yaml`) enforce trailing-whitespace,
EOF fixes, YAML/JSON/TOML validity, secrets detection, ruff lint+format,
and strict mypy on commit — run `uv run --group dev pre-commit run --all-files`
to check before committing.

CI (`.github/workflows/ci.yml`) runs `lint`, `type-check`, `test`,
`validate`, and on main also `build`. Release automation lives in
`.github/workflows/release.yml`.

---

## 10. State & Data Files

| Path | Contents | Managed by |
|---|---|---|
| `company/*.yaml` | Source-of-truth registry (edit freely, then `validate`) | you |
| `config/**/*.yaml` | Engine behavior (runtime, orchestration, memory, decision, events) | you |
| `generated/` | Build output (gitignored) | `build`, `company *`, `graph export` |
| `memory/store.jsonl` | Memory entries (gitignored) | memory engine |
| `runtime/runtime_state.json` | Persisted runtime state (gitignored) | runtime engine |
| `.ai-company/state/` | Sprint/milestone/project health for Opencode sessions | you + agents |
| `.ai-company/constitution/` | Session constitution | you |
| `reports/`, `events/`, `slides/`, `scripts/`, `memory/` | Generated/runtime data (root-level gitignored) | tools & tests |

To reset runtime state cleanly: stop the runtime, then delete
`runtime/runtime_state.json` (the engine re-creates it on next boot).

---

## 11. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `Startup failed at step ...` | A startup step raised; runtime transitions to `failed`. Read the step name, fix config, re-run `runtime start` |
| `Component X isolated` in logs | Recovery failed (no policy, no restart mechanism, attempts exhausted). Fix the cause, then re-admit with the supervisor's `unisolate` (programmatic) or restart |
| `Max attempts (...) exceeded` | `recovery.yaml` cap hit; component isolated to stop recovery loops. Fix root cause and restart |
| `Could not recover runtime state from disk` | `runtime/runtime_state.json` missing/corrupt; runtime starts fresh (informational warning). Delete the file to reset |
| `EventBus not started` noise | Events degrade to local dispatch during shutdown — expected |
| State not recovered across boots | Verify `runtime.persist_state: true` and `startup.recover_persisted_state: true` |
| `Could not find 'opencode' on PATH` | Install Opencode and re-run `ai-company doctor` |
| `generate` fails with model errors | Check the LLM backend: Ollama up? model pulled? `command_map.yaml` model id correct? |
| Plan stuck `FAILED` | `orchestrate status <plan-id>` → `resume` from checkpoint, or `retry`, or `rollback` |
| Memory search returns nothing | Check namespace/type filters; run `memory stats`; archived entries are excluded unless `--include-archived` |

---

## 12. Day-to-Day Operating Checklist

```powershell
# 1. Health check before starting work
uv run ai-company doctor

# 2. Boot the company (foreground, Ctrl-C to stop) — or run checks standalone
uv run ai-company runtime start
# in another terminal:
uv run ai-company runtime status
uv run ai-company runtime health

# 3. Rebuild + validate after any registry/config edit
uv run ai-company build
uv run ai-company validate

# 4. Run pipelines
uv run ai-company orchestrate start generation

# 5. Inspect memory / graph / reports as needed
uv run ai-company memory stats
uv run ai-company graph show
uv run ai-company report generate health

# 6. Optional — open the web dashboard (read + guarded writes)
uv run ai-company serve           # then browse to http://127.0.0.1:8000/
uv run ai-company dashboard token create   # one-time write-token setup (§3.1 of the Dashboard Guide)

# 7. Before pushing — quality gates (§9)
uv run --group dev pre-commit run --all-files
uv run --group dev pytest
```

---

## 13. Related Documentation

- [OPERATIONS_RUNBOOK](OPERATIONS_RUNBOOK.md) — runtime CLI daily operations
- [DASHBOARD_GUIDE](DASHBOARD_GUIDE.md) — start, access, and use the web dashboard
- [RUNTIME_ENGINE](RUNTIME_ENGINE.md) — kernel overview, engines, jobs
- [STARTUP_SEQUENCE](STARTUP_SEQUENCE.md) — boot/shutdown steps
- [RUNTIME_LIFECYCLE](RUNTIME_LIFECYCLE.md) — phase machine, persisted state
- [SUPERVISOR](SUPERVISOR.md) — failure detection, recovery, isolation
- [HEALTH_MONITORING](HEALTH_MONITORING.md) — probes, heartbeats, metrics
- [ORCHESTRATION_ENGINE](ORCHESTRATION_ENGINE.md) — COO pipelines
- [PIPELINES](PIPELINES.md) — pipeline schema, handlers, stage modes
- [EXECUTION_MODEL](EXECUTION_MODEL.md) — plan scheduling, lifecycle, retries
- [RECOVERY](RECOVERY.md) — recovery strategies and actions
- [CHECKPOINTS](CHECKPOINTS.md) — snapshot & resume semantics
- [memory-engine-design](memory-engine-design.md) — memory engine internals
- [architecture](architecture.md) / [architecture-diagram](architecture-diagram.md)
