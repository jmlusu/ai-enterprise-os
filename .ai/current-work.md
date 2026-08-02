# Current Work State

> **Purpose:** Single source of truth for what's in progress, what's next, and
> what's blocked. Updated at the end of each work session and after each
> significant commit. Agents should read this file first to understand current
> context.

## Sprint Status

| Field | Value |
|---|---|
| **Current Sprint** | Sprint 5.4 — Telemetry: durable, bounded, actionable (SQLite store, retention/rollup, isolation alerting, recovery metric) |
| **Status** | 🔄 **IN PROGRESS** — T1 (SQLite live telemetry store) shipped; T2–T4 pending; T5 stretch |
| **Goal** | Complete the R5/R2 telemetry story before Phase 3: (T1) SQLite **live** telemetry store (incremental sync, read path = ADR 0004 projection), (T2) retention + rollup policies (config-driven, rollup-then-truncate, scheduler job), (T3) isolation alerting (`runtime.engine_isolated` → alerts → dashboard), (T4) recovery-success metric (counters + KPI rate). Zero CLI-surface changes (ADR 0006); R3 parity rows for new reads |
| **Commit** | Sprint 5.3: `de9c851` · Wave 2b: `2244497` · Wave 2a: `131d9d9` |
| **Created** | 2026-08-02 |
| **Completed** | — |
| **Follow-up (in progress)** | Post-Sprint 5.3 risk mitigation completed: R12/R8/R3/R11/R4 — see "Dashboard Initiative Follow-up" below |

### Sprint 5.4 Backlog (committed plan — 2026-08-02)

**Goal:** telemetry is durable (SQLite live store), bounded (retention/rollup), and actionable (isolation alerting + recovery-success metric) — closing the R5/R2 backlog before Phase 3.

| # | Item | Pts | Acceptance summary |
|---|---|---|---|
| **T1** | SQLite **live** telemetry store — **SHIPPED** | 8 | `ReadModelStore.sync_from_jsonl()` — incremental, watermark-based, idempotent (no dupes on re-sync); synced on the 30s telemetry ticker (single writer via `facade.metrics_persist` → `sync_read_model`); facade `metrics_history_summary` / `provider_usage_summary` read the store with **fail-open to JSONL**; JSONL stays append-only source of truth (ADR 0004). AC met: appends during a live session appear without restart; re-sync idempotent; store-down → JSONL fallback. Suite 1308 → **1320 green** |
| **T2** | Retention + rollup | 8 | `telemetry/retention.py` + `config/runtime/telemetry.yaml` (metrics 7d / provider_usage 90d / cli_telemetry 180d defaults); **rollup-then-truncate** hourly/daily aggregates; `telemetry_retention` recurring scheduler job (pattern: `memory_consolidation`); rollup-aware read path. AC: dry-run + apply; rollup math correct; raw never truncated before rollup |
| **T3** | Isolation alerting (R2 backlog) | 3 | Unified `runtime.engine_isolated` event (engine, reason, attempts, ts) from supervisor `_isolate`/watchdog; fail-open `runtime/alerts.jsonl` + `telemetry/alerts.py` + `GET /api/alerts` + pulse/System Health red chip + KPI line; alert **resolved** on recovery (no spam). AC: alert visible within one health cycle; persists across restart |
| **T4** | Recovery-success metric (R2 backlog) | 3 | Metrics counters `recovery_attempts` / `recovery_successes` / `recovery_failures` + gauge `recovery_success_rate`; `RecoveryManager` outcome recording (recovered → success; escalated/isolated → failure; **once per outcome**); `/telemetry` KPI line "Self-healing: N% success". AC: counters increment exactly once per outcome; rate persists in snapshot |
| **T5** | CI segfault flake (STRETCH) | 5 | Root-cause the ubuntu `test` job exit-139 (~15% after `test_runtime_boot.py`; thread teardown + HeartbeatSender + SQLite) and fix, or land documented mitigation + tracking issue. AC: 10 consecutive green runs, or analysis + mitigation + issue |

**Sequencing:** T1 (foundation) → T4 ‖ T3 (small, independent) → T2 (needs T1) → T5 (last, risk-isolated).

**Definition of Done:** suite 1308 → ~1360 green; parity rows + golden tests for new read surfaces (alerts, rollup reads); ruff/mypy/format/command-map/CLI-surface/uv-audit clean; trackers updated with each commit.

### Sprint 5.4 T1 Deliverables — SQLite live telemetry store (DONE)

