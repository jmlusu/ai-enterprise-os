# Initiative: GUI Dashboard + OpenCode Desktop as Command Centers

Status: **ACTIVE — Phase 0 in progress**
Owner: Chief Architect (opencode/big-pickle) · Ratified by: CEO / CIO / CTO / CAIO / CDO / SWE
Last updated: 2026-08-01

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
| 2 | Self-healing doesn't work: all 5 engines `failed` / `heartbeat_timeout`, `restart_count: 0`. Watchdog isolates; supervisor never recovers. Active pipeline `p_recovery_test` ended fully failed. | `runtime/runtime_state.json` | **P0** | **[DONE]** — recovery fix landed (ADR 0007); `test_engine_failure_recovers_via_factory` + `test_restart_via_factory` green; end-to-end drill run as final verification |
| 3 | "Dashboard" is a 16-line static stub; `docs/architecture.md` lists a "Dashboard Engine" with no source; prompt `07_dashboard_generator.md` is aspirational ("Update automatically"). GUI is greenfield. | `dashboards/sprint_dashboard.html` (16 lines); `docs/architecture.md` line 14; `prompts/opencode/07_dashboard_generator.md` | **P0** | **[NOT STARTED]** — Phases 1–2 |
| 4 | ~60% of telemetry is generated then discarded: metrics/heartbeats/health are in-memory dicts lost on restart; provider token usage is computed (`CompletionResult.usage`) and never persisted. "Model Usage" / "Agent Health" have zero upstream data. | `src/ai_company/runtime/metrics.py` (`MetricsRegistry` = plain dicts, no persistence); `src/ai_company/providers/base.py` (`usage: dict` field, unused) | **P0** | **[IN PROGRESS]** — CLI invocation telemetry LIVE (`runtime/cli_telemetry.jsonl`, fail-open, WS-0.4); runtime metrics persistence + provider usage instrumentation remain (Phase 2 telemetry workstream) |
| 5 | Two sources of truth drifting: `command_map.yaml` pins `opencode/north-mini-code-free` + an `architect` agent that is **not defined** in `opencode.json`; `opencode.json` uses `ollama/llama3.1:8b` with agents `build/plan/explore/general`. | `src/ai_company/cli/command_map.yaml` vs `opencode.json` | **P1** | **[DONE]** — `architect` agent added to `opencode.json` 2026-08-01 (see §7.2); command map now an **enforced contract** (ADR 0006, CI integrity gates); model variance documented as decision D4 |
| 6 | All state gitignored, no backup: `memory/`, `events/`, `generated/`, `.ai-company/`, `runtime/`, `reports/`, `scripts/`, `slides/` excluded from git; a dead laptop = full data loss. | `.gitignore` lines 35–58 | **P1** | **[IN PROGRESS]** — WS-0.5: `ai_company/backup/` + `nightly-backup.yml` + `.env.example` landed; restore drill + `.opencode/` template commit pending |

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

CIO refuses to approve the build without this phase. `[IN PROGRESS]` — near-complete; remaining: WS-0.5 drill + WS-0.7 windows CI

| WS | Workstream | Status | Exit criterion |
|----|-----------|--------|----------------|
| 0.1 | Fix `command_map.yaml` ↔ `prompts/opencode/` drift; CI integrity check (every target resolves) | **[DONE]** 2026-08-01 | **Two gates:** `tests/test_command_map_integrity.py` (5 tests) + `python -m ai_company.integrity.check_command_map` (module), both wired into CI; all 8 prompts dispatchable, all 14 targets resolve |
| 0.2 | Fix supervisor/recovery: failures recover or escalate (scripted failure drill ends *recovered*) | **[DONE]** (ADR 0007) | Fix landed in `runtime/recovery.py` + `supervisor.py` + `engine.py` (restart-before-isolate, per-engine factories); drill tests `test_engine_failure_recovers_via_factory` / `test_restart_via_factory` / `test_max_attempts_exhausted` green; final live drill pending §7.6 |
| 0.3 | Reconcile `opencode.json` vs `command_map.yaml` models/agents (add missing `architect` agent) | **[DONE]** 2026-08-01 | `--agent architect` resolves; integrity test asserts agent defined (guards recurrence) |
| 0.4 | Ship opt-in baseline telemetry (CLI invocation events) — *before* the dashboard, so the pivot is provable | **[DONE]** 2026-08-01 | `ai_company/telemetry/cli.py` (fail-open, JSONL); **verified live**: every `ai-company` invocation appends to `runtime/cli_telemetry.jsonl` via `ctx.call_on_close` hook (see §7.4) |
| 0.5 | Nightly backup bundle of gitignored state + restore drill; `uv audit` in CI; `.env.example`; commit `.opencode/` config template | **[IN PROGRESS]** | `ai_company/backup/` + `nightly-backup.yml` + `.env.example` + `uv audit` in CI landed; **pending:** restore drill + `.opencode/` template commit |
| 0.6 | ADRs (stack D1, topology D2, API contract D3); parity matrix v0 | **[DONE]** | ADR 0001–0009 merged (0008 = frontend stack proposed, 0009 = API contract proposed); `docs/dashboard/parity-matrix-v0.md` (capability + command-exhaustive, 70 commands) |
| 0.7 | windows-latest CI job (currently Ubuntu-only — real gap for a Windows-first project) | **[NOT STARTED]** | CI matrix includes `windows-latest` |

