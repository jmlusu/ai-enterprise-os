# Current Work State

> **Purpose:** Single source of truth for what's in progress, what's next, and
> what's blocked. Updated at the end of each work session and after each
> significant commit. Agents should read this file first to understand current
> context.

## Sprint Status

| Field | Value |
|---|---|
| **Current Sprint** | Sprint 5.1 — Opencode Persona Agents |
| **Status** | ✅ **COMPLETED** (2026-08-01) |
| **Goal** | Generate opencode agent files for all 35 company personas (13 executives, 17 specialists, 5 board members) with deterministic slugs, Jinja2 templates, and `python -m ai_company.agents sync` CLI |
| **Created** | 2026-08-01T10:10:48Z |
| **Completed** | 2026-08-01T10:45:00Z |

### Sprint 5.1 Deliverables — All Done

- [x] `AgentSlugIndex` — deterministic slug assignment with collision detection
- [x] `AgentSyncEngine` — plan/run sync with scope support (project|global|both)
- [x] `sync.py` — `python -m ai_company.agents sync` entry point (argparse, not Typer)
- [x] Agent rendering via `agents/template.py` (no `model` frontmatter — inherits invoking model)
- [x] 35 agents synced globally (executives use explicit slug table; built-ins never shadowed)
- [x] Project-level persona agents removed (only `architect.md`, `builder.md` remain in `.opencode/agents/`)

## Completed — Phase 1 Wave 1: Dashboard API (COMMITTED)

**Commits:** `6d2654b`, `b6d5a26` — **done and live.** Do NOT re-plan this.

| Deliverable | Status |
|---|---|
| FastAPI app (`api/app.py`) — REST + WebSocket | ✅ |
| `RuntimeFacade` (`services/runtime_facade.py`) — shared surface (ADR 0003) | ✅ |
| `DashboardEventBridge` (`services/dashboard_events.py`) — EventBus → asyncio queue | ✅ |
| Read-only contract v1 (ADR 0009): `GET /`, `/api/health`, `/api/status`, `/api/metrics`, `/api/engines`, `/api/events` | ✅ |
| WS `/api/ws?since=<iso>` — replay + live push | ✅ |
| Loopback-only Host allowlist + security headers (`_SecurityMiddleware`) | ✅ |
| `run_in_threadpool` bridge — runtime locks never on the event loop | ✅ |

---

## Next Sprint Candidates (Prioritized)

**No sprint has been officially started yet.**

### 1. Sprint 5.2 — Dashboard Frontend v1 (Jinja2 + htmx) ⭐ **Next**
**ADR:** 0008 (v1 accepted)
**Goal:** Server-rendered dashboard — no Node toolchain.

| Task | Status | Notes |
|---|---|---|
| Base layout template (`templates/base.html`) | ⬜ | CSP-compatible |
| Dashboard index (htmx WS + auto-reconnect) | ⬜ | |
| Engine status cards (partials) | ⬜ | |
| Events stream panel (partial) | ⬜ | |
| Metrics view | ⬜ | Lightweight, no heavy JS |
| FastAPI `TemplateResponse` wiring + static mount | ⬜ | |

### 2. Sprint 5.3 — Phase 2 Write Auth (Bearer + CSRF + Audit) 🔐
**ADR:** 0010 (Proposed)
**Goal:** Enable mutating endpoints with full security.

| Task | Status | Notes |
|---|---|---|
| Opaque bearer token (256-bit) gen/validation | ⬜ | `services/auth.py` |
| Double-submit CSRF token (cookie + header) | ⬜ | `services/csrf.py` |
| `audit.write` event on every mutation | ⬜ | |
| Fail-closed on non-loopback (R9) | ⬜ | Extend `_SecurityMiddleware` |
| Mutation endpoints: runtime start/stop/reload, orchestrate start | ⬜ | Behind auth |
| Token management CLI: `ai-company dashboard token create\|revoke\|list` | ⬜ | |

### 3. Sprint 5.4 — SQLite derived read model (ADR 0004) 📊
**ADR:** 0004 (Accepted)
**Goal:** Rebuildable SQLite (WAL) projection for dashboard reads.

| Task | Status | Notes |
|---|---|---|
| Projection schema | ⬜ | JSONL/JSON remain source of truth |
| Rebuild trigger (startup? watcher? CLI?) | ⬜ | **Decision needed** |
| WAL mode + concurrent readers | ⬜ | |

### 4. Sprint 5.5 — Svelte 5 Migration (Phase 4) 🔮
**ADR:** 0008 (v2 deferred)
**Goal:** Richer UX with Svelte 5 + Vite when budget allows.

| Task | Status | Notes |
|---|---|---|
| Vite + Svelte 5 setup | ⬜ | Separate `dashboard/` folder |
| Component library | ⬜ | |
| API client with TS types from OpenAPI | ⬜ | |
| Build pipeline integration | ⬜ | |

---

