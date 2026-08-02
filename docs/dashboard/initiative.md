# Initiative: GUI Dashboard + OpenCode Desktop as Command Centers

Status: **ACTIVE — Phase 1 DONE (read-only dashboard v1 shipped 2026-08-01); Phase 2 Waves 2a+2b SHIPPED 2026-08-02 — exit criterion met (full generate → review → validate → approve loop from the browser); Phase 3 next (OpenCode desktop as first-class command center)**
Owner: Chief Architect (opencode/big-pickle) · Ratified by: CEO / CIO / CTO / CAIO / CDO / SWE
Last updated: 2026-08-02

> This file is the **living tracker** for the initiative. Every phase, risk, and
> decision below is updated as work lands. Status markers used:
> `[NOT STARTED]`, `[IN PROGRESS]`, `[DONE]`, `[BLOCKED]`, `[OPEN]` (decision/risk).

---

## 1. Mandate (as interpreted)

1. **GUI Dashboard** becomes the primary **human** command center for AI Enterprise OS.
2. **OpenCode desktop** becomes the main **agentic** workbench / command center.
3. **CLI is demoted to a power-user/automation surface — never deleted.**

Operating model ratified by the team: **OpenCode desktop = the workshop;
Dashboard = the boardroom + NOC; CLI = the API-compatible shell underneath both.**

---

## 2. Ground-truth audit (verified against repo on 2026-08-01)

All six findings from the independent expert audit were re-verified directly
against this repository before tracking began. Evidence paths are as found.

| # | Finding | Evidence (verified) | Severity | Status |
|---|---------|---------------------|----------|--------|
| 1 | Generation dispatch map broken: `command_map.yaml` maps 11 targets to 9 prompt files that don't exist; only `bootstrap` + `registry` resolve. Real `prompts/opencode/` has **8 files, differently named** (01–08: bootstrap, registry, generator_engine, cli, document_generator, opencode_agent_generator, dashboard_generator, constitution_loader). | `src/ai_company/cli/command_map.yaml` vs `prompts/opencode/*.md` | **P0** | **[DONE]** — reconciled 2026-08-01; CI integrity test added (see §7.1) |
| 2 | Self-healing doesn't work: all 5 engines `failed` / `heartbeat_timeout`, `restart_count: 0`. Watchdog isolates; supervisor never recovers. Active pipeline `p_recovery_test` ended fully failed. | `runtime/runtime_state.json` | **P0** | **[DONE]** — recovery fix landed (ADR 0007); drill tests green; **end-to-end live drill PASSED 2026-08-01** (§7.6) |
| 3 | "Dashboard" is a 16-line static stub; `docs/architecture.md` lists a "Dashboard Engine" with no source; prompt `07_dashboard_generator.md` is aspirational ("Update automatically"). GUI is greenfield. | `dashboards/sprint_dashboard.html` (16 lines); `docs/architecture.md` line 14; `prompts/opencode/07_dashboard_generator.md` | **P0** | **[DONE]** — Phase 1 complete 2026-08-01: read-only dashboard v1 live on `ai-company serve` (wave 1 API `6d2654b`/`b6d5a26` + wave 2 frontend); 8 views render live data; parity P1 rows SHIPPED (§7.7) |
| 4 | ~60% of telemetry is generated then discarded: metrics/heartbeats/health are in-memory dicts lost on restart; provider token usage is computed (`CompletionResult.usage`) and never persisted. "Model Usage" / "Agent Health" have zero upstream data. | `src/ai_company/runtime/metrics.py` (`MetricsRegistry` = plain dicts, no persistence); `src/ai_company/providers/base.py` (`usage: dict` field, unused) | **P0** | **[DONE]** — telemetry workstream complete (Wave 2b, 2026-08-02): runtime metrics persist to `runtime/metrics_history.jsonl` (30s ticker + manual capture), provider usage to `runtime/provider_usage.jsonl` via `UsageTrackingProvider`; KPI / Model Usage / Agent Health panels on `/telemetry` render live data |
| 5 | Two sources of truth drifting: `command_map.yaml` pins `opencode/north-mini-code-free` + an `architect` agent that is **not defined** in `opencode.json`; `opencode.json` uses `ollama/llama3.1:8b` with agents `build/plan/explore/general`. | `src/ai_company/cli/command_map.yaml` vs `opencode.json` | **P1** | **[DONE]** — `architect` agent added to `opencode.json` 2026-08-01 (see §7.2); command map now an **enforced contract** (ADR 0006, CI integrity gates); model variance documented as decision D4 |
| 6 | All state gitignored, no backup: `memory/`, `events/`, `generated/`, `.ai-company/`, `runtime/`, `reports/`, `scripts/`, `slides/` excluded from git; a dead laptop = full data loss. | `.gitignore` lines 35–58 | **P1** | **[DONE]** — WS-0.5 complete 2026-08-01: nightly bundle + `restore_backup()` + live restore drill (397/397 files) + `.opencode/` template committed |

