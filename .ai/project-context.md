# Project Context

> **Purpose:** Everything an agent needs to know about the project before
> working: identity, structure, conventions, commands, and history.

## Identity

| Field | Value |
|---|---|
| **Name** | AI Enterprise OS (`ai-company`) |
| **Version** | 0.1.0 |
| **Description** | Scalable local AI agent workflows |
| **Company** | Lightspeed Holdings Limited |
| **Python** | `>=3.12` (3.12 only — `X \| None` syntax, Pydantic v2) |
| **Build** | `hatchling` (wheel packages `src/ai_company`) |
| **Dependency tool** | `uv` (lockfile `uv.lock` committed) |
| **CLI entry** | `ai-company = "ai_company.cli.main:app"` (Typer) |

## Core Dependencies (`pyproject.toml`)

- **Runtime:** `typer>=0.27`, `rich>=15`, `Jinja2>=3.1.6`, `PyYAML>=6.0.3`,
  `pydantic>=2.13.4`, `python-dotenv`, `networkx>=3.6.1`, `shellingham`,
  `croniter`, `fastapi>=0.141.1`, `uvicorn>=0.52.0`, `websockets>=17.0.1`
- **Dev group:** `pytest>=9.1.1`, `mypy>=2.3.0`, `ruff>=0.16.0`,
  `pre-commit>=4.6.1`, `types-pyyaml`, `httpx`

## Repository Layout (top level)

```
.ai/              ← THIS knowledge base (committed — agent single source of truth)
.ai-company/      ← constitution, sprint state, templates (gitignored)
.opencode/        ← project-scope OpenCode agents (architect, builder)
.github/workflows/← ci.yml, nightly-backup.yml, release.yml
company/          ← persona source YAML (executives, specialists, board, departments, policies, workflows)
config/           ← declarative runtime/orchestration/events/memory/decision/workflow config YAML
diagrams/         ← data-flow diagrams (Level 0/1/2)
docs/             ← ADRs + operational docs (STARTUP_SEQUENCE, EXECUTION_MODEL, PIPELINES, ...)
generated/        ← build output (gitignored, 314 artifacts)
prompts/opencode/ ← OpenCode prompt library (01..08)
src/ai_company/   ← all source code
templates/        ← Jinja2 templates (README, placeholders, opencode agents)
tests/            ← pytest suite
```

## CLI Command Reference (frozen tree — ADR 0006)

| Command | Purpose |
|---|---|
| `ai-company bootstrap` | Scaffold initial repo structure (placeholders) |
| `ai-company build` | Build generated artifacts |
| `ai-company generate <target>` | Dispatch a phase to OpenCode |
| `ai-company validate` | Validate registry/config/generated output |
| `ai-company validator engine` | Full 5-target Validator Engine |
| `ai-company doctor` | Diagnose environment and configuration |
| `ai-company targets` | List generate targets |
| `ai-company status` | System status overview |
| `ai-company registry list\|show\|verify` | Registry introspection |
| `ai-company memory show\|clear` | Memory state |
| `ai-company graph show\|stats` | Company graph |
| `ai-company report generate <type>` | Reports |
| `ai-company executive ...` | Executive subsystem commands |
| `ai-company runtime ...` | Runtime kernel: `start`, `stop`, `restart`, `status`, `reload`, `health`, `metrics`, `scheduler`, `supervisor` |
| `ai-company orchestrate ...` | COO: `start`, `stop`, `status`, `plans`, `records`, `jobs`, `recover`, `rollback` |
| `ai-company serve` | Dashboard API server (uvicorn, loopback-only) |

> Note: `python -m ai_company.agents sync` is deliberately NOT in the Typer
> tree — it's a standalone argparse entry point invoked ad-hoc.

## Configuration (declarative YAML — `config/`)

| Area | Files | Purpose |
|---|---|---|
| Company | `company/company.yaml`, `governance.yaml`, `strategy.yaml`, `budget.yaml`, `kpis.yaml`, `vision.yaml`, `culture.yaml`, `policies.yaml` | Manifest + company data |
| Board | `board/*.yaml` | charters, committees, meetings, voting |
| Departments/Execs/Specialists | `departments/template.yaml`, `executives/template.yaml`, `specialists/template.yaml` | Persona templates |
| Workflows | `workflows/*.yaml` | budget_approval, hire_employee, incident_response, sprint_planning |
| Decision | `decision/approval_matrix.yaml`, `decision_tree.yaml`, `risk_matrix.yaml` | Approval/risk rules |
| Events | `events/event_registry.yaml`, `event_pipeline.yaml` | Event schemas + pipeline |
| Memory | `memory/memory.yaml` | Tiering, retention, importance |
| Orchestration | `orchestration/*.yaml` | engine, scheduler, recovery, retries, checkpoints, dependencies, monitoring, notifications |
| Runtime | `runtime/*.yaml` | runtime, startup, scheduler, heartbeat, health, monitoring, recovery, diagnostics |

## Tooling & Quality Gates