## In-Progress Work (Current Session)

### `.ai/` Knowledge Base — REBUILD
**Status:** 8/8 complete — committing so it survives workspace resets
**Context:** The workspace resets to the committed state; all uncommitted
files get wiped. This directory is committed on purpose (NOT in `.gitignore`).

| File | Status | Notes |
|---|---|---|
| `.ai/architecture.md` | ✅ | Layered architecture, patterns, data flow |
| `.ai/project-context.md` | ✅ | Identity, conventions, commands, history |
| `.ai/coding-rules.md` | ✅ | 34 rules: Python 3.12, Pydantic v2, uv, ruff, mypy |
| `.ai/repo-map.md` | ✅ | File-by-file map of every module |
| `.ai/system-overview.md` | ✅ | Runtime lifecycle, engines, pipeline, API |
| `.ai/decisions.md` | ✅ | ADR index + key decisions + log |
| `.ai/agent-roles.md` | ✅ | 35 personas + slugs + sync mechanism |
| `.ai/current-work.md` | ✅ | This file |

---

## Open Issues & Decisions Needed

| Issue | Context | Decision Needed |
|---|---|---|
| **SQLite read model rebuild trigger** | ADR 0004 accepted | On startup? Watcher? Manual CLI? |
| **Agent sync `--scope` default** | Currently defaults to `global` | Default to `both` for new users? |
| **Dashboard port binding** | Hardcoded `127.0.0.1:8000` | Make configurable via `config/runtime/*.yaml`? |
| **Windows CI matrix** | Only test job runs on Windows | Should lint/typecheck also run on Windows? |

---

## Recently Completed (Commits)

```text
3af24e5 chore: remove legacy sprint dashboard stub and gitignore dashboards/ output
ce1df08 feat: add .ai/ knowledge base so agents stop re-discovering the system
a76acdf fix: sort circuit_breaker import before configuration (I001)
3b145b5 chore: update commit instruction
bc28582 Merge branch 'main'
13b27ba fix: restore architect agent in opencode.json for command map integrity
b6d5a26 feat: Phase 1 wave 1 — dashboard API server (read-only contract v1)
27348a1 feat: Phase 0 close-out — restore drill, Windows CI, live recovery drill
3324dbf feat: Phase 0 command centers — telemetry, backup, integrity gate, self-healing
c30efcf feat: rename CEO to Jack Mlusu and extend executive bio
f100d3b feat: Sprint 4.6 — Enterprise Runtime Engine (kernel/OS layer)
c37f867 feat: Sprint 4.5 — Enterprise Orchestration Engine (COO layer)
```

---

## Key Context for Next Session

1. **Sprint 5.1 is DONE** — all 35 persona agents are live in Opencode.
   Test with `@ceo-jack-mlusu help`.

2. **Dashboard API v1 is DONE and committed** (`b6d5a26`) — read-only REST +
   WS on `127.0.0.1:8000`. **The next work is the frontend** (Jinja2 + htmx,
   ADR 0008 v1), then Phase 2 write auth (ADR 0010).

3. **`.ai/` knowledge base is complete** — 8 files, committed. **Rule: update
   the relevant `.ai/` file after every commit** so agents never re-discover
   the system.

4. **Constitution is immutable** — `.ai-company/constitution/rules.md`
   cannot be overridden by any agent. Read sprint state first, update it last.

5. **CLI is frozen** — the Typer command tree is a contract (ADR 0006). New
   features must back-port CLI commands; CI validates the command map.

6. **Workspace resets to HEAD** — commit work promptly; uncommitted files
   (including `.ai/`) get wiped.

---

## Quick Commands Reference

```bash
# Sync agents (after any company/*.yaml change)
python -m ai_company.agents sync

# Start runtime (blocking)
ai-company runtime start

# Start dashboard API (read-only v1, loopback)
ai-company serve

# Run tests / lint / typecheck
uv run --group dev pytest -xvs
uv run --group dev ruff check src/
uv run --group dev mypy --strict src/
pre-commit run --all-files

# Validate command map integrity (CI gate)
python -m ai_company.cli.command_map validate
```

---

## File Watch List (Changes Here Trigger Work)

| File | Why It Matters |
|---|---|
| `company/*.yaml` | Persona source of truth — triggers agent re-sync |
| `config/runtime/startup.yaml` | Declarative boot — affects runtime lifecycle |
| `config/orchestration/engine.yaml` | Pipeline definitions |
| `opencode.json` | Provider config, agent definitions — CI validates |
| `docs/adr/*.md` | New ADRs = new sprints |
| `.ai-company/state/current_sprint.yaml` | Active sprint — update when starting/completing |
| `pyproject.toml` | Dependencies/tooling — version bumps need testing |

---

*Updated: 2026-08-01 — ADR 0008/0009 ratified, orphaned artifacts cleaned*
*Next update: When the dashboard frontend sprint starts or after the next commit*