**Good news (also verified):** the runtime is a mature control plane —
`RuntimeEngine` (status/health/metrics/diagnostics/recover/unisolate),
persisted `EventBus` (replay + dead-letter + history), audit engine,
decision/approval/risk engine, memory engine — all Pydantic-typed and JSON-ready.
`RuntimeStatus`'s docstring already says "used by CLI and dashboard".
**This is surface + transport + data capture, not re-architecture.**

---

## 3. Target architecture (two-command-center model)

```
┌─────────────┐   ┌────────────────────────────┐
│  OpenCode   │   │  GUI Dashboard (browser)   │   ← the two command centers
│  desktop    │   │  boardroom: see + decide   │
│  workshop:  │   └────────────┬───────────────┘
│  delegate+  │                │ REST + WebSocket (127.0.0.1)
│  author     │                ▼
└──────┬──────┘   ┌──────────────────────────────────┐
       │          │  ai-company serve (FastAPI+uvicorn│
       └─dispatch→│  ├─ api/ routers (thin adapters)  │
                  │  ├─ services/ ← THE single source │
                  │  │   of truth (shared by CLI+API) │
                  │  └─ RuntimeEngine + EventBus in-  │
                  │     process (existing, unchanged) │
                  └──────────────┬───────────────────┘
                                 │ SQLite (WAL) telemetry store,
                                 │ derived from JSONL source of truth
```

- **Backend:** FastAPI + plain uvicorn (NOT `[standard]` — uvloop breaks on Windows) + websockets. Three new deps. Pydantic models become API schemas for free.
- **Frontend:** v1 = Jinja2 + htmx (reuses existing Jinja2 dependency, zero Node toolchain) OR Svelte 5 + Vite. **Decision D1 pending** (ADR-001).
- **Real-time:** existing EventBus already has replay + persistence. Dashboard = a bus subscriber: `bus.subscribe()` → per-client `asyncio.Queue` → WebSocket, plus 1–5s snapshot ticker. Reconnect via `?since=<event_id>` + `EventBus.replay()`. No new messaging infra.
- **Service layer:** extract `ai_company/services/` (system, runtime, generation, validation, memory, registry, graph, report, orchestration, agents, opencode_runner). CLI becomes a thin Typer → service → Rich adapter; API is the same service → JSON. **Anti-drift guarantee.**
- **Telemetry:** JSONL stays the append-only source of truth; SQLite (WAL) is a derived, rebuildable projection. 5s `MetricSampler` (reuses scheduler) + provider instrumentation decorator (one choke point on `BaseProvider.chat/complete/embed` → `model.usage`) + run materializer over the event bus.
- **OpenCode integration:** refactor `generate` into `opencode_runner` (streamed subprocess, exit code, files touched, watchdog-tracked) → "Dispatch to OpenCode" from dashboard + "Open in OpenCode desktop" deep links. Prompts stay plain Markdown — portable, not vendor-locked.

---

## 4. Phase tracker

### Phase 0 — Foundation repair (2–3 wks, zero dashboard code) — MANDATORY GATE

CIO refuses to approve the build without this phase. **[DONE]** 2026-08-01 — all 7 workstreams
complete; drills run live (restore 397/397 files, recovery restart-before-isolate); Phase 1 opened same day.

| WS | Workstream | Status | Exit criterion |
|----|-----------|--------|----------------|
| 0.1 | Fix `command_map.yaml` ↔ `prompts/opencode/` drift; CI integrity check (every target resolves) | **[DONE]** 2026-08-01 | **Two gates:** `tests/test_command_map_integrity.py` (5 tests) + `python -m ai_company.integrity.check_command_map` (module), both wired into CI; all 8 prompts dispatchable, all 14 targets resolve |
| 0.2 | Fix supervisor/recovery: failures recover or escalate (scripted failure drill ends *recovered*) | **[DONE]** (ADR 0007) | Fix landed in `runtime/recovery.py` + `supervisor.py` + `engine.py` (restart-before-isolate, per-engine factories); drill tests `test_engine_failure_recovers_via_factory` / `test_restart_via_factory` / `test_max_attempts_exhausted` green; **live drill run 2026-08-01 (§7.6)** — heartbeat_timeout → 1 restart via factory, not isolated, RUNNING/HEALTHY |
| 0.3 | Reconcile `opencode.json` vs `command_map.yaml` models/agents (add missing `architect` agent) | **[DONE]** 2026-08-01 | `--agent architect` resolves; integrity test asserts agent defined (guards recurrence) |
| 0.4 | Ship opt-in baseline telemetry (CLI invocation events) — *before* the dashboard, so the pivot is provable | **[DONE]** 2026-08-01 | `ai_company/telemetry/cli.py` (fail-open, JSONL); **verified live**: every `ai-company` invocation appends to `runtime/cli_telemetry.jsonl` via `ctx.call_on_close` hook (see §7.4) |
| 0.5 | Nightly backup bundle of gitignored state + restore drill; `uv audit` in CI; `.env.example`; commit `.opencode/` config template | **[DONE]** 2026-08-01 | `ai_company/backup/` + `nightly-backup.yml` + `.env.example` + `uv audit` in CI landed; `restore_backup()` (safe extraction) + `--restore` flag + 8 unit tests; **live restore drill PASSED** (397/397 files byte-for-byte, SHA-256, §7.5); `.opencode/` template completed (agents + package.json + `.gitignore`) |
| 0.6 | ADRs (stack D1, topology D2, API contract D3); parity matrix v0 | **[DONE]** | ADR 0001–0009 merged (0008 = frontend stack proposed, 0009 = API contract proposed); `docs/dashboard/parity-matrix-v0.md` (capability + command-exhaustive, 70 commands) |
| 0.7 | windows-latest CI job (currently Ubuntu-only — real gap for a Windows-first project) | **[DONE]** 2026-08-01 | `test-windows` job on `windows-latest` added (full pytest suite, bash rc-5 guard); 1054 tests pass on Windows locally |

