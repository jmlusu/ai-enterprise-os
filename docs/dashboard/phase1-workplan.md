# Work Plan — Dashboard Initiative, Phase 1: Read-only Dashboard v1

Status: **DONE** (2026-08-01) — all 8 views live, parity P1 rows SHIPPED, CI green · Owner: Chief Architect
Last updated: 2026-08-01
Related: `docs/dashboard/initiative.md` (§4 Phase 1), `docs/dashboard/parity-matrix-v0.md`,
ADR 0002 (FastAPI backend), ADR 0003 (services layer), ADR 0008 (Jinja2+htmx v1),
ADR 0009 (read-only API contract v1), `.ai/current-work.md` (Sprint 5.2 — Phase 2 Waves 2a+2b shipped 2026-08-02, superseding this phase)

---

## 1. Goal & exit criteria

> **Goal:** An exec can self-serve the "pulse" page; an operator answers
> "is the system healthy?" in <5s — from a browser, without a terminal.

**Exit criteria (all must hold before `[DONE]`):**

1. `ai-company serve` renders the dashboard frontend (Jinja2 + htmx) at
   `http://127.0.0.1:8000/`, not raw JSON.
2. Overview ("pulse"), System Health, Agents (roster), Runs & History, Memory,
   Reports, Validation gate, Registry/Org graph — all 8 views render live data
   from the read-only API.
3. Every status is honest and time-stamped, using the four-state vocabulary
   (All good / Watch / Needs action / Unknown) — **never a green lie**
   (ADR 0009, risk R12).
4. Every data gap renders an explicit **"data pending"** state, never fake
   numbers (risk R5).
5. Live refresh ≤5s via the WS bridge with auto-reconnect (`?since=` replay).
6. Parity: all read commands in the parity matrix v0 have a working GUI path
   (the "PLANNED (P1)" rows become SHIPPED).
7. Full test suite green (≥ current 1070), new frontend/API tests added,
   Windows CI green.
8. `.ai/` knowledge base + initiative tracker + parity matrix updated in the
   same change that ships the work (project rule).

---

## 2. Scope

### In scope
- Read-only views + live events; no mutating actions (those are Phase 2).
- Read expansion of the shared services layer (ADR 0003) + FastAPI read
  endpoints to cover every parity P1 row.
- Jinja2 + htmx frontend (ADR 0008 v1), zero Node toolchain.
- Markdown + Mermaid rendering in-page (marked + DOMPurify + mermaid.js) for
  Reports/Org graph.
- CSP revision scoped to the dashboard surface (still no `'unsafe-inline'` scripts).
- Parity test suite seed: golden CLI output == API JSON for read commands.

### Out of scope (Phase 2+)
- Write endpoints, bearer token, CSRF, audit (ADR 0010).
- SQLite derived read model (ADR 0004, Sprint 5.4).
- Runtime metrics persistence + provider usage instrumentation (telemetry
  workstream — Phase 2). Panels relying on it stay "data pending".
- Svelte 5 (Phase 4, ADR 0008 v2).
- CLI changes: **CLI surface is frozen** (ADR 0005/0006); any CLI change must
  be additive and parity-matrix-updated.

---

## 3. Current state (wave 1 — done, do not re-plan)

Already shipped (`6d2654b`, `b6d5a26`, CI green):

| Piece | Status |
|---|---|
| FastAPI app `api/app.py` — REST + WebSocket | ✅ |
| `RuntimeFacade` (`services/runtime_facade.py`) — status/health/metrics/engines | ✅ |
| `DashboardEventBridge` (`services/dashboard_events.py`) — bus → asyncio queue | ✅ |
| Read-only contract v1: `GET /`, `/api/health`, `/api/status`, `/api/metrics`, `/api/engines`, `/api/events` | ✅ |
| WS `/api/ws?since=<iso>` — replay + live push | ✅ |
| Loopback-only Host allowlist + security headers (`_SecurityMiddleware`) | ✅ |
| `run_in_threadpool` bridge — runtime locks never on the event loop | ✅ |
| Integration tests (`tests/unit/api/test_api.py`) | ✅ |

**Phase 1 close-out:** the wave-2 commit (WS-1.0 → WS-6.0, see below) flips
this plan to DONE. All 8 views render live read-only data under a scoped CSP
(`script-src 'self'`, no `unsafe-inline`), the parity test suite seed
(`tests/golden/test_parity_read.py`, 9 tests) is green, and the full suite is
1142 tests passing.

---

## 4. Workstreams & tasks

Legend: `⬜` = not started · `🔄` = in progress · `✅` = done

### WS-1.0 — Services layer read expansion (ADR 0003) ✅
Extend `RuntimeFacade` with read-only methods over existing engines
(thin adapters — no business logic lives here):