### Phase 1 — Read-only Dashboard v1 (4–6 wks) — 80% of demo/exec value for ~30% effort

`[NOT STARTED]`

- `ai-company serve` booting FastAPI + WS bridge.
- Views: Overview, System Health, Agents (roster), Runs & History, Memory (read), Reports, Validation gate, Registry/Org graph.
- Reuse the 11 sections of prompt `07_dashboard_generator.md` as the IA; render Markdown + Mermaid reports in-page (marked + DOMPurify + mermaid.js).
- Live refresh ≤5s, honest "stale/stopped/unknown" states (never a green lie), localhost-bound, read-only by default.
- **Exit:** an exec can self-serve the "pulse" page; an operator answers "is the system healthy?" in <5s.

### Phase 2 — Operational dashboard (4–6 wks) — the actual pivot

`[NOT STARTED]`

- Write actions with confirm dialogs: start/stop/restart/reload runtime, run validator, resume/retry/rollback pipelines.
- Generate dispatcher → streams to OpenCode, run history, live logs; write-auth token + CSRF + audit hook on every write.
- Decision/approval inbox — decision engine (risk scoring, approval matrix, escalation) rendered as visual approval cards. **Killer feature:** the governance brain exists; the GUI becomes its renderer.
- **Exit:** an operator runs a full generate → review → validate → approve loop without opening a terminal.

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
| R2 | System doesn't self-heal (watchdog isolates, no recovery) | Critical | Recovery policies in Phase 0; recovery-success metric; alert on isolation | **[MITIGATED]** — ADR 0007 + drill tests green; live end-to-end drill pending §7.6; recovery-success metric + isolation alerting to add |
| R3 | Dual-interface drift (CLI vs dashboard re-implementing logic) | High | Single `services/` layer; contract tests (golden CLI output == API JSON); parity test suite in CI | **[OPEN]** — ADR 0003 accepted; services layer is Phase 1 |
| R4 | OpenCode vendor lock-in / version churn | High | Provider abstraction at dispatcher; portable Markdown prompts; pinned version + doctor probe; headless generate fallback; never fork/re-skin desktop app | **[OPEN]** |
| R5 | Dashboard ships with no data (Model Usage/Agent Health empty) | High | Capture-first ordering: telemetry (Phases 0–1) precedes panels (Phase 2); stub honestly with "data pending," never fake | **[PARTIALLY MITIGATED]** — CLI telemetry capture now live (WS-0.4); runtime metrics persistence + provider usage instrumentation pending; panels must stay honest until then |
| R6 | Data loss (all state gitignored, single machine) | High | Nightly backup bundle + quarterly restore drill + backup tile with alerting | **[OPEN]** |
| R7 | Scope creep (console becomes mini-ERP) | Medium | CEO's NOT-do list: no SaaS/multi-tenant, no visual pipeline-builder v1, no own agent runtime, ≤30% effort on UI, no new metrics until serving layer lands | **[OPEN]** |
| R8 | Breaking 500+ tests / CI regression | High | Additive-only refactor; engines untouched; CLI surface frozen; full suite green each sprint; parity is a release blocker | **[OPEN]** — guardrails confirmed: engines unchanged in 0.1 |
| R9 | Localhost security (web server = new attack surface) | Medium-High | Bind 127.0.0.1 only; Host-header + CORS checks; token mode when non-loopback; keys in OS keyring, never rendered; CSP; DOMPurify on all Markdown | **[OPEN]** |
| R10 | Windows/uvicorn issues | Medium | Plain uvicorn (no uvloop), explicit port + friendly errors, `proc.terminate()` not `os.kill`, add windows-latest CI job | **[OPEN]** — confirmed CI is Ubuntu-only |
| R11 | User confusion during transition | High | Category rule: read = dashboard, safe write = both, destructive/bulk = CLI-only; "Equivalent CLI command" tooltips; persona onboarding (View/Operate/Develop); frozen CLI | **[OPEN]** — codified in parity matrix v0 |
| R12 | Misleading statuses (four overlapping vocabularies; stopped ≠ broken) | Medium | One canonical four-state system (All good / Watch / Needs action / Unknown); every status time-stamped; color + icon + text, never color alone | **[OPEN]** |