### Phase 1 — Read-only Dashboard v1 (4–6 wks) — 80% of demo/exec value for ~30% effort

`[DONE]` — **shipped 2026-08-01.** Wave 1 API (`6d2654b`/`b6d5a26`) + wave 2 frontend
(WS-1.0→WS-6.0) both merged, CI green (1142 tests), live on `ai-company serve`.

- ✅ `ai-company serve` booting FastAPI + WS bridge (read-only contract v1, ADR 0009).
- ✅ Views: Overview/Pulse, System Health, Agents (roster), Runs & History, Memory (read), Reports, Validation gate, Registry/Org graph — all 8 render live data.
- ✅ IA from the 11 sections of prompt `07_dashboard_generator.md`; Markdown + Mermaid reports rendered in-page (marked + DOMPurify + mermaid.js, vendored under CSP `script-src 'self'`).
- ✅ Live refresh ≤5s (WS + poll ticker, `?since=` replay, dedupe by `event_id`, auto-reconnect); honest four-state statuses with timestamps (R12), "data pending" for KPI/Agent Health telemetry gaps (R5).
- ✅ Loopback-only, read-only by default; scoped page CSP (`script-src 'self'`, no `unsafe-inline`); API responses keep `default-src 'none'`.
- ✅ Parity test suite seed green: `tests/golden/test_parity_read.py` (9 tests — CLI output == API JSON).
- **Exit criteria met:** an exec self-serves the "pulse" page; an operator answers "is the system healthy?" in <5s from a browser.
- Work plan: `docs/dashboard/phase1-workplan.md` → **DONE**. Parity matrix P1 rows → **SHIPPED**. OD1–OD4 resolved (see workplan §7).

### Phase 2 — Operational dashboard (4–6 wks) — the actual pivot

`[DONE]` — **Waves 2a + 2b SHIPPED 2026-08-01/02.** Exit criterion met: an
operator runs a full generate → review → validate → approve loop without
opening a terminal. Work plan: `docs/dashboard/phase2-workplan.md` → **DONE**.
Parity matrix P2 rows → **`1+2`** (all safe-write rows live on both surfaces).

- ✅ Write-auth security scheme live (ADR 0010): opaque 256-bit bearer token
  (`runtime/.write_token`, env override, optional SHA-256 hash-at-rest),
  per-run CSRF synchronizer token (`GET /api/write-csrf` + `X-CSRF-Token`),
  mandatory `audit.write` / `audit.write_rejected` audit on every mutation
  (fail-open JSONL; rejected payloads never leak token/CSRF). Non-loopback
  Hosts fail closed; loopback is token-optional with `--require-loopback-token`.
- ✅ Mutation endpoints live (20 POSTs, Wave 2a) + Wave 2b writes: generate
  dispatch/run/log/cancel, decision inbox (create/approve/reject/escalate/
  cancel), per-artifact company validators, graph export, company CRUD
  (files/departments/manifest), agent sync, backup create/status, telemetry
  persist. All behind the shared `api/guards.py` `WriteGuard` (ADR 0010
  semantics unchanged; high-impact actions require a `reason`, 422).
- ✅ **Generate dispatcher (Wave 2b):** `services/generate_runner.py` streams
  OpenCode subprocess output to `runtime/generate_logs/<run_id>.log`, persists
  `runtime/generate_runs.jsonl`, boot replay marks interrupted runs; `/generate`
  panel has target select, prompt input, live log tail, history.
- ✅ **Decision/approval inbox (Wave 2b):** `/decisions` renders decision-engine
  cards (risk score, approval matrix) with approve / reject / escalate / cancel;
  inbox survives restarts via `DecisionHistory.import_decisions()`.
- ✅ **R5 telemetry (Wave 2b):** `telemetry/metrics.py` + `telemetry/provider.py`
  JSONL persistence + `UsageTrackingProvider`; `/telemetry` KPI / Model Usage /
  Agent Health panels live; 30s auto-persist ticker in app lifespan.
- ✅ **Backup tile (R6):** pulse view backup action + status via `POST
  /api/backup` / `GET /api/backup/status` (ADR 0001).