- [x] **`ReadModelStore.sync_from_jsonl()`** — watermark-based incremental import: per-source byte offsets stored in `meta` (`sync_offset_events/metrics/provider_usage`); only bytes appended since the last sync are parsed and inserted; events deduped by `event_id` (`INSERT OR IGNORE`); rows + watermarks commit in **one transaction** (crash-safe, no duplicates); missing/truncated/never-synced sources → full stream re-import (projection always mirrors source). `rebuild()` seeds the watermarks so startup rebuild → live incremental sync.
- [x] **`ReadModelEngine.sync()`** — engine-level passthrough for the ticker/CLI; `stats()` now reports `last_sync_at`.
- [x] **Facade repoint (fail-open)** — `RuntimeFacade.metrics_history_summary` / `provider_usage_summary` prefer the `read_model` engine's store (`persistence_enabled` preserved in the envelope); fall back to JSONL when the engine is absent or the store read fails. New `sync_read_model()`; `metrics_persist()` now persists **and** syncs (the 30s serve ticker drives both — single writer).
- [x] **Tests** — `tests/unit/readmodel/test_readmodel.py` (+7): sync appends, idempotency, full-import-when-never-rebuilt, truncation mirror, event dedup, missing sources no-op, engine sync. `tests/unit/services/test_facade_wave2b.py` (+5): store-preferring reads, sync catch-up without restart, `metrics_persist` syncs the store, JSONL fallback preserved. Suite 1308 → **1320 green**; ruff/mypy/format/command-map/CLI-surface clean.

### Dashboard Initiative Follow-up (post-Sprint 5.3, in progress)

- [x] **D5 north-star metric signed off** — CEO approved 2026-08-02: share of operator actions via Dashboard/OpenCode desktop ≥ **80% by month 6**; baseline = CLI telemetry (`runtime/cli_telemetry.jsonl`); GUI/desktop telemetry in Phase 3 (honest numerator); Phase 4 trigger depends on it
- [x] **R4 fallback strategy decided (D9)** — CEO approved 2026-08-02: **free/local models** (e.g. `ollama/llama3.1:8b`, D4) are the official fallback
- [x] **R4 end-to-end fallback shipped → R4 `[MITIGATED]`** — shared `services/generate_dispatch.py` (`dispatch_generate`: opencode primary → `ollama` fallback on missing / startup failure / non-zero exit); wired into the streaming runner (honest `provider`/`model` in `runtime/generate_runs.jsonl` + append-mode logs) and the frozen CLI `generate` command (surface unchanged, R8 gate still green); tunable via `config/runtime/model_fallback.yaml`; cancellation preserved (`register_proc`); proven by runner e2e tests with stub binaries + dispatch unit tests + CLI wiring tests — suite 1289 → **1308 green**
- [x] **R12 canonical status service** — `services/status_service.py` (four-state `ok`/`watch`/`action`/`unknown` + timestamp, phase state machine; stopped → watch, never action); CLI `runtime status` Overall line, `GET /api/status` + `/api/health` canonical, dashboard views + app.js unified; golden parity `tests/golden/test_parity_status.py`; **also fixed root cause of misleading unhealthy flags — `HeartbeatSender` liveness worker (passive engines were isolated after boot) + read-model `check_same_thread=False`**; R12 → `[MITIGATED]` in initiative.md — **committed `147540b` (heartbeat fix) + `75e0595` (status service), pushed 2026-08-02, CI green**
- [x] **R8 CI gate — CLI additive-only rule** — `integrity/check_cli_surface.py` (typer/click introspection vs committed `cli_surface_contract.json`; removal/rename/change = hard error exit 1; additive drift = exit 2, accept with `--update`); wired into both lint jobs in ci.yml next to the command-map gate; 8 unit tests (`tests/unit/integrity/test_check_cli_surface.py`); verified: real removal → exit 1
- [x] **R3 parity coverage milestone** — explicit target in `docs/dashboard/initiative.md` §5 R3 + parity-matrix-v0.md: **≥40 of 71 command rows parity-tested by Phase 3 close-out**; every new command adds its parity test in the same change
- [x] **R11 persona onboarding scope — D10 SIGNED OFF** (CEO 2026-08-02) in initiative.md §6: three personas View/Operate/Develop, one skippable first-run tour each + persistent "Equivalent CLI command" tooltips; no tutorial system; destructive/bulk stays CLI-only, surfaced in Develop persona. **R11 → `[MITIGATED]`**; delivery lands with Phase 2/3 features

### Sprint 5.3 Deliverables

