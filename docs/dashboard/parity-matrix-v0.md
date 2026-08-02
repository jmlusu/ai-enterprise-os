# Parity Matrix v0 — CLI ↔ API ↔ Dashboard ↔ OpenCode desktop

Status: **v0 baseline (2026-08-01) — Phase 1 complete (all read rows SHIPPED); Phase 2 complete (Waves 2a + 2b SHIPPED 2026-08-02 — all safe-write rows `1+2`)** · Owner: Chief Architect
Purpose: **Scope contract.** Maps every CLI command and capability to its API
endpoint and GUI path. The Phase 4 demotion trigger requires **100%
parity-matrix coverage** with the parity test suite green.
Related ADRs: 0001 (command centers), 0005 (CLI retained as automation
contract), 0009 (API contract), 0010 (Phase 2 write auth — ratified 2026-08-01).

## Status legend

| Marker | Meaning |
|--------|---------|
| **SHIPPED** | Implemented and CI-tested |
| **PLANNED (P1)** | Accepted design, Phase 1 read-only work |
| **PLANNED (P2)** | Accepted design, Phase 2 write work |
| **CLI-ONLY** | Deliberately no GUI path (destructive/bulk guardrail, R11) |
| **DEFERRED** | Intentionally later |
| **`1`** | Read path SHIPPED (Phase 1) |
| **`2`** | Write path not yet implemented (Phase 2) |
| **`1/2`** | Read SHIPPED, write still Phase 2 |
| **`1+2`** | **Both read and write SHIPPED** (Phase 2: Wave 2a subset + Wave 2b close-out, ADR 0010) |
| **`2b`** | Historical marker — write deferred to Phase 2 Wave 2b (all such rows shipped `1+2` on 2026-08-02) |

## Category rule (Risk R11)

| Category | Rule |
|----------|------|
| **Read** | Dashboard-first; CLI remains equivalent |
| **Safe write** | Both surfaces, with confirm dialog on dashboard |
| **Destructive / bulk** | **CLI-only** (deliberate guardrail; no GUI button) |

"Equivalent CLI command" tooltips are shown on every dashboard action.

---

## Part A — Capability overview (API endpoints, per ADR 0001/0005)