- ✅ **WS `?token=` enforcement** for non-loopback (close 1008, ADR 0010 §1).
- ✅ Suite 1142 → **1252 tests green** (1171 Wave 2a + wave-2b/telemetry/parity
  additions); ruff/mypy/format/command-map/lock/audit clean.
- **Exit:** ✅ met — full generate → review → validate → approve loop live.

### Phase 3 — OpenCode desktop as first-class command center (3–4 wks)

`[NOT STARTED]` — note: groundwork exists (`src/ai_company/agents/` agent-sync engine + `tests/test_agents_sync.py`, currently untracked).

- Session bridge: every session loads constitution/state and closes by posting telemetry (session endpoint) → Model Usage and Agent Health become real for the first time.
- Deep links both ways: dashboard → "continue in OpenCode"; desktop → "submit for review".
- **Exit:** ≥90% of generation targets runnable desktop-first without typing a CLI command.

### Phase 4 — CLI demotion + migration (4 wks, trigger-gated)

`[NOT STARTED]`

- CLI gets `--deprecated` banners; `ai-company dashboard` launcher; README/docs rewritten dashboard-first; CLI → "Power users / automation" appendix.
- **Demotion trigger (all must hold 2 weeks):** 100% parity-matrix coverage, parity test suite green, ≥80% of operator actions via GUI/desktop, zero "no GUI path" escalations.
- **The CLI is never deleted.** It is the automation backbone, rollback path, and integration contract.

---

## 5. Risk register (consolidated, with mitigations)

| # | Risk | Severity | Mitigation | Status |
|---|------|----------|-----------|--------|
| R1 | Broken generate dispatch (phantom targets) | Critical, certain | Phase 0 fix + CI integrity check | **[MITIGATED]** — 0.1 done |
| R2 | System doesn't self-heal (watchdog isolates, no recovery) | Critical | Recovery policies in Phase 0; recovery-success metric; alert on isolation | **[MITIGATED]** — ADR 0007 + drill tests green; **live end-to-end drill PASSED (§7.6)**; recovery-success metric + isolation alerting moved to Phase 2 backlog |
| R3 | Dual-interface drift (CLI vs dashboard re-implementing logic) | High | Single `services/` layer; contract tests (golden CLI output == API JSON); parity test suite in CI | **[PARTIALLY MITIGATED]** — ADR 0003 accepted; facade is the single surface; parity seeds green (`tests/golden/test_parity_read.py`, 9 commands + `tests/golden/test_parity_wave2b.py`, generate/backup contract + shared guard); **2026-08-02 added `tests/golden/test_parity_status.py` — `runtime status` CLI vs `GET /api/status` canonical facts (2 tests)**. **Explicit milestone (2026-08-02): ≥40 of 71 command rows parity-tested by Phase 3 close-out; every new command adds its parity test in the same change (parity-matrix-v0.md)** |
| R4 | OpenCode vendor lock-in / version churn | High | Provider abstraction at dispatcher; portable Markdown prompts; pinned version + doctor probe; headless generate fallback; never fork/re-skin desktop app | **[MITIGATED]** — **decision D9 (CEO sign-off 2026-08-02): free/local models are the official fallback** (e.g. `ollama/llama3.1:8b`, D4). **End-to-end fallback shipped 2026-08-02**: shared `services/generate_dispatch.py` powers both the streaming runner and the frozen CLI; when OpenCode is missing, fails to start, or exits non-zero, dispatch runs the local model via `ollama` (tunable in `config/runtime/model_fallback.yaml`); run records name the provider/model that actually produced the result (honest telemetry, R5); proven end-to-end (runner fallback e2e with stub binaries, dispatch unit tests, CLI wiring tests) — suite 1308 green |
| R5 | Dashboard ships with no data (Model Usage/Agent Health empty) | High | Capture-first ordering: telemetry (Phases 0–1) precedes panels (Phase 2); stub honestly with "data pending," never fake | **[MITIGATED]** — telemetry workstream complete (Wave 2b, 2026-08-02): metrics persistence (`runtime/metrics_history.jsonl`, 30s ticker) + provider usage (`runtime/provider_usage.jsonl`, `UsageTrackingProvider`) + live KPI / Model Usage / Agent Health panels on `/telemetry`; Phase 1 views render real data throughout |
| R6 | Data loss (all state gitignored, single machine) | High | Nightly backup bundle + quarterly restore drill + backup tile with alerting | **[MITIGATED]** — nightly bundle + restore drill done 2026-08-01 (WS-0.5, 397/397 files); **backup tile shipped Wave 2b (2026-08-02)**: pulse view backup action + status via `POST /api/backup` / `GET /api/backup/status` (ADR 0001) |
| R7 | Scope creep (console becomes mini-ERP) | Medium | CEO's NOT-do list: no SaaS/multi-tenant, no visual pipeline-builder v1, no own agent runtime, ≤30% effort on UI, no new metrics until serving layer lands | **[OPEN]** |
| R8 | Breaking 500+ tests / CI regression | High | Additive-only refactor; engines untouched; CLI surface frozen; full suite green each sprint; parity is a release blocker | **[PARTIALLY MITIGATED]** — guardrails confirmed (engines unchanged in 0.1); **Phase 1 landed additive-only: 1070 → 1142 tests green on Linux + Windows, no CLI or engine changes**; **Phase 2 Waves 2a+2b: 1142 → 1252 green, still additive-only**; **2026-08-02: CLI surface integrity gate live** — `integrity/check_cli_surface.py` vs committed contract in both lint jobs (removal/rename/change = build failure; additive drift requires `--update` + commit); suite 1289 green |
| R9 | Localhost security (web server = new attack surface) | Medium-High | Bind 127.0.0.1 only; Host-header + CORS checks; token mode when non-loopback; keys in OS keyring, never rendered; CSP; DOMPurify on all Markdown | **[MITIGATED]** — loopback bind + Host allowlist + scoped page CSP + DOMPurify (Phase 1) **+ ADR 0010 shipped Wave 2a (2026-08-01):** fail-closed non-loopback token mode, loopback token-optional with `--require-loopback-token`, per-run CSRF, mandatory write audit, hash-at-rest option; keys never rendered (keyring intentionally not used per ADR 0010 — CISO preference, single-platform portability); token value printed only on first-time creation |
| R10 | Windows/uvicorn issues | Medium | Plain uvicorn (no uvloop), explicit port + friendly errors, `proc.terminate()` not `os.kill`, add windows-latest CI job | **[MITIGATED]** — windows-latest CI job added 2026-08-01; plain uvicorn + `proc.terminate()` enforced; explicit port + friendly errors land with `ai-company serve` (Phase 1) |
| R11 | User confusion during transition | High | Category rule: read = dashboard, safe write = both, destructive/bulk = CLI-only; "Equivalent CLI command" tooltips; persona onboarding (View/Operate/Develop); frozen CLI | **[MITIGATED]** — category rule codified in parity matrix v0; **"Equivalent CLI command" tooltips on every Phase 1 view**; **D10 SIGNED OFF by CEO 2026-08-02** — three personas View/Operate/Develop, one skippable first-run tour each + tooltips, no tutorial system (see §6); delivery lands with Phase 2/3 features |
| R12 | Misleading statuses (four overlapping vocabularies; stopped ≠ broken) | Medium | One canonical four-state system (All good / Watch / Needs action / Unknown); every status time-stamped; color + icon + text, never color alone | **[MITIGATED]** — **canonical status service shipped 2026-08-02** (`services/status_service.py`): one four-state vocabulary (`ok`/`watch`/`action`/`unknown`) + `timestamp` on every status, derived by phase state machine (stopped/stopping → `watch`, never `action` — stopped ≠ broken); **all surfaces unified**: CLI `runtime status` prints `Overall:`, `GET /api/status` + `GET /api/health` return canonical `overall`, dashboard pulse/System Health views + app.js chip use the same vocabulary (color+icon+text); golden parity test `tests/golden/test_parity_status.py` locks CLI == API; **also fixed the root cause of misleading "unhealthy" flags — passive engines were heartbeat-timeouted/isolated after boot (`HeartbeatSender` liveness worker + read-model `check_same_thread=False`)** |