- [x] **`readmodel/` package (ADR 0004)** — `ReadModelStore` (SQLite WAL, schema v1) + `ReadModelEngine` (rebuild-on-construct = the **startup** trigger); tables `events`, `metrics_history`, `provider_usage`, `meta`; reads: `recent_events`, `event_counts_by_type`, `metrics_snapshots`, `metrics_summary`, `provider_usage_by_model`
- [x] **Startup wiring** — `config/runtime/startup.yaml` step `initialize_read_model` (engine `read_model`, `db_path: "@state_dir"` → `runtime/dashboard.db`) before `start_runtime`; boot sequence is now **11 steps / 6 engines**
- [x] **Agent sync `--scope` default `both`** — `agents/sync.py` (`AgentSyncConfig.scope`), `agents/__main__.py` (`--scope`), `api/operational_endpoints.py` (`AgentsSyncBody.scope`), `services/runtime_facade.py` (`agents_sync(scope="both")`); new users get project + global dirs
- [x] **Dashboard port decision documented** — `cli/main.py` `serve()` keeps default `127.0.0.1:8000` hardcoded (loopback-only), overridable via `--host/--port`; non-loopback requires ADR 0010 auth
- [x] **Windows CI** — `ci.yml` lint + type-check jobs now use a `os: [ubuntu-latest, windows-latest]` matrix (`fail-fast: false`); tests already ran on both
- [x] Tests: `tests/unit/readmodel/test_readmodel.py` (13 new), boot test updated (11 steps / 6 engines incl. `read_model`), agents-sync default + CLI global-dir writes; suite 1252 → **1265 green**; ruff/mypy/format clean
- [x] Pre-existing fixes while green-checking: metrics JSONL writer now guarantees strictly increasing timestamps (Windows coarse clock); parity test asserts Typer 0.27 `target` rendering; ruff SIM117/RUF100 cleanups in wave 2b tests

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

### 1. Sprint 5.5 — Phase 3: OpenCode desktop as first-class command center 🖥️
Initiative Phase 3 `[NOT STARTED]`: session bridge (every session loads constitution/state, closes by posting telemetry → Model Usage / Agent Health become real), deep links both ways (dashboard → "continue in OpenCode"; desktop → "submit for review"), GUI/desktop action telemetry for the D5 north-star numerator. **Exit:** ≥90% of generation targets runnable desktop-first without typing a CLI command.

### 2. Sprint 5.6 — Svelte 5 Migration (Phase 4) 🔮
**ADR:** 0008 (v2 deferred) — richer UX with Svelte 5 + Vite when budget allows.

---

## Open Issues & Decisions Needed

| Issue | Context | Decision Needed |
|---|---|---|
| ~~SQLite read model rebuild trigger~~ | ADR 0004 accepted | ✅ **Resolved (Sprint 5.3): rebuild on startup** via `initialize_read_model` step (`ReadModelEngine` rebuild-on-construct) |
| ~~Agent sync `--scope` default~~ | Previously defaulted to `project` | ✅ **Resolved (Sprint 5.3): default `both`** for new users (project + global) |
| ~~Dashboard port binding~~ | Hardcoded `127.0.0.1:8000` | ✅ **Resolved (Sprint 5.3): keep hardcoded loopback default**; overridable via `--host/--port`; non-loopback requires ADR 0010 auth |
| ~~Windows CI matrix~~ | Only test job ran on Windows | ✅ **Resolved (Sprint 5.3): lint + type-check also run on Windows** (ubuntu + windows matrix) |

---

## Recently Completed (Commits)

