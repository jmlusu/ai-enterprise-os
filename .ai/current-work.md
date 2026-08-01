# Current Work State

> **Purpose:** Single source of truth for what's in progress, what's next, and
> what's blocked. Updated at the end of each work session and after each
> significant commit. Agents should read this file first to understand current
> context.

## Sprint Status

| Field | Value |
|---|---|
| **Current Sprint** | Sprint 5.2 — Phase 2 Wave 2a: Write Auth (ADR 0010) + Operational Writes |
| **Status** | ✅ **COMPLETED** (2026-08-01) — Wave 2a shipped; Wave 2b (generate dispatcher + approval inbox) is next |
| **Goal** | Enable mutating endpoints with full security (bearer token + CSRF + mandatory write audit) — the "operational dashboard" pivot |
| **Commit** | `131d9d9` (ADR 0010 ratified in the same change) |
| **Created** | 2026-08-01 |
| **Completed** | 2026-08-01 |

### Sprint 5.2 Wave 2a Deliverables — All Done

- [x] ADR 0010 ratified (Proposed → Accepted, decision D8) — opaque 256-bit bearer token, per-run CSRF, mandatory `audit.write` / `audit.write_rejected` (fail-open JSONL)
- [x] `api/auth.py` — `WriteTokenService` (create/rotate/revoke/verify, hash-at-rest, env override `AI_ENTERPRISE_WRITE_TOKEN`), `CsrfService`, `host_allowed()`, fail-open audit publisher
- [x] `api/write_endpoints.py` — 20 mutation POSTs + `GET /api/write-csrf` + `GET /api/audit/writes`; guard = Host policy → token (401) → CSRF (403) → `audit.write_rejected`; high-impact actions (stop/restart/recover/unisolate/rollback) require `reason` (422)
- [x] `services/runtime_facade.py` write adapters (runtime/orchestrate/memory/validate/reports/build/bootstrap); engines untouched (ADR 0005/0006)
- [x] Frontend: operator buttons + native confirm dialogs (reason prompts), Write History page (`/writes`) with token input + audit table, CSP-safe JS (textContent only)
- [x] CLI additive (ADR 0006): `ai-company dashboard token create|revoke|list|info` (value printed only on first-time creation; rotation never echoes); `serve --hash-at-rest --require-loopback-token`
- [x] Tests: `test_auth.py` (18) + `test_write_endpoints.py` (11); suite 1142 → **1171 green**; ruff/mypy/format/lock/audit/build clean
- [x] Docs: parity-matrix P2 rows → `1+2` (generate rows → `2b`), initiative Phase 2 `[IN PROGRESS]` / R9 `[MITIGATED]` / D8 `[DECIDED]` / §7.8, `docs/dashboard/phase2-workplan.md`, `.ai/` knowledge base

---

## Completed — Phase 2 Wave 2a: Write Auth + Operational Writes (COMMITTED)

**Commit:** `131d9d9` — **done and live.** Do NOT re-plan this. Work plan: `docs/dashboard/phase2-workplan.md` (Wave 2a).

| Deliverable | Status |
|---|---|
| `api/auth.py` — `WriteTokenService` / `CsrfService` / `host_allowed()` / fail-open audit publisher | ✅ |
| `api/write_endpoints.py` — 20 mutation POSTs + `GET /api/write-csrf` + `GET /api/audit/writes` | ✅ |
| `events/models.py` — `EventType.AUDIT_WRITE` / `AUDIT_WRITE_REJECTED` | ✅ |
| Write guard: non-loopback Host → token mandatory (fail-closed); loopback → optional / `--require-loopback-token`; invalid token 401; CSRF mismatch 403; rejected payloads never leak token/CSRF | ✅ |
| High-impact `reason` requirement (`HIGH_IMPACT_ACTIONS`): runtime stop/restart/recover/unisolate, orchestrate rollback | ✅ |
| CLI `dashboard token create\|revoke\|list\|info` + `serve --hash-at-rest` / `--require-loopback-token` (additive, ADR 0006) | ✅ |
| Frontend: write actions + confirm dialogs, Write History page, token input, CSP-safe | ✅ |
| Tests 1142 → **1171** (18 auth + 11 write-endpoint tests); ruff/mypy/format/lock/audit/build clean | ✅ |
| Docs: ADR 0010 Accepted, parity matrix `1+2`/`2b`, initiative §4/R9/D8/§7.8, phase2-workplan.md | ✅ |

---

## Completed — Phase 1 (COMMITTED)

**Wave 1 API:** `6d2654b`, `b6d5a26` · **Wave 2 frontend:** `d0b1385` — **Phase 1 is DONE.** Do NOT re-plan this. Work plan: `docs/dashboard/phase1-workplan.md`.

| Deliverable | Status |
|---|---|
| FastAPI app (`api/app.py`) — REST + WebSocket, loopback-only, security headers | ✅ |
| `RuntimeFacade` (`services/runtime_facade.py`) — shared surface (ADR 0003), 16 read methods | ✅ |
| 19 read-only API endpoints (ADR 0009) + WS `/api/ws?since=` replay | ✅ |
| Jinja2 + htmx frontend (ADR 0008 v1): `base.html` + 8 views | ✅ |
| Vendored assets `static/vendor/` + provenance README | ✅ |
| Scoped page CSP (`script-src 'self'`, no `unsafe-inline`) | ✅ |
| Parity test suite seed `tests/golden/test_parity_read.py` (9 tests) | ✅ |
| Suite 1070 → **1142 tests green**; no CLI or engine changes | ✅ |

---

## Next Sprint Candidates (Prioritized)

### 1. Sprint 5.2 Wave 2b — Generate Dispatcher + Approval Inbox ⭐ **Next**
**ADR:** 0010 (Accepted) · **Scope:** complete the Phase 2 exit criterion: a full generate → review → validate → approve loop from the browser.

