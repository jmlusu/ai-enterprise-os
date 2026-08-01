# Architectural Decisions

> **Purpose:** Log of key architectural decisions made in this project, with
> status, date, deciders, and rationale. This is the living ADR index. For
> full ADR text, see `docs/adr/`. **Update this file after each commit that
> introduces an architectural decision.**

## How to Use This File

1. **Before making a significant change**, check if there's an existing ADR
   that covers it (search by the decision title or topic).
2. **When you make a decision**, add a row here with status `Proposed` and
   create the full ADR in `docs/adr/` using the `NNNN-` filename convention.
3. **During review**, update the status to `Accepted`, `Rejected`, or
   `Superseded`.
4. **Each commit** that changes architecture should reference the relevant
   ADR number.

## ADR Index

| # | Title | Status | Deciders | Summary |
|---|---|---|---|---|
| 0001 | Dashboard & OpenCode as the primary command centers | Accepted | CTO, Chief of Staff, Architecture (12-expert analysis) | CLI stays; Dashboard is primary human face; OpenCode desktop is primary agent face |
| 0002 | Dashboard backend: FastAPI + uvicorn (plain) + WebSocket | Accepted | CTO, Cloud Architecture, SWE | FastAPI for REST+WS; plain uvicorn (no uvloop — Windows-safe); thread executor bridges sync runtime |
| 0003 | Shared services layer (CLI, API, dashboard are thin adapters) | Accepted | CTO, SWE, Data Engineering | `services/` layer holds business logic; CLI/API/OpenCode are thin adapters |
| 0004 | SQLite (WAL) derived read model for dashboard reads | Accepted | CDO, Data Engineering, Cloud Architecture | JSONL/JSON remain source of truth; SQLite is a rebuildable read projection with WAL for concurrent dashboard reads |
| 0005 | CLI retained as automation contract | Accepted | CTO, DevOps, Chief of Staff | CLI never deleted; CI validates it; new features back-ported; CLI invocation telemetry added |
| 0006 | Command map is an enforced contract (CI integrity check) | Accepted | Software Engineering, CTO | `command_map.yaml` ↔ prompts ↔ `opencode.json` verified by CI — catches drift before runtime |
| 0007 | Supervisor self-healing: restart before isolate | Accepted | Software Engineering, Cloud Architecture | Engines get restart attempts (w/ fresh heartbeat) before isolation; `isolate` raises if no process record |
| 0008 | Dashboard frontend: Jinja2 + htmx (v1), Svelte 5 (v2) | Accepted (v1) | Chief Architect, CTO, SWE, Cloud Architecture | v1: Jinja2+htmx (no Node toolchain, fastest). v2: Svelte 5 + Vite (richer UX, budgeted in Phase 4) |
| 0009 | Dashboard API contract: REST + WebSocket, replay-based reconnect | Accepted | Chief Architect, SWE, Cybersecurity Architecture | Read-only v1: REST JSON + WS push. Reconnect via `?since=`. Write endpoints deferred to Phase 2 with auth+CSRF+audit |
| 0010 | Phase 2 write auth: bearer token + CSRF + mandatory write audit | Proposed | Chief Architect, CISO, Cybersecurity Architecture, SWE | Opaque bearer token (256-bit); double-submit CSRF token; `audit.write` event on every mutation; fail-closed on non-loopback |

## Key Decisions (beyond formal ADRs)