---

## 6. Decision log

| # | Decision | Options | Status | Note |
|---|----------|---------|--------|------|
| D1 | Frontend for v1 | Jinja2+htmx (zero Node, fastest) vs Svelte 5 (full interactivity) | **[DECIDED]** | ADR 0008 accepted (v1 = Jinja2+htmx; Svelte 5 = v2 path, Phase 4) |
| D2 | Topology: dashboard as runtime engine; `services/` single source of truth | (ratified model) | **[DECIDED]** | ADR 0002 + 0003 accepted |
| D3 | API contract: REST + WebSocket, `?since=` replay reconnect | (ratified model) | **[DECIDED]** | ADR 0009 accepted; contract v1 shipped (Phase 1 wave 1); **Phase 1 wave 2 extended the read surface to all parity P1 rows (19 new endpoints)** |
| D4 | Dispatch model variance | `opencode/north-mini-code-free` (desktop-first, no key) vs `ollama/llama3.1:8b` (local default) | **[DECIDED]** | Per-target entries retained; command map is an enforced contract (ADR 0006); `architect` agent defined |
| D5 | North-star metric | **Recommendation: share of operator actions via Dashboard/OpenCode desktop, target ≥80% by month 6, measured by Phase-0 telemetry** | **[DECIDED]** | **SIGNED OFF by CEO 2026-08-02** — metric = share of operator actions via Dashboard/OpenCode desktop; target ≥80% by month 6; baseline = CLI telemetry (`runtime/cli_telemetry.jsonl`), GUI/desktop action telemetry to be added in Phase 3 so numerator/denominator are honest; Phase 4 demotion trigger depends on it |
| D8 | Phase 2 write auth scheme | (ratified model: opaque bearer token + double-submit CSRF + mandatory write audit; fail-closed non-loopback; optional hash-at-rest; high-impact reason requirement) | **[DECIDED]** | **ADR 0010 accepted 2026-08-01** and shipped with Wave 2a (Sprint 5.2); CISO / Cybersecurity Architecture / Software Engineering reviewed |
| D9 | R4 fallback provider strategy | Free models and local models as fallbacks (e.g. `ollama/llama3.1:8b` local default already in dispatch map, D4) | **[DECIDED]** | **CEO sign-off 2026-08-02**: when OpenCode dispatch fails (version pin break, outage, doctor failure), generation falls back to free/local models — no vendor lock-in. **Proven by e2e test 2026-08-02**: `services/generate_dispatch.py` fallback path green across runner/CLI — R4 → `[MITIGATED]` |
| D10 | Persona onboarding scope (R11) | **Recommendation: three personas, in-view guidance only** — View (read-only: sign-in → system-health pulse → panels; no write paths shown), Operate (read + safe writes: decision inbox, generate loop, backup — the "operator" of the north-star metric D5), Develop (full: registry edits, agent sync, CLI reference, `Equivalent CLI command` tooltips). Flows: one guided first-run tour per persona (3–5 screens, skippable) + persistent "Equivalent CLI command" tooltips (already shipped on Phase 1 views) | **[DECIDED]** | **SIGNED OFF by CEO 2026-08-02** — three personas View/Operate/Develop; one skippable first-run tour each + persistent tooltips; **no full tutorial system**; destructive/bulk rows stay CLI-only and are surfaced as such in the Develop persona, never offered as GUI actions. Landing phase: Phase 2/3 (after R12 status unification, so tours show the canonical status vocabulary). R11 → `[MITIGATED]` on this sign-off |