| Task | Status | Notes |
|---|---|---|
| `POST /api/generate` — OpenCode dispatch (streaming subprocess, exit code, files touched) + run history + live logs | ⬜ | `opencode_runner` refactor; parity `generate` rows → `1+2` |
| Generate panel frontend (targets, prompt input, live log stream) | ⬜ | |
| Decision/approval inbox — risk cards, approval matrix, escalation | ⬜ | Renderer over existing decision engine |
| Per-artifact company validators via API (`board-validate` … `doc-validate`) | ⬜ | Parity rows → `1+2` |
| Graph export write, company CRUD write (`PUT /api/company`), agent sync, backup, telemetry write | ⬜ | Remaining P2 surfaces |
| WS `?token=` enforcement for non-loopback | ⬜ | ADR 0010 §1 |

### 2. Sprint 5.3 — SQLite derived read model (ADR 0004) 📊
**ADR:** 0004 (Accepted) — rebuildable SQLite (WAL) projection for dashboard reads; rebuild trigger decision needed (startup? watcher? CLI?).

### 3. Sprint 5.4 — Telemetry workstream (R5 closure) 📡
Runtime metrics persistence + provider usage instrumentation so KPI / Model Usage / Agent Health panels go live (currently "data pending").

### 4. Sprint 5.5 — Svelte 5 Migration (Phase 4) 🔮
**ADR:** 0008 (v2 deferred) — richer UX with Svelte 5 + Vite when budget allows.

---

## Open Issues & Decisions Needed

| Issue | Context | Decision Needed |
|---|---|---|
| **SQLite read model rebuild trigger** | ADR 0004 accepted | On startup? Watcher? Manual CLI? |
| **Agent sync `--scope` default** | Currently defaults to `global` | Default to `both` for new users? |
| **Dashboard port binding** | Hardcoded `127.0.0.1:8000` | Make configurable via `config/runtime/*.yaml`? |
| **Windows CI matrix** | Only test job runs on Windows | Should lint/typecheck also run on Windows? |
| **Wave 2b generate dispatch scope** | Q2 open: CLI `generate` dispatches to OpenCode via blocking subprocess today | Stream from dashboard in Wave 2b — confirm blocking → streaming plan |

---

## Recently Completed (Commits)

```text
131d9d9        feat: Phase 2 wave 2a — write auth (ADR 0010), 20 mutation endpoints, audit + token CLI
b88c0b6        chore: record Phase 1 wave 2 commit hash in current-work tracker
d0b1385        feat: Phase 1 wave 2 — dashboard frontend v1 (8 views, scoped CSP, parity seed)
a190434        chore: ratify ADR 0008/0009 and refresh stale project trackers
3af24e5        chore: remove legacy sprint dashboard stub and gitignore dashboards/ output
ce1df08        feat: add .ai/ knowledge base so agents stop re-discovering the system
b6d5a26        feat: Phase 1 wave 1 — dashboard API server (read-only contract v1)
27348a1        feat: Phase 0 close-out — restore drill, Windows CI, live recovery drill
3324dbf        feat: Phase 0 command centers — telemetry, backup, integrity gate, self-healing
```

---

## Key Context for Next Session

1. **Phase 2 Wave 2a (ADR 0010) is SHIPPED** — commit `131d9d9`. The dashboard
   now has 20 guarded mutation endpoints (runtime/orchestrate/memory/validate/
   reports/build/bootstrap) behind bearer token + CSRF + `audit.write`; Write
   History page at `/writes`; token CLI at `ai-company dashboard token`.
   Non-loopback Hosts fail closed; loopback is token-optional unless
   `--require-loopback-token`. **Suite: 1171 tests green.**

2. **Next work is Wave 2b**: `POST /api/generate` (OpenCode streaming
   dispatcher + run history + live logs) and the decision/approval inbox —
   that completes the Phase 2 exit criterion ("a full generate → review →
   validate → approve loop without opening a terminal").

3. **`.ai/` knowledge base is complete** — 8 files, committed. **Rule: update
   the relevant `.ai/` file after every commit** so agents never re-discover
   the system.

4. **Constitution is immutable** — `.ai-company/constitution/rules.md`
   cannot be overridden by any agent. Read sprint state first, update it last.

5. **CLI is frozen** — the Typer command tree is a contract (ADR 0006). New
   features must back-port CLI commands; CI validates the command map.
   Wave 2a token CLI was additive-only (`dashboard token` sub-group).

6. **Workspace resets to HEAD** — commit work promptly; uncommitted files
   (including `.ai/`) get wiped.

7. **Parity test suite is seeded** — `tests/golden/test_parity_read.py`
   (golden CLI output == API JSON). Every new read command must add a parity
   row + parity test (Phase 4 demotion trigger depends on it). Write parity
   coverage grows with Wave 2b.

---

## Quick Commands Reference

```bash
# Sync agents (after any company/*.yaml change)
python -m ai_company.agents sync

# Start runtime (blocking)
ai-company runtime start

# Start dashboard API (read + guarded writes, loopback; token optional on loopback)
ai-company serve
ai-company serve --require-loopback-token --hash-at-rest   # strict mode

# Token management (ADR 0010) — value printed only on first-time creation
ai-company dashboard token create
ai-company dashboard token list
ai-company dashboard token revoke

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
| `src/ai_company/api/auth.py` | ADR 0010 write guards — fail-open audit semantics must not change |

---

*Updated: 2026-08-01 — Phase 2 Wave 2a (ADR 0010 write auth + 20 mutation endpoints) committed (`131d9d9`), 1171 tests green*
*Next update: When Phase 2 Wave 2b (generate dispatcher + approval inbox) starts or after the next commit*