| Task | Status | Acceptance |
|---|---|---|
| `registry_list()`, `registry_show(name)`, `registry_verify()` | ✅ | JSON mirror of `ai-company registry list/show/verify` |
| `executives_list()`, `executive_show(name)`, `org_chart()` | ✅ | JSON mirror of `exec list/show/org-chart` |
| `memory_list/get/search/show/stats/snapshots()` | ✅ | JSON mirror of `memory ...` reads |
| `graph_show()`, `graph_stats()` | ✅ | JSON mirror of `graph show/stats` |
| `reports_list()`, `report_generate_read(type)` (read-only render) | ✅ | JSON mirror of `report generate` read path |
| `validate_read()` — read-only validation run | ✅ | JSON mirror of `ai-company validate` |
| `diagnostics()` | ✅ | JSON mirror of `ai-company doctor` |
| `orchestration_status()`, `orchestration_history()` | ✅ | JSON mirror of `orchestrate status/history` |
| `generate_targets()` | ✅ | JSON mirror of `ai-company targets` |
| Facade unit tests for each new method | ✅ | `tests/unit/services/test_runtime_facade_read.py` (33 tests) |

### WS-2.0 — Read-only API expansion (ADR 0009, parity P1) ✅
Thin FastAPI routers over the facade (same patterns as wave 1, loopback-safe):

| Task | Status | Acceptance |
|---|---|---|
| `GET /api/registry`, `/api/registry/{name}`, `/api/registry/verify` | ✅ | parity row SHIPPED |
| `GET /api/executives`, `/api/executives/{name}`, `/api/org-chart` | ✅ | parity row SHIPPED |
| `GET /api/memory`, `/api/memory/{key}`, `/api/memory/search`, `/api/memory/stats`, `/api/memory/snapshots` | ✅ | parity row SHIPPED |
| `GET /api/graph`, `/api/graph/stats` | ✅ | parity row SHIPPED |
| `GET /api/reports`, `GET /api/reports/{type}` | ✅ | parity row SHIPPED |
| `GET /api/validate` | ✅ | parity row SHIPPED |
| `GET /api/diagnostics` | ✅ | parity row SHIPPED |
| `GET /api/orchestrate/status`, `/api/orchestrate/history` | ✅ | parity row SHIPPED |
| `GET /api/generate/targets` | ✅ | parity row SHIPPED |
| API integration tests per endpoint | ✅ | `tests/unit/api/test_api_domain.py` (26 tests + 5 frontend/CSP) |

### WS-3.0 — Frontend shell (ADR 0008 v1) ✅
| Task | Status | Acceptance |
|---|---|---|
| `templates/dashboard/base.html` — CSP-compatible layout (no inline scripts/styles; nonce-less: external htmx + css only) | ✅ | passes CSP policy; no `unsafe-inline` |
| Static mount: `src/ai_company/api/static/` (css, htmx.min.js, marked, DOMPurify, mermaid) served via `StaticFiles` | ✅ | assets load under CSP (5 vendored assets + `vendor/README.md` provenance manifest) |
| Scoped CSP revision: `default-src 'self'` + `script-src 'self'` + `style-src 'self'` + `connect-src 'self' ws:` + `img-src 'self' data:`; keep `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'none'` | ✅ | security headers updated in `_SecurityMiddleware`; tests assert no `unsafe-inline` |
| `TemplateResponse` wiring: routes render base template; JSON API unchanged (content-negotiation not needed — separate paths) | ✅ | `/` renders HTML; `/api/*` returns JSON |
| Nav/IA: 11 sections from `07_dashboard_generator.md` grouped into the 8 views | ✅ | visible nav, works offline from static files |
| Parity test suite seed: golden CLI output == API JSON (read commands) | ✅ | `tests/golden/test_parity_read.py` (9 tests) green; pytest runs them in the standard suite |

### WS-4.0 — Views (server-rendered partials) ✅
Views map (parity P1 → GUI path; `07` = IA section from `07_dashboard_generator.md`):

| View | Data source (endpoint) | IA sections | Status |
|---|---|---|---|
| **Overview ("pulse")** | `/api/status`, `/api/health`, `/api/metrics`, `/api/engines` | 07: Repository Health, Sprint, Release Status | ✅ |
| **System Health** | `/api/health`, `/api/engines`, `/api/metrics`, `/api/diagnostics` | 07: Testing (health), Architecture | ✅ |
| **Agents (roster)** | `/api/executives`, `/api/org-chart` | 07: Agent Health (roster; health telemetry = data pending) | ✅ |
| **Runs & History** | `/api/orchestrate/status`, `/api/orchestrate/history` | 07: Release Status | ✅ |
| **Memory (read)** | `/api/memory*` | — | ✅ |
| **Reports** | `/api/reports*` | 07: Documentation, Risks, Technical Debt, KPIs (KPI = data pending) | ✅ |
| **Validation gate** | `/api/validate` | 07: Testing | ✅ |
| **Registry/Org graph** | `/api/registry*`, `/api/graph*` | 07: Architecture (Mermaid) | ✅ |

Each view: htmx partial (`templates/dashboard/partials/*.html`), honest
states, "Equivalent CLI command" tooltip (parity matrix R11 rule).