---

## 7. Phase 0 execution log

### 7.1 WS-0.1 DONE — command_map reconciliation + integrity gate (2026-08-01)

- `src/ai_company/cli/command_map.yaml` reconciled: all 14 targets (11 legacy re-pointed + 3 new: `cli`, `dashboard`, `constitution`) resolve to real files in `prompts/opencode/`.
- Mapping rationale: legacy conceptual targets (`board/exec/dept/specialist`) map to `06_opencode_agent_generator.md` which explicitly generates Executives/Departments/Specialists/Boards; `workflow/prompt/graph` map to `03_generator_engine.md` (the engine generates Python/Markdown/Prompts and the org graph).
- Integrity gate: `tests/test_command_map_integrity.py` asserts every target resolves and every prompt file is referenced (runs in CI `test` job → prevents recurrence).

### 7.2 WS-0.3 DONE — opencode.json reconciliation (2026-08-01)

- Added the missing `architect` agent to `opencode.json` (model `opencode/north-mini-code-free`, primary) so `ai-company generate <target>` → `opencode run --agent architect` resolves.
- **Concurrency incident (process finding):** a parallel agent session was editing `opencode.json` and `src/ai_company/agents/` at the same time; both writers added `architect`, producing malformed duplicate JSON. The new integrity test (`test_dispatch_agent_defined_in_opencode_json`) caught it in CI. Resolved to a single `architect` entry whose model matches the dispatch map. **Lesson:** parallel writers on the same config files must coordinate (tracking rule §8.7).

### 7.3 WS-0.2 DONE — recovery (drill test evidence)

Root cause on record: `runtime_state.json` shows all 5 engines `failed`/`heartbeat_timeout` with `restart_count: 0` and an active `p_recovery_test` pipeline that ended fully failed. Supervisor recovery policy is the fix target; scripted failure drill is the acceptance test. Fix landed (ADR 0007, restart-before-isolate, per-engine factories) and the live drill passed 2026-08-01 (see §7.6).

### 7.4 Phase 0 hygiene — flaky timing test fixed (2026-08-01)

- `tests/unit/runtime/test_metrics.py::test_timed_context_manager` asserted `>= 0.01` after `sleep(0.01)`; on Windows this randomly measured `0.0` (monotonic clock resolution) — a pre-existing CI-breaker under R8. Fixed with a 50ms sleep and tolerant 0.04s bound. Test-only change; engines untouched.

### 7.5 Phase 0 close-out — restore drill + `.opencode/` template (2026-08-01)

- `restore_backup()` added to `ai_company/backup/backup.py`: safe extraction — explicit rejection of absolute paths and `..` traversal plus tarfile `filter="data"` — and a `--restore ARCHIVE` CLI mode; 8 unit tests in `tests/unit/backup/test_backup.py` (round-trip, byte-identical, traversal/absolute rejection, main flows).
- **Live restore drill PASSED** (`scripts/restore_drill.py`): bundled the five gitignored runtime dirs (238 KB), restored into an isolated temp root, verified **397/397 files byte-for-byte (SHA-256)**, exit 0. Closes finding #6 / R6 restore half.
- `.opencode/` config template completed: `templates/opencode/` now mirrors the real config — `agents/architect.md`, `agents/builder.md`, `package.json` (`@opencode-ai/plugin@1.18.7`) and `.gitignore` (node_modules + lockfiles stay machine-local).

