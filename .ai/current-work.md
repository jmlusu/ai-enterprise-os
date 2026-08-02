# Current Work State

> **Purpose:** Single source of truth for what's in progress, what's next, and
> what's blocked. Updated at the end of each work session and after each
> significant commit. Agents should read this file first to understand current
> context.

## Sprint Status

| Field | Value |
|---|---|
| **Current Sprint** | Sprint 5.2 — Phase 2 Waves 2a+2b: Write Auth (ADR 0010) + Generate→Review→Validate→Approve Loop |
| **Status** | ✅ **COMPLETED** (2026-08-02) — Waves 2a AND 2b shipped; **Phase 2 exit criterion met** (full generate → review → validate → approve loop from the browser) |
| **Goal** | Complete the operational dashboard pivot: guarded mutation endpoints + the full governance loop (generate dispatcher, decision inbox, per-artifact validation, graph export, company CRUD, agent sync, backup) + R5 telemetry live panels |
| **Commit** | Wave 2a: `131d9d9` · Wave 2b: `2244497` |
| **Created** | 2026-08-01 |
| **Completed** | 2026-08-02 |

### Sprint 5.2 Wave 2b Deliverables — All Done

- [x] `services/generate_runner.py` — thread-safe streaming OpenCode dispatcher (`start/cancel/get/list_runs/log_tail`), child stdout streamed to `runtime/generate_logs/<run_id>.log`, runs persisted to `runtime/generate_runs.jsonl`, boot replay marks queued/running as `interrupted by restart`, shell=False, fail-open
- [x] `api/guards.py` — shared `WriteGuard` (`guard()/require_reason()/audited()/reject()`) + `HIGH_IMPACT_ACTIONS`; `write_endpoints.py` migrated to it (ADR 0010 semantics unchanged)
- [x] Decision/approval inbox — `decisions_list/get/create/approve/reject/escalate/cancel` facade adapters; inbox survives restarts via `DecisionHistory.import_decisions()`; `engine.reject()` added; `create_decision`/`make_decision` record-once (no facade double-record)
- [x] Per-artifact company validators via API (`validate_artifacts` wraps per-artifact `ValidationReport` in `ValidatorResult`)
- [x] Remaining P2 write surfaces: graph export write, company CRUD write (files/departments/manifest), agent sync (`AgentSyncEngine(config=...)`), backup create/status, telemetry persist
- [x] Frontend: `/generate` (dispatch + live logs + history), `/decisions` (approval inbox), `/telemetry` (KPI / Model Usage / Agent Health live panels), pulse backup tile; CSP-safe `data-write`/`data-action` wire helpers
- [x] R5 telemetry workstream: `telemetry/metrics.py` + `telemetry/provider.py` (JSONL persistence, aggregated summaries) + `providers/usage.py` `UsageTrackingProvider` + `ProviderFactory(..., track_usage=False)`; 30s persistence ticker in app lifespan
- [x] WS `?token=` enforcement for non-loopback (close 1008, ADR 0010 §1)
- [x] Tests: telemetry (10), generate runner (9), facade wave 2b (24), API wave 2b (24 incl. page renders + guard/audit parity), golden parity wave 2b; suite 1171 → **1252 green**; ruff/mypy/format/command-map clean

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

### 1. Sprint 5.3 — SQLite derived read model (ADR 0004) 📊
**ADR:** 0004 (Accepted) — rebuildable SQLite (WAL) projection for dashboard reads; rebuild trigger decision needed (startup? watcher? CLI?).

### 2. Sprint 5.4 — Telemetry follow-ups 📡
R5 core (metrics + provider usage persistence) shipped with Wave 2b. Follow-ups: SQLite telemetry store, retention/rollup policies, alerting on isolation (R2 backlog), recovery-success metric.

### 3. Sprint 5.5 — Svelte 5 Migration (Phase 4) 🔮
**ADR:** 0008 (v2 deferred) — richer UX with Svelte 5 + Vite when budget allows.

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
2244497        feat: Phase 2 Wave 2b + telemetry/parity/backup close-out (generate loop, decision inbox, R5 telemetry)
66cf7c4        chore: refresh api package exports for Phase 2 write surface (ADR 0010)
479f5c6        chore: refresh .ai/ knowledge base for Phase 2 wave 2a (ADR 0010 ratified, write surface live)
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

1. **Phase 2 Waves 2a+2b (ADR 0010) are SHIPPED** — Wave 2a commit `131d9d9`;
   Wave 2b committed with this update. The dashboard now runs the full
   **generate → review → validate → approve loop**: `/generate` streams an
   OpenCode run with live logs + history, `/decisions` renders the approval
   inbox (risk cards, approve/reject/escalate), per-artifact validators run
   from the API, and graph export / company CRUD / agent sync / backup /
   telemetry all have guarded, audited write endpoints. **Phase 2 exit
   criterion met. Suite: 1252 tests green.**

2. **R5 telemetry is live** — runtime metrics persist every 30s to
   `runtime/metrics_history.jsonl`, provider usage to
   `runtime/provider_usage.jsonl` (aggregated by model). KPI / Model Usage /
   Agent Health panels on `/telemetry` render real data (no more "data
   pending").

3. **`.ai/` knowledge base is complete** — 8 files, committed. **Rule: update
   the relevant `.ai/` file after every commit** so agents never re-discover
   the system.

4. **Constitution is immutable** — `.ai-company/constitution/rules.md`
   cannot be overridden by any agent. Read sprint state first, update it last.

5. **CLI is frozen** — the Typer command tree is a contract (ADR 0006). New
   features must back-port CLI commands; CI validates the command map.
   Wave 2a token CLI was additive-only (`dashboard token` sub-group); Wave 2b
   made no CLI surface changes.

6. **Workspace resets to HEAD** — commit work promptly; uncommitted files
   (including `.ai/`) get wiped.

7. **Parity test suite is seeded** — `tests/golden/test_parity_read.py`
   (golden CLI output == API JSON) plus `tests/golden/test_parity_wave2b.py`
   (generate/backup contract + shared guard parity). Every new read command
   must add a parity row + parity test (Phase 4 demotion trigger depends on
   it). Wave 2b flipped all remaining safe-write rows to `1+2`.

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

*Updated: 2026-08-02 — Phase 2 Waves 2a+2b committed; exit criterion met (generate → review → validate → approve loop), R5 telemetry live panels, 1252 tests green*
*Next update: When Sprint 5.3 (SQLite read model, ADR 0004) starts or after the next commit*