| Capability | CLI command | API endpoint (planned) | Dashboard view (planned) | Status |
|---|---|---|---|---|
| Bootstrap / scaffold | `ai-company bootstrap` | `POST /api/bootstrap` | Setup wizard | **SHIPPED** (Wave 2a, ADR 0010) |
| Build artifacts | `ai-company build` | `POST /api/build` | Build panel | **SHIPPED** (Wave 2a, ADR 0010) |
| Validate registry | `ai-company validate` | `GET/POST /api/validate` | Health/validate view | **SHIPPED** (read Phase 1 + write Wave 2a) |
| Generate via OpenCode | `ai-company generate <target>` | `GET/POST /api/generate` + `/api/generate/runs\|start\|cancel\|log` | Generate panel (prompt + agent, live logs, history) | **SHIPPED** (`1+2`, Wave 2b) |
| List generate targets | `ai-company targets` | `GET /api/generate/targets` | Generate panel | **SHIPPED** (Phase 1) |
| Doctor / diagnostics | `ai-company doctor` | `GET /api/diagnostics` | Diagnostics view | **SHIPPED** (Phase 1) |
| System status | `ai-company status` | `GET /api/status` | Overview dashboard | **SHIPPED** (Phase 1 — Pulse view) |
| Serve dashboard API | `ai-company serve` | Serves all `/api/*` + `WS /api/ws` | Hosts the dashboard backend (loopback only) | SHIPPED (Phase 2 flags: `--hash-at-rest`, `--require-loopback-token`) |
| Company CRUD | `ai-company company ...` | `GET/PUT /api/company` + `/api/company/departments` | Company editor | **SHIPPED** (`1+2`, Wave 2b write) |
| Executive artifacts | `ai-company exec ...` | `GET /api/executives` | Executive view | **SHIPPED** (Phase 1 — Agents view) |
| Registry browse | `ai-company registry list/show` | `GET /api/registry` | Registry explorer | **SHIPPED** (Phase 1 — Registry view) |
| Memory browse | `ai-company memory show` | `GET /api/memory` | Memory view | **SHIPPED** (Phase 1 — Memory view) |
| Graph export | `ai-company graph show/stats` | `GET /api/graph` + `POST /api/graph/export` | Org graph (Mermaid) | **SHIPPED** (`1+2`, Wave 2b export write) |
| Reports | `ai-company report generate summary` | `GET /api/reports` + `POST /api/reports/generate` | Reports view | **SHIPPED** (read Phase 1 + generate write Wave 2a) |
| Orchestration | `ai-company orchestrate ...` | `POST /api/orchestrate/*` | Pipelines view | **SHIPPED** (read Phase 1 + write Wave 2a) |
| Runtime control | `ai-company runtime ...` | `POST /api/runtime/*` | Runtime control | **SHIPPED** (start/stop/restart/reload Wave 2a) |
| Runtime live status | `ai-company runtime status` | `GET /api/runtime/status` | Runtime status widget | **SHIPPED** (Phase 1 — System Health view) |
| Runtime health | `ai-company runtime health` | `GET /api/runtime/health` | Health widget | **SHIPPED** (Phase 1 — System Health view) |
| Runtime metrics | `ai-company runtime metrics` | `GET /api/runtime/metrics` | Metrics charts | **SHIPPED** (Phase 1 — System Health view) |
| Runtime events | `ai-company serve` (WS feed) | `WS /api/ws?since=` (replay-then-live) | Live event feed | **SHIPPED** (Phase 1 — Pulse live feed, auto-reconnect + replay) |
| Runtime recovery | `ai-company runtime recover` | `POST /api/runtime/recover` | Recovery view | **SHIPPED** (recover/unisolate Wave 2a, high-impact + reason) |
| Agent sync | `python -m ai_company.agents sync` | `POST /api/agents/sync` | Agents view | **SHIPPED** (`1+2`, Wave 2b) |
| Backups | `python -m ai_company.backup` | `GET/POST /api/backup` + `/api/backup/status` | Backups view + pulse tile | **SHIPPED** (`1+2`, Wave 2b) |
| CLI telemetry | `runtime/cli_telemetry.jsonl` | `GET /api/telemetry/*` | Model/command usage | **SHIPPED** (`1+2`, Wave 2b telemetry panels) |
| Dashboards (sprint) | (static `dashboards/sprint_dashboard.html`) | `GET /api/dashboard/sprint` | Sprint dashboard | DEFERRED — replaced by the new dashboard (finding #3) |

---

## Part B — Command-exhaustive matrix

> **Phase column meaning (updated 2026-08-02, Phase 2 Wave 2b close-out):**
> `1` = read path **SHIPPED** (API endpoint + dashboard view live and CI-tested);
> `2` = Phase 2 write work; `1/2` = read half shipped, write half Phase 2;
> `1+2` = **both read and write SHIPPED** (Wave 2a subset + Wave 2b close-out,
> ADR 0010 — write actions behind bearer token + CSRF, audited as
> `audit.write`); `2b` = historical marker for rows shipped with Wave 2b
> (OpenCode generate dispatch, approval inbox, telemetry, backup). Write actions
> added GUI buttons in Wave 2a with confirm dialogs (high-impact ones require a
> reason). **All safe-write rows are `1+2` as of 2026-08-02.**

### Top-level

| CLI command | Category | GUI path | Phase |
|-------------|----------|----------|-------|
| `ai-company bootstrap` | Safe write | Run artifact: one-click bootstrap (confirm) | **1+2** |
| `ai-company build` | Safe write | Build panel (confirm) | **1+2** |
| `ai-company generate <target>` | Safe write | Dispatch panel → OpenCode, run history, live logs | **1+2** |
| `ai-company validate` | Safe write | Validation gate view + "Run validator" | **1+2** |
| `ai-company doctor` | Read | System Health → diagnostics | 1 |
| `ai-company targets` | Read | Dispatch panel target list | 1 |
| `ai-company status` | Read | Overview ("pulse" page) | 1 |
| `ai-company serve` | Read (hosts API + WS bridge) | Serves the dashboard backend (loopback only) | 1 |

### `ai-company company` group

| CLI command | Category | GUI path | Phase |
|-------------|----------|----------|-------|
| `company generate` | Safe write | Dispatch panel (company) + run history | **1+2** |
| `company validate` | Safe write | Validation gate + run action | **1+2** |
| `company report` | Read | Reports view (Markdown/Mermaid in-page) | 1 |
| `company board-generate` | Safe write | Dispatch panel (board) | **1+2** |
| `company board-validate` | Safe write | Validation gate | **1+2** |
| `company board-report` | Read | Reports view | 1 |
| `company exec-generate` | Safe write | Dispatch panel (exec) | **1+2** |
| `company exec-validate` | Safe write | Validation gate | **1+2** |
| `company dept-generate` | Safe write | Dispatch panel (dept) | **1+2** |
| `company dept-validate` | Safe write | Validation gate | **1+2** |
| `company specialist-generate` | Safe write | Dispatch panel (specialist) | **1+2** |
| `company specialist-validate` | Safe write | Validation gate | **1+2** |
| `company workflow-generate` | Safe write | Dispatch panel (workflow) | **1+2** |
| `company workflow-validate` | Safe write | Validation gate | **1+2** |
| `company prompt-generate` | Safe write | Dispatch panel (prompt) | **1+2** |
| `company prompt-validate` | Safe write | Validation gate | **1+2** |
| `company docs-generate` | Safe write | Dispatch panel (docs) | **1+2** |
| `company doc-validate` | Safe write | Validation gate | **1+2** |

### `ai-company exec` group

| CLI command | Category | GUI path | Phase |
|-------------|----------|----------|-------|
| `exec list` | Read | Agents roster | 1 |
| `exec show <name>` | Read | Agent detail card | 1 |
| `exec org-chart` | Read | Registry/Org graph view | 1 |
| `exec agent <name>` | Read | Agent detail + open in OpenCode deep link | 1/3 |

### `ai-company registry` group

| CLI command | Category | GUI path | Phase |
|-------------|----------|----------|-------|
| `registry list` | Read | Registry view (tables) | 1 |
| `registry show <name>` | Read | Entity detail | 1 |
| `registry verify` | Read | Validation gate (read-only run) | 1 |

### `ai-company memory` group

| CLI command | Category | GUI path | Phase |
|-------------|----------|----------|-------|
| `memory list` | Read | Memory view | 1 |
| `memory get <key>` | Read | Memory detail | 1 |
| `memory search <q>` | Read | Memory search | 1 |
| `memory show` | Read | Memory stats/status | 1 |
| `memory stats` | Read | Memory stats | 1 |
| `memory snapshots` | Read | Memory snapshots list | 1 |
| `memory save` | Safe write | Memory editor (confirm) | **1+2** |
| `memory update` | Safe write | Memory editor (confirm) | **1+2** |
| `memory snapshot` | Safe write | Memory snapshot button (confirm) | **1+2** |
| `memory restore` | Safe write | Restore from snapshot (confirm) | **1+2** |
| `memory archive` | Safe write | Archive action (confirm) | **1+2** |
| `memory unarchive` | Safe write | Unarchive action (confirm) | **1+2** |
| `memory export` | Safe write | Export action (confirm) | **1+2** |
| `memory delete` | **Destructive** | **CLI-only** | — |
| `memory purge` | **Destructive** | **CLI-only** | — |
| `memory clear` | **Destructive** | **CLI-only** | — |
| `memory archive-old` | **Bulk** | **CLI-only** | — |
| `memory apply-retention` | **Bulk** | **CLI-only** | — |

### `ai-company graph` group

| CLI command | Category | GUI path | Phase |
|-------------|----------|----------|-------|
| `graph show` | Read | Registry/Org graph (Mermaid in-page) | 1 |
| `graph stats` | Read | Org graph stats | 1 |
| `graph export` | Safe write | Export button (confirm) | **1+2** |

### `ai-company report` group

| CLI command | Category | GUI path | Phase |
|-------------|----------|----------|-------|
| `report generate <type>` | Safe write | Reports view + generate action | **1+2** |

### `ai-company orchestrate` group

| CLI command | Category | GUI path | Phase |
|-------------|----------|----------|-------|
| `orchestrate plan` | Safe write | Run planning (confirm) | **1+2** |
| `orchestrate start` | Safe write | Run start (confirm) | **1+2** |
| `orchestrate status` | Read | Runs & History | 1 |
| `orchestrate history` | Read | Runs & History | 1 |
| `orchestrate resume` | Safe write | Resume pipeline (confirm) | **1+2** |
| `orchestrate retry` | Safe write | Retry pipeline (confirm) | **1+2** |
| `orchestrate rollback` | Safe write | Rollback pipeline (confirm, escalation review) | **1+2** |

### `ai-company runtime` group

| CLI command | Category | GUI path | Phase |
|-------------|----------|----------|-------|
| `runtime status` | Read | System Health (canonical overall chip, R12) | **1** (parity-tested: `tests/golden/test_parity_status.py`) |
| `runtime health` | Read | System Health | 1 |
| `runtime metrics` | Read | System Health / telemetry panels | 1 |
| `runtime diagnostics` | Read | System Health diagnostics | 1 |
| `runtime start` | Safe write | Start runtime (confirm) | **1+2** |
| `runtime stop` | Safe write | Stop runtime (confirm) | **1+2** |
| `runtime restart` | Safe write | Restart runtime (confirm) | **1+2** |
| `runtime reload` | Safe write | Reload config (confirm) | **1+2** |

---

## Coverage summary (v0 baseline, updated at Phase 1 close-out 2026-08-01)

| Group | Total | GUI/BOTH | CLI-only (destructive/bulk) |
|-------|-------|----------|------------------------------|
| Top-level | 8 | 8 | 0 |
| company | 18 | 18 | 0 |
| exec | 4 | 4 | 0 |
| registry | 3 | 3 | 0 |
| memory | 19 | 14 | 5 (`delete`, `purge`, `clear`, `archive-old`, `apply-retention`) |
| graph | 3 | 3 | 0 |
| report | 1 | 1 | 0 |
| orchestrate | 7 | 7 | 0 |
| runtime | 8 | 8 | 0 |
| **Total** | **71** | **66 (93%)** | **5 (7%)** |

**Phase 1 status:** **all 31 read rows SHIPPED** — API endpoint + dashboard
view live (`ai-company serve`), verified by `tests/unit/api/test_api_domain.py`
(31 tests) and the parity suite seed `tests/golden/test_parity_read.py`
(9 tests, golden CLI output == API JSON).

**R12 status row (2026-08-02):** `runtime status` ↔ `GET /api/status` +
`GET /api/health` now share the canonical four-state status service
(`services/status_service.py`) — locked by `tests/golden/test_parity_status.py`
(2 tests: running + stopped parity, CLI boots its own runtime against a
hermetic API-side runtime).

**Phase 2 status (Waves 2a + 2b, ADR 0010 ratified 2026-08-01, close-out
2026-08-02):** **all safe-write rows are `1+2`** — both surfaces live, behind
bearer token + CSRF + `audit.write` (shared `api/guards.py` `WriteGuard`;
high-impact actions require a reason). Wave 2a shipped the runtime/orchestrate/
memory/validate/reports/build/bootstrap writes; **Wave 2b** closed the rest:
`generate` + all `*-generate` dispatch rows (streaming `generate_runner`),
the decision/approval inbox, per-artifact company validators
(`board-validate` … `doc-validate`), graph export, company CRUD write, agent
sync, backup, and telemetry persist. Parity suite grew with
`tests/golden/test_parity_wave2b.py` (per-artifact validate reports == CLI
`validate` lines, generate + backup OpenAPI contract, shared guard parity
401/403 on both wave 2a and wave 2b endpoints). Suite grew 1142 → **1252
tests**.

**Guarantees:**
- Every read and every safe write has a GUI path (no "no GUI path" escalations possible → feeds Phase 4 trigger).
- Every destructive/bulk operation stays CLI-only by design (guardrail, not gap).
- The CLI column is the automation contract (ADR 0005) and must never regress.
- Phase 4 demotion trigger additionally requires the **parity test suite** (golden CLI output == API JSON per command) green in CI — seeded in Phase 1, coverage grows with each phase.

## Update rule

This matrix is the **scope contract**. Any new CLI command or capability must
add its row here in the same change; any row that changes category requires
CTO + CIO sign-off. API + Dashboard columns are Phase 1 work on the FastAPI
backend (ADR 0002) and shared services layer (ADR 0003).