### WS-5.0 — Live refresh + events panel ✅
| Task | Status | Acceptance |
|---|---|---|
| Events stream panel (custom WS client in `static/js/app.js` — htmx ws ext + `?since=` replay + dedupe by `event_id`) | ✅ | live events render; old events replay via `?since=` |
| Auto-reconnect on WS close (retry with backoff, replay `?since=<lastEventTs>`) | ✅ | disconnect → reconnect → no missed events (dedupe by `event_id`) |
| 1–5s snapshot ticker (poll `/api/health` + `/api/metrics`) | ✅ | ≤5s staleness |
| Honest staleness UI: timestamp + "stale/stopped/unknown" badges (class switch at 3x/6x poll interval) | ✅ | R12 vocabulary |

### WS-6.0 — Hardening & close-out ✅
| Task | Status | Acceptance |
|---|---|---|
| Security review pass: Host allowlist, CSP, no secrets in HTML, DOMPurify on all rendered Markdown/Mermaid | ✅ | R9 mitigations verified (all pages scoped CSP; API stays `default-src 'none'`; app.js sanitizes every innerHTML write) |
| Frontend tests (static analysis + API-driven; no JS test runner in v1) | ✅ | 5 new tests in `test_api_domain.py` (pages render, assets served, scoped CSP); CI green |
| `.ai/` KB, initiative.md (Phase 1 → DONE), parity matrix (P1 rows → SHIPPED), `.ai/current-work.md` updated | ✅ | docs honest |
| Live smoke: `ai-company serve` + browser walkthrough of all 8 views | ✅ | exit criteria 1–5 demoed (all 11 routes 200, real data present) |

---

## 5. Sequencing & milestones

| Milestone | Contents | Exit check |
|---|---|---|
| **M1 — Read API complete** | WS-1.0 + WS-2.0 (facade + endpoints + tests) | ✅ parity P1 rows API-complete; all read tests green |
| **M2 — Frontend shell** | WS-3.0 (base, static, CSP, TemplateResponse, nav) | ✅ `/` renders HTML under scoped CSP; JSON API untouched |
| **M3 — Views complete** | WS-4.0 (all 8 views) | ✅ each view renders real data; gaps show "data pending" |
| **M4 — Live + events** | WS-5.0 (WS panel, reconnect, ticker, staleness) | ✅ ≤5s refresh, honest states |
| **M5 — Phase 1 DONE** | WS-6.0 (hardening, docs, demo) | ✅ exit criteria 1–8 — live smoke passed, 1142 tests green, parity seed green |

**Ordering note:** M1 is strictly first (views need data). M3 and M4 can
overlap; M5 gates `[DONE]`. Each milestone ends with a green commit per the
project rule (update `.ai/current-work.md` in the same change).

---

## 6. Risks & mitigations (from initiative §5)

| Risk | Mitigation in this plan |
|---|---|
| **R5 — Dashboard ships with no data** | "Data pending" states mandated for Agent Health telemetry, Model Usage, KPIs (upstream lands in Phase 2); Overview/Health/Runs/Memory/Registry/Reports all have real API data today |
| **R9 — Localhost security** | Scoped CSP (no `unsafe-inline`), DOMPurify on Markdown/Mermaid, Host allowlist retained, no secrets in HTML; security review pass in WS-6.0 |
| **R3 — Dual-interface drift** | Golden parity test seed (CLI output == API JSON); facade is the single shared surface |
| **R8 — Breaking 500+ tests / CI** | Additive-only: engines untouched, CLI frozen, API additions only; full suite + Windows CI gate each milestone |
| **R11 — User confusion** | "Equivalent CLI command" tooltips on every view; category rule (read = dashboard-first) documented |
| **R12 — Misleading statuses** | Four-state vocabulary + timestamp + color/icon/text enforced in every partial |

---

## 7. Open decisions resolved during Phase 1

| # | Decision | Proposer | Resolution |
|---|---|---|---|
| OD1 | Dashboard port binding — make configurable via `config/runtime/*.yaml` (currently hardcoded `127.0.0.1:8000`) | current-work.md | **Deferred to Phase 2** — loopback-only port is a security posture, not a bug; revisit with auth work (ADR 0010) |
| OD2 | htmx WS extension vs. minimal custom JS for reconnect | Chief Architect | **Custom JS** (`static/js/app.js`) — owns `?since=` replay + dedupe by `event_id` + staleness class switches; htmx `ws.js` vendored for future `hx-ext` use |
| OD3 | `marked`/`mermaid` version pinning (vendored vs CDN — CSP `'self'` requires vendoring) | Cybersecurity | **Vendored locally** (pinned versions + `static/vendor/README.md` provenance manifest); CDN rejected — CSP is `script-src 'self'` |
| OD4 | Golden parity suite runner: pytest marker vs. separate CI job | SWE | **Plain pytest tests** in `tests/golden/` — no new CI job, no marker; the full suite already runs them on both Linux and Windows |

---

## 8. Definition of done (Phase 1)

- All 8 views render live read-only data with honest states, ≤5s refresh.
- Parity matrix P1 rows flipped to SHIPPED; parity test suite seeded and green.
- CSP scoped without `unsafe-inline`; DOMPurify applied; loopback-only.
- Test suite green on Windows CI; no CLI or engine changes.
- Initiative tracker, `.ai/` KB, parity matrix updated; work plan status → DONE.