| Decision | Rationale | Where |
|---|---|---|
| **Python 3.12 only** | `X \| None` syntax, Pydantic v2, modern stdlib features. No older versions supported. | `pyproject.toml` `requires-python = ">=3.12"` |
| **mypy `--strict` with selective disables** | Strictness catches real bugs, but 13 error codes are impractical for this codebase (e.g., `no-untyped-def` in glue code). Disabled codes are documented and intentional. | `pyproject.toml` `[tool.mypy]` |
| **Ruff with intentional ignores** | Some rules fight readability in this codebase (e.g., `SIM114` forces merging if-branches that are clearer separate). All 14 ignores are documented with rationale. | `pyproject.toml` `[tool.ruff.lint]` |
| **`uv` as sole dependency tool** | Deterministic lockfile, fast install, group support. No pip/Poetry mixing. | `pyproject.toml`, CI |
| **Frozen `CompanyRegistry`** | Immutability prevents accidental drift during generation. Registry is the single source of truth; it should never change mid-run. | `models/company.py` `ConfigDict(frozen=True)` |
| **Registry Engine singleton** | Module-level `registry_engine` instance. All callers go through the same instance, which caches the last load result. Prevents redundant YAML parsing. | `registry/registry.py` |
| **Coordinator dispatches by `task_type`** | Engines never call each other directly. The Coordinator holds all engine references and dispatches pipeline tasks by `task_type` string. Enables pluggable handlers without touching orchestrator code. | `orchestration/coordinator.py` |
| **Declarative pipelines in YAML** | Pipelines, recovery policies, scheduler jobs, startup steps, and engine configs all live in YAML. This makes the system auditable and modifiable without code changes. | `config/orchestration/engine.yaml`, `config/runtime/startup.yaml` |
| **Agent sync is separate from CLI** | `python -m ai_company.agents sync` is a standalone argparse entry point — deliberately NOT part of the frozen Typer tree. It's invoked ad-hoc, not as `ai-company <command>`. | `agents/__main__.py` |
| **Agent files omit `model` frontmatter** | Opencode subagents without a model inherit the active model of the invoking agent. Pinning a model would break model promotion/demotion. | `agents/sync.py` docstring |
| **Dashboard API is loopback-only (v1)** | The dashboard binds `127.0.0.1` only with Host-header allowlist. Non-loopback exposure (Phase 2) requires the full write-auth scheme (ADR 0010). | `api/app.py` `_ALLOWED_HOSTS`, `_SecurityMiddleware` |
| **Telemetry is fail-open** | CLI invocation is recorded as JSONL; if persistence fails, the CLI continues. Never let observability break the user's command. | `cli/main.py`, `telemetry/cli.py` |
| **EventBus uses JSONL persistence** | Events persist to `events/store.jsonl` for replay. Dead-letter events go to `events/dead_letter.jsonl`. Simple, grep-able, no extra dependencies. | `events/bus.py`, `events/persistence.py` |
| **Memory tiered storage** | Working (in-memory) → Short-term (JSONL) → Long-term (JSONL) → Archived. Tier management runs as a scheduled job. Importance thresholds drive promotion/demotion. | `memory/engine.py` |
| **Pre-commit excludes generated/.ai-company** | Generated output and `.ai-company/` state change frequently and are gitignored from lint/format hooks. Source code in `src/` is always checked. | `.pre-commit-config.yaml` |

## Decision Log (chronological)

### Phase 0 — Command Centers
- `3324dbf` — telemetry, backup, integrity gate, self-healing shipped.
- `27348a1` — Phase 0 close-out: live recovery drill restored,
  `uv audit` added to CI, Windows CI matrix for test job.

### Phase 1 Wave 1 — Dashboard API v1 (`6d2654b`, `b6d5a26`)
- Adopted FastAPI + plain uvicorn (no uvloop) for cross-platform safety (ADR 0002).
- Read-only REST + WebSocket contract with replay-based reconnect (ADR 0009).
- Loopback-only binding with Host-header allowlist (security R9).
- `_SecurityMiddleware` adds CSP, X-Frame-Options, nosniff, no-store headers.
- All runtime calls bridged via `run_in_threadpool` — never block the loop.
- **Status: committed and live as Phase 1 wave 1.**

### Sprint 5.1 — OpenCode Persona Agents
- 35 persona agents (13 executives + 17 specialists + 5 board members)
  persisted globally to `~/.config/opencode/agents/` via
  `python -m ai_company.agents sync`.
- Deterministic slug assignment via `AgentSlugIndex` with collision detection;
  explicit executive slug table (`ceo`, `cto`, ...); built-in agent names
  (`build`, `plan`, `explore`, `general`, `architect`, `builder`, ...) can
  never be shadowed.
- Project-level non-persona agents (`architect.md`, `builder.md`) retained
  in `.opencode/agents/` — persona agents removed from project scope.

### Supervisor Self-Healing (ADR 0007)
- `RecoveryManager` registers per-engine restart factories.
- `policy_for()` falls back to category policies for named engines.
- `_isolate` raises when no process record exists (no fake recovery).

### 2026-08-01 — `.ai/` knowledge base
- Created 8-file knowledge base (architecture, project-context, coding-rules,
  repo-map, system-overview, decisions, agent-roles, current-work) so agents
  stop re-discovering the system.
- **Rule: update the relevant `.ai/` file after every commit.**