### 7.6 Phase 0 close-out — live recovery drill + Windows CI (2026-08-01)

- **Live self-healing drill PASSED** (`scripts/runtime_recovery_drill.py`): real `RuntimeEngine` + `RecoveryManager` + `Supervisor` (real runtime config) — `heartbeat_timeout` on a registered engine → **restart via factory (1 restart, 1 attempt), NOT isolated, state RUNNING/HEALTHY**. Closes the last WS-0.2 acceptance item (ADR 0007 proven end-to-end).
- **Windows CI landed (WS-0.7):** `test-windows` job added to `.github/workflows/ci.yml` on `windows-latest` running the full pytest suite (bash rc-5 guard). 1054 tests pass on Windows locally. Closes risk R10's CI gap.

### 7.7 Phase 1 close-out — read-only dashboard v1 (2026-08-01)

- **WS-1.0 services layer (ADR 0003):** `RuntimeFacade` extended with 16 read methods — `registry_list/show/verify`, `executives_list/show`, `org_chart`, `memory_list/get/search/stats/snapshots`, `graph_show/stats`, `reports_list`, `report_generate_read`, `validate_read`, `diagnostics`, `orchestration_status/history`, `generate_targets`. All thin adapters over existing engines; 33 unit tests (`tests/unit/services/test_runtime_facade_read.py`).
- **WS-2.0 API (ADR 0009):** 19 new GET endpoints registered (literal segments before `{name}`/`{type}` params); `/` now serves HTML, index moved to `/api`; 26 integration tests + 5 frontend/CSP tests (`tests/unit/api/test_api_domain.py`), golden parity against the tracked `company/` fixture.
- **WS-3.0 frontend shell (ADR 0008 v1):** vendored htmx 1.9.12 + ws ext, marked 12.0.2, DOMPurify 3.1.6, mermaid 10.9.1 (`static/vendor/` + provenance `README.md`); `dashboard.css` + `app.js` (WS auto-reconnect, `?since=` replay, dedupe by `event_id`, staleness classes, marked+DOMPurify, mermaid render). **Scoped page CSP** (`default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' ws:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`) — API responses keep `default-src 'none'`.
- **WS-4.0/5.0:** all 8 views live (Pulse, System Health, Agents, Runs & History, Memory, Reports, Validation, Registry/Org graph); ≤5s refresh via WS + poll ticker; honest four-state statuses (R12), "data pending" for telemetry gaps (R5).
- **WS-6.0:** parity test suite seed (`tests/golden/test_parity_read.py`, 9 tests — CLI output == API JSON for registry/exec/graph/targets/validate/doctor); full suite **1070 → 1142 tests green** (Linux + Windows, ruff/mypy/format/lock/audit/build/validate all green); live smoke of all 11 routes with correct scoped CSP. **No CLI or engine changes** (ADR 0005/0006 respected).

### 7.8 Phase 2 Wave 2a close-out — write auth + operational writes (2026-08-01)

- **ADR 0010 ratified** (Proposed → Accepted, decision D8) and shipped in the
  same change. Security scheme: opaque `secrets.token_urlsafe(32)` bearer token
  (`runtime/.write_token`, env override `AI_ENTERPRISE_WRITE_TOKEN`, optional
  SHA-256 hash-at-rest via `--hash-at-rest`), per-run CSRF synchronizer token
  (`GET /api/write-csrf`, echoed in `X-CSRF-Token`), mandatory
  `audit.write`/`audit.write_rejected` on every mutation (fail-open to
  `runtime/.audit.failed.jsonl` — never blocks localhost writes; rejected
  payloads never include the submitted token/CSRF).
- **Write guard (R9 closure):** non-loopback Host → token mandatory
  (fail-closed); loopback → token optional unless `--require-loopback-token`;
  provided token must verify (else 401); CSRF missing/mismatch → 403.
  `host_allowed()` allowlist = `{"127.0.0.1","localhost","::1","[::1]"}` (bare
  `::1` rejected per RFC 3986 — `[::1]:port` required).
- **High-impact actions** (`HIGH_IMPACT_ACTIONS`): `runtime.stop`,
  `runtime.restart`, `runtime.recover`, `runtime.unisolate`,
  `orchestrate.rollback` — require a `reason` field (422 otherwise); reason is
  captured in the audit payload.
- **Facade write adapters** appended to `RuntimeFacade` (auth enforced at the
  API layer, not the facade — engines untouched, ADR 0005/0006): runtime
  start/stop/restart/reload/recover/unisolate; orchestrate plan/start/resume/
  retry/rollback; memory save/update/snapshot/restore/export/archive/unarchive;
  validate run; report generate; build; bootstrap.
- **Frontend:** Write History page (`/writes`) with token input + audit table;
  operator action buttons with native confirm dialogs (reason required for
  high-impact); CSP-safe JS (DOM textContent only, no innerHTML).
- **CLI (additive):** `ai-company serve --hash-at-rest --require-loopback-token`;
  `ai-company dashboard token create|revoke|list|info` — value printed only on
  first-time creation; rotation never echoes the new value (verified by test);
  env-managed tokens refuse CLI revoke.