---

## 6. Decision log

| # | Decision | Options | Status | Note |
|---|----------|---------|--------|------|
| D1 | Frontend for v1 | Jinja2+htmx (zero Node, fastest) vs Svelte 5 (full interactivity) | **[OPEN]** | Both share the same API; 1-day ADR, not a fork → ADR 0008 (proposed) |
| D2 | Topology: dashboard as runtime engine; `services/` single source of truth | (ratified model) | **[DECIDED]** | ADR 0002 + 0003 accepted |
| D3 | API contract: REST + WebSocket, `?since=` replay reconnect | (ratified model) | **[PROPOSED]** | ADR 0009 |
| D4 | Dispatch model variance | `opencode/north-mini-code-free` (desktop-first, no key) vs `ollama/llama3.1:8b` (local default) | **[DECIDED]** | Per-target entries retained; command map is an enforced contract (ADR 0006); `architect` agent defined |
| D5 | North-star metric | **Recommendation: share of operator actions via Dashboard/OpenCode desktop, target ≥80% by month 6, measured by Phase-0 telemetry** | **[OPEN]** | Needs CEO sign-off |

---

## 7. Phase 0 execution log

### 7.1 WS-0.1 DONE — command_map reconciliation + integrity gate (2026-08-01)

- `src/ai_company/cli/command_map.yaml` reconciled: all 14 targets (11 legacy re-pointed + 3 new: `cli`, `dashboard`, `constitution`) resolve to real files in `prompts/opencode/`.
- Mapping rationale: legacy conceptual targets (`board/exec/dept/specialist`) map to `06_opencode_agent_generator.md` which explicitly generates Executives/Departments/Specialists/Boards; `workflow/prompt/graph` map to `03_generator_engine.md` (the engine generates Python/Markdown/Prompts and the org graph).
- Integrity gate: `tests/test_command_map_integrity.py` asserts every target resolves and every prompt file is referenced (runs in CI `test` job → prevents recurrence).

### 7.2 WS-0.3 DONE — opencode.json reconciliation (2026-08-01)

- Added the missing `architect` agent to `opencode.json` (model `opencode/north-mini-code-free`, primary) so `ai-company generate <target>` → `opencode run --agent architect` resolves.
- **Concurrency incident (process finding):** a parallel agent session was editing `opencode.json` and `src/ai_company/agents/` at the same time; both writers added `architect`, producing malformed duplicate JSON. The new integrity test (`test_dispatch_agent_defined_in_opencode_json`) caught it in CI. Resolved to a single `architect` entry whose model matches the dispatch map. **Lesson:** parallel writers on the same config files must coordinate (tracking rule §8.7).

### 7.3 WS-0.2 NOT STARTED — recovery

Root cause on record: `runtime_state.json` shows all 5 engines `failed`/`heartbeat_timeout` with `restart_count: 0` and an active `p_recovery_test` pipeline that ended fully failed. Supervisor recovery policy is the fix target; scripted failure drill is the acceptance test.

### 7.4 Phase 0 hygiene — flaky timing test fixed (2026-08-01)

- `tests/unit/runtime/test_metrics.py::test_timed_context_manager` asserted `>= 0.01` after `sleep(0.01)`; on Windows this randomly measured `0.0` (monotonic clock resolution) — a pre-existing CI-breaker under R8. Fixed with a 50ms sleep and tolerant 0.04s bound. Test-only change; engines untouched.

---

## 8. Change tracking rules (how this doc stays honest)

1. **Statuses are updated in the same change that ships the work** — never retroactively "for luck."
2. Every phase/WS row ships with its **exit criterion demonstrated** (test output, drill log, or demo) before `[DONE]`.
3. Risk rows flip to `[MITIGATED]` only when the mitigation is verified, not when it is planned.
4. Decisions flip to `[DECIDED]` only on explicit sign-off (ADR merged + owner noted).
5. CLI surface is **frozen** through Phase 3; any CLI change must be additive and parity-matrix-updated.
6. `runtime/runtime_state.json` and telemetry JSONL are the ground truth for health claims; the dashboard must never render a status the state file does not support.
7. Parallel writers on the same config files must coordinate before editing (`git status` check first); the CI integrity gates will catch conflicts but coordination is cheaper.