| Tool | Config | Enforcement |
|---|---|---|
| **ruff** | target py312; 14 ignores w/ rationale (BLE001, C401, C408, DTZ005/6, RUF012/15/22/59, S110, SIM102/3/14, TC005) | pre-commit + CI |
| **mypy** | `strict = true`; 13 documented `disable_error_code` entries | pre-commit (`uv run --group dev mypy --strict src/`) + CI |
| **pre-commit** | trailing-whitespace, end-of-file-fixer, large files (500KB), yaml/json/toml checks, merge-conflict, symlinks, private-key, mixed-line-ending (lf), ruff, mypy | local hooks; **excludes** `generated/` and `.ai-company/` |
| **pytest** | minversion 9.0; `testpaths = tests`; `pythonpath = src` | `uv run --group dev pytest` |
| **CI** | lint + mypy + tests (Windows matrix) + command-map integrity + `uv audit` | `.github/workflows/ci.yml` |
| **Backups** | nightly backup workflow; `ai-company backup` | `.github/workflows/nightly-backup.yml` |

## Git Hygiene

- Branch: `main`; commits follow `feat:` / `fix:` / `chore:` prefixes.
- `.gitignore` covers: `.ai-company/`, `.benchmarks/`, `generated/`, `test_output/`,
  `dist/`, `.opencode/`, `/runtime/`, `/events/`, `/memory/`, `/reports/`,
  `/scripts/`, `/slides/`, `.env*`, `uv.lock` — **`.ai/` is NOT ignored: commit it.**
- Pre-commit must pass before push; CI validates the command map ↔ prompts ↔
  `opencode.json` contract (ADR 0006).

## Sprint History

| Sprint | Status | Deliverable |
|---|---|---|
| Sprint 4.5 | ✅ | Enterprise Orchestration Engine (COO layer) — `c37f867` |
| Sprint 4.6 | ✅ | Enterprise Runtime Engine (kernel/OS layer) — `f100d3b` |
| Phase 0 | ✅ | Command centers: telemetry, backup, integrity gate, self-healing — `3324dbf`; close-out (Windows CI, live recovery drill) — `27348a1` |
| Phase 1 Wave 1 | ✅ | Dashboard API server, read-only contract v1 — `b6d5a26` / `6d2654b` |
| Sprint 5.1 | ✅ | OpenCode persona agents (35) + global sync engine — `current_sprint.yaml` |
| Phase 1 Wave 2 | ✅ | Dashboard frontend v1 (8 views, scoped CSP, parity seed) — `d0b1385` |
| Sprint 5.2 Wave 2a | ✅ | Phase 2 write auth (ADR 0010) + operational write endpoints — see `.ai/current-work.md` |
| Next | ⬜ | Phase 2 Wave 2b: generate dispatcher → OpenCode, decision/approval inbox, then SQLite read model (Sprint 5.4) — see `.ai/current-work.md` |

## ADR Index (see `.ai/decisions.md` for rationale; full text in `docs/adr/`)

- **0001** Dashboard & OpenCode as primary command centers — Accepted
- **0002** Dashboard backend: FastAPI + plain uvicorn + WebSocket — Accepted
- **0003** Shared services layer (CLI, API, dashboard thin adapters) — Accepted
- **0004** SQLite (WAL) derived read model for dashboard reads — Accepted
- **0005** CLI retained as automation contract — Accepted
- **0006** Command map enforced contract (CI integrity check) — Accepted
- **0007** Supervisor self-healing: restart before isolate — Accepted
- **0008** Dashboard frontend: Jinja2 + htmx (v1), Svelte 5 (v2) — Accepted (v1)
- **0009** Dashboard API contract: REST + WS, replay-based reconnect — Accepted
- **0010** Phase 2 write auth: bearer token + CSRF + audit — **Accepted** (Wave 2a shipped 2026-08-01)

## Constitution (`.ai-company/constitution/rules.md`) — immutable

1. **Read State First:** every session MUST read
   `.ai-company/state/current_sprint.yaml` before writing code.
2. **Always use Pydantic v2** for data validation and schemas.
3. **Never use pseudo-code or placeholders** in production files.
4. **Strict Typing:** all Python modules use standard `typing`.
5. **Update State Last:** update sprint state upon completion.

## Environment

- **Provider:** Ollama local (`http://localhost:11434/v1`) — see `opencode.json`
- **Default model:** `ollama/llama3.1:8b`; small: `ollama/qwen2.5-coder:7b`
- **OpenCode agents:** build (default), plan, explore, general, architect
  (primary, `opencode/north-mini-code-free`)
- **Permissions:** bash/edit → ask

## Quick Reference (commands)

```bash
uv sync --group dev                  # install
uv run ai-company --help             # CLI help
uv run --group dev pytest -xvs       # tests
uv run --group dev ruff check src/   # lint
uv run --group dev mypy --strict src/  # type-check
pre-commit run --all-files           # all hooks
python -m ai_company.agents sync     # sync personas to ~/.config/opencode/agents/
ai-company runtime start             # boot kernel
ai-company serve                     # dashboard API on 127.0.0.1:8000
```