- **Tests:** `tests/unit/api/test_auth.py` (18) + `test_write_endpoints.py`
  (11) — host allowlist incl. `[::1]:8000` / rejection of bare `::1` and
  `127.0.0.1.evil.com`, CSRF roundtrip, rotation semantics, hash-at-rest,
  fail-open JSONL, audit payloads, no token/CSRF leakage, `require_loopback_token`
  mode. Full suite **1142 → 1171 green**; ruff/mypy/format/uv-lock/uv-audit
  clean; parity matrix P2 rows → `1+2` (Wave 2a subset; generate rows → `2b`).

### 7.9 Phase 2 Wave 2b close-out — generate→review→validate→approve loop + R5 telemetry (2026-08-02)

- **Generate dispatcher** (`services/generate_runner.py`): thread-safe
  streaming dispatcher — `start/cancel/get/list_runs/log_tail`; child stdout
  streams to `runtime/generate_logs/<run_id>.log`; runs persist to
  `runtime/generate_runs.jsonl`; boot replay marks queued/running runs
  `interrupted by restart`; `shell=False`; fail-open. 9 unit tests with a
  `_FakeProc`.
- **Shared guard** (`api/guards.py`): `WriteGuard` (`guard()/require_reason()/
  audited()/reject()`) + `HIGH_IMPACT_ACTIONS` — `write_endpoints.py` migrated
  so Wave 2a and Wave 2b endpoints share the exact ADR 0010 semantics (bearer
  token + `X-CSRF-Token` + `audit.write`/`audit.write_rejected` fail-open
  JSONL; high-impact reason → 422). Guard parity proven by
  `tests/golden/test_parity_wave2b.py` (401 token-enforced loopback on both
  wave 2a `/api/runtime/start` and wave 2b `/api/generate`; 403 missing CSRF).
- **Decision/approval inbox:** facade `decisions_list/get/create/approve/
  reject/escalate/cancel` over the existing decision engine; record-once
  semantics (no facade double-record); inbox survives restarts via
  `DecisionHistory.import_decisions()`; `engine.reject()` added. `/decisions`
  renders risk cards with approve / reject / escalate / cancel actions.
- **Per-artifact validators:** `validate_artifacts` wraps each per-artifact
  `ValidationReport` (board/exec/dept/specialist/workflow/prompt/docs) in a
  `ValidatorResult` — parity against CLI `validate` PASS/FAIL lines (5 tests).
- **Remaining P2 write surfaces:** graph export write, company CRUD write
  (files/departments/manifest), agent sync (`AgentSyncEngine(config=...)`),
  backup create/status, telemetry persist — all behind the shared guard.
- **R5 telemetry workstream (finding #4 close):** `telemetry/metrics.py`
  (`log_metrics_snapshot`/`read_metrics_history`/`metrics_history_summary` →
  `runtime/metrics_history.jsonl`), `telemetry/provider.py`
  (`record_provider_usage`/`read_provider_usage`/`provider_usage_summary` →
  `runtime/provider_usage.jsonl`, aggregated by model), `providers/usage.py`
  `UsageTrackingProvider`, `ProviderFactory(..., track_usage=False)`. 30s
  auto-persist ticker in app lifespan + manual "Capture now". 10 tests.
- **Frontend:** `/generate` (targets, prompt, live log tail, run history),
  `/decisions` (approval inbox), `/telemetry` (KPI / Model Usage / Agent
  Health), pulse backup tile + age chip; CSP-safe `data-write`/
  `data-action` wire helpers; nav updated; wave-2b CSS section.
- **WS `?token=` enforcement** for non-loopback deployments (close 1008,
  ADR 0010 §1) — verified by tests.
- **Tests:** 10 telemetry + 9 generate-runner + 24 facade wave 2b + 24 API
  wave 2b (incl. page renders with CSP header) + 5 golden parity wave 2b.
  Full suite **1171 → 1252 green**; ruff/mypy/format/command-map clean;
  parity matrix safe-write rows → **`1+2`**; R5 → **MITIGATED**, R6 →
  **MITIGATED** (backup tile), finding #4 → **DONE**.

---

## 8. Change tracking rules (how this doc stays honest)

1. **Statuses are updated in the same change that ships the work** — never retroactively "for luck."
2. Every phase/WS row ships with its **exit criterion demonstrated** (test output, drill log, or demo) before `[DONE]`.
3. Risk rows flip to `[MITIGATED]` only when the mitigation is verified, not when it is planned.
4. Decisions flip to `[DECIDED]` only on explicit sign-off (ADR merged + owner noted).
5. CLI surface is **frozen** through Phase 3; any CLI change must be additive and parity-matrix-updated.
6. `runtime/runtime_state.json` and telemetry JSONL are the ground truth for health claims; the dashboard must never render a status the state file does not support.
7. Parallel writers on the same config files must coordinate before editing (`git status` check first); the CI integrity gates will catch conflicts but coordination is cheaper.