```text
1fd0c97        feat: R4 — end-to-end free/local fallback for generate dispatch (D9 close-out)
936f9ea        fix: strip ANSI styling from CLI help in parity test (CI FORCE_COLOR wraps tokens)
de9c851        feat: Sprint 5.3 — SQLite read model on startup (ADR 0004), agent sync scope both, Windows CI lint/type-check
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

1. **Sprint 5.3 (SQLite read model + decision close-out) is COMMITTED** (`de9c851`)
   — the four orphaned decisions from the previous session are resolved,
   implemented, and shipped: read model rebuild **on startup** (ADR 0004,
   `runtime/dashboard.db` WAL projection over the JSONL sources of truth, via
   the `initialize_read_model` boot step), agent sync `--scope` default **both**,
   dashboard port stays **127.0.0.1:8000**, and **Windows CI** now runs
   lint/type-check. Suite: **1265 tests green**; ruff/mypy/format clean.
   **Pushed to origin/main; CI fully green (8/8 jobs).**

2. **D5 + D9 CEO sign-offs recorded (2026-08-02)** — D5: north-star metric =
   share of operator actions via Dashboard/OpenCode desktop **≥80% by month 6**
   (baseline = CLI telemetry `runtime/cli_telemetry.jsonl`; GUI telemetry in
   Phase 3). D9: fallback provider strategy = **free/local models** (e.g.
   `ollama/llama3.1:8b`) — **R4 → `[MITIGATED]` 2026-08-02** via the shared
   `services/generate_dispatch.py` fallback, proven end-to-end. Logged in
   `docs/dashboard/initiative.md` + `.ai/decisions.md`.

3. **Dashboard-initiative follow-up risks (2026-08-02 batch)** — **R12
   MITIGATED**: canonical status service (`services/status_service.py`, four
   states + timestamp, phase-state-machine derived) unifies CLI/API/dashboard;
   root cause of misleading "unhealthy" flags fixed (`HeartbeatSender` liveness
   worker + read-model `check_same_thread=False`). **R8**: CLI surface integrity
   gate live in CI (`integrity/check_cli_surface.py` vs committed contract;
   additive-only, exit 1 on removal/rename/change, `--update` for additive
   drift). **R3**: parity milestone ≥40/71 rows by Phase 3 close-out. **R11 →
   MITIGATED**: D10 persona onboarding **SIGNED OFF by CEO 2026-08-02**
   (View/Operate/Develop, one skippable first-run tour each + tooltips, no
   tutorial system). **R4 → MITIGATED**: end-to-end free/local fallback shipped
   (`services/generate_dispatch.py`, `config/runtime/model_fallback.yaml`).

4. **R5 telemetry is live** — runtime metrics persist every 30s to
   `runtime/metrics_history.jsonl`, provider usage to
   `runtime/provider_usage.jsonl` (aggregated by model). KPI / Model Usage /
   Agent Health panels on `/telemetry` render real data (no more "data
   pending").

5. **`.ai/` knowledge base is complete** — 8 files, committed. **Rule: update
   the relevant `.ai/` file after every commit** so agents never re-discover
   the system.

6. **Constitution is immutable** — `.ai-company/constitution/rules.md`
   cannot be overridden by any agent. Read sprint state first, update it last.

7. **CLI is frozen** — the Typer command tree is a contract (ADR 0006). New
   features must back-port CLI commands; CI validates the command map.
   Wave 2a token CLI was additive-only (`dashboard token` sub-group); Wave 2b
   made no CLI surface changes.

8. **Workspace resets to HEAD** — commit work promptly; uncommitted files
   (including `.ai/`) get wiped.

9. **Parity test suite is seeded** — `tests/golden/test_parity_read.py`
   (golden CLI output == API JSON) plus `tests/golden/test_parity_wave2b.py`
   (generate/backup contract + shared guard parity) plus
   `tests/golden/test_parity_status.py` (canonical status CLI == API, 2026-08-02).
   Every new read command must add a parity row + parity test (Phase 4 demotion
   trigger depends on it). Wave 2b flipped all remaining safe-write rows to `1+2`.

10. **Known CI flake (ubuntu `test` job, 2026-08-02)** — intermittent native
    `Segmentation fault` (exit 139) right after
    `tests/integration/test_runtime_boot.py` finishes (~15% mark; thread
    teardown boundary; HeartbeatSender/health-monitor threads + SQLite).
    Same-commit rerun passes; `test-windows` never hit it; not introduced by
    the R8/R12 batches (reproduced on a docs-only commit). If CI shows this,
    re-run the failed job before investigating code.

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

*Updated: 2026-08-02 — **Sprint 5.4 T1 SHIPPED** (SQLite live telemetry store: `sync_from_jsonl` incremental watermark sync, facade reads prefer the store w/ JSONL fallback, sync wired into the 30s ticker via `metrics_persist`; suite 1308 → **1320 green**); Sprint 5.3 (`de9c851`) + R12 batch (`147540b` + `75e0595`) + R8/R3/R11 batch (`38a3d7f` + typer-group fix `935beeb`) + **R4 fallback (`1fd0c97`)** all committed + pushed; **R4 `[MITIGATED]`** — shared `services/generate_dispatch.py` fallback (opencode → free/local `ollama`) proven end-to-end across runner/CLI; **D10 persona onboarding SIGNED OFF (R11 → `[MITIGATED]`)**; R12 `[MITIGATED]`; R8 gate live (CLI surface contract, additive-only); R3 parity milestone set (≥40/71 rows by Phase 3); suite 1265 → **1308 green**; **CI green on main (run 30750231104: 8/8 jobs, after one documented-segfault-flake rerun of the ubuntu `test` job)**; **Sprint 5.4 PLANNED & COMMITTED — see "Sprint 5.4 Backlog" above (T1–T4 = 22 pts, T5 CI-flake stretch); next candidates: Sprint 5.5 (Phase 3 desktop), Sprint 5.6 (Svelte 5)***
*Next update: at the next Sprint 5.4 commit (T2 retention/rollup, T3 isolation alerting, or T4 recovery metric)*
