# Parity Matrix v0 — CLI ↔ API ↔ Dashboard ↔ OpenCode desktop

Status: **v0 baseline (2026-08-01)** · Owner: Chief Architect
Purpose: **Scope contract.** Maps every CLI command and capability to its API
endpoint and GUI path. The Phase 4 demotion trigger requires **100%
parity-matrix coverage** with the parity test suite green.
Related ADRs: 0001 (command centers), 0005 (CLI retained as automation
contract), 0009 (API contract).

## Status legend

| Marker | Meaning |
|--------|---------|
| **SHIPPED** | Implemented and CI-tested |
| **PLANNED (P1)** | Accepted design, Phase 1 read-only work |
| **PLANNED (P2)** | Accepted design, Phase 2 write work |
| **CLI-ONLY** | Deliberately no GUI path (destructive/bulk guardrail, R11) |
| **DEFERRED** | Intentionally later |

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
| Bootstrap / scaffold | `ai-company bootstrap` | `POST /api/bootstrap` | Setup wizard | SHIPPED / PLANNED (P2) |
| Build artifacts | `ai-company build` | `POST /api/build` | Build panel | SHIPPED / PLANNED (P2) |
| Validate registry | `ai-company validate` | `GET /api/validate` | Health/validate view | SHIPPED / PLANNED (P1) |
| Generate via OpenCode | `ai-company generate <target>` | `POST /api/generate` | Generate panel (prompt + agent) | SHIPPED / PLANNED (P2) |
| List generate targets | `ai-company targets` | `GET /api/generate/targets` | Generate panel | SHIPPED / PLANNED (P1) |
| Doctor / diagnostics | `ai-company doctor` | `GET /api/diagnostics` | Diagnostics view | SHIPPED / PLANNED (P1) |
| System status | `ai-company status` | `GET /api/status` | Overview dashboard | SHIPPED / PLANNED (P1) |
| Serve dashboard API | `ai-company serve` | Serves all `/api/*` + `WS /api/ws` | Hosts the dashboard backend (loopback only) | SHIPPED |
| Company CRUD | `ai-company company ...` | `GET/PUT /api/company` | Company editor | SHIPPED / PLANNED (P1/P2) |
| Executive artifacts | `ai-company exec ...` | `GET /api/executives` | Executive view | SHIPPED / PLANNED (P1) |
| Registry browse | `ai-company registry list/show` | `GET /api/registry` | Registry explorer | SHIPPED / PLANNED (P1) |
| Memory browse | `ai-company memory show` | `GET /api/memory` | Memory view | SHIPPED / PLANNED (P1) |
| Graph export | `ai-company graph show/stats` | `GET /api/graph` | Org graph (Mermaid) | SHIPPED / PLANNED (P1) |
| Reports | `ai-company report generate summary` | `GET /api/reports` | Reports view | SHIPPED / PLANNED (P1) |
| Orchestration | `ai-company orchestrate ...` | `POST /api/orchestrate` | Pipelines view | SHIPPED / PLANNED (P2) |
| Runtime control | `ai-company runtime ...` | `POST /api/runtime/start/stop` | Runtime control | SHIPPED / PLANNED (P2) |
| Runtime live status | `ai-company runtime status` | `GET /api/runtime/status` | Runtime status widget | SHIPPED / PLANNED (P1) |
| Runtime health | `ai-company runtime health` | `GET /api/runtime/health` | Health widget | SHIPPED / PLANNED (P1) |
| Runtime metrics | `ai-company runtime metrics` | `GET /api/runtime/metrics` | Metrics charts | SHIPPED / PLANNED (P1) |
| Runtime events | `ai-company serve` (WS feed) | `WS /api/ws?since=` (replay-then-live) | Live event feed | SHIPPED (server) / PLANNED (P1) |
| Runtime recovery | `ai-company runtime recover` | `POST /api/runtime/recover` | Recovery view | SHIPPED / PLANNED (P2) |
| Agent sync | `python -m ai_company.agents sync` | `POST /api/agents/sync` | Agents view | SHIPPED / PLANNED (P2) |
| Backups | `python -m ai_company.backup` | `POST /api/backup` | Backups view | SHIPPED / PLANNED (P2) |
| CLI telemetry | `runtime/cli_telemetry.jsonl` | `GET /api/telemetry/cli` | Model/command usage | SHIPPED / PLANNED (P2) |
| Dashboards (sprint) | (static `dashboards/sprint_dashboard.html`) | `GET /api/dashboard/sprint` | Sprint dashboard | DEFERRED — replaced by the new dashboard (finding #3) |

---

## Part B — Command-exhaustive matrix

### Top-level

| CLI command | Category | GUI path | Phase |
|-------------|----------|----------|-------|
| `ai-company bootstrap` | Safe write | Run artifact: one-click bootstrap (confirm) | 2 |
| `ai-company build` | Safe write | Build panel (confirm) | 2 |
| `ai-company generate <target>` | Safe write | Dispatch panel → OpenCode, run history, live logs | 2 |
| `ai-company validate` | Safe write | Validation gate view + "Run validator" | 1 read / 2 write |
| `ai-company doctor` | Read | System Health → diagnostics | 1 |
| `ai-company targets` | Read | Dispatch panel target list | 1 |
| `ai-company status` | Read | Overview ("pulse" page) | 1 |
| `ai-company serve` | Read (hosts API + WS bridge) | Serves the dashboard backend (loopback only) | 1 |

### `ai-company company` group

| CLI command | Category | GUI path | Phase |
|-------------|----------|----------|-------|
| `company generate` | Safe write | Dispatch panel (company) + run history | 2 |
| `company validate` | Safe write | Validation gate + run action | 1 read / 2 write |
| `company report` | Read | Reports view (Markdown/Mermaid in-page) | 1 |
| `company board-generate` | Safe write | Dispatch panel (board) | 2 |
| `company board-validate` | Safe write | Validation gate | 1/2 |
| `company board-report` | Read | Reports view | 1 |
| `company exec-generate` | Safe write | Dispatch panel (exec) | 2 |
| `company exec-validate` | Safe write | Validation gate | 1/2 |
| `company dept-generate` | Safe write | Dispatch panel (dept) | 2 |
| `company dept-validate` | Safe write | Validation gate | 1/2 |
| `company specialist-generate` | Safe write | Dispatch panel (specialist) | 2 |
| `company specialist-validate` | Safe write | Validation gate | 1/2 |
| `company workflow-generate` | Safe write | Dispatch panel (workflow) | 2 |
| `company workflow-validate` | Safe write | Validation gate | 1/2 |
| `company prompt-generate` | Safe write | Dispatch panel (prompt) | 2 |
| `company prompt-validate` | Safe write | Validation gate | 1/2 |
| `company docs-generate` | Safe write | Dispatch panel (docs) | 2 |
| `company doc-validate` | Safe write | Validation gate | 1/2 |

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
| `memory save` | Safe write | Memory editor (confirm) | 2 |
| `memory update` | Safe write | Memory editor (confirm) | 2 |
| `memory snapshot` | Safe write | Memory snapshot button (confirm) | 2 |
| `memory restore` | Safe write | Restore from snapshot (confirm) | 2 |
| `memory archive` | Safe write | Archive action (confirm) | 2 |
| `memory unarchive` | Safe write | Unarchive action (confirm) | 2 |
| `memory export` | Safe write | Export action (confirm) | 2 |
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
| `graph export` | Safe write | Export button (confirm) | 2 |

### `ai-company report` group

| CLI command | Category | GUI path | Phase |
|-------------|----------|----------|-------|
| `report generate <type>` | Safe write | Reports view + generate action | 1 read / 2 write |

### `ai-company orchestrate` group

| CLI command | Category | GUI path | Phase |
|-------------|----------|----------|-------|
| `orchestrate plan` | Safe write | Run planning (confirm) | 2 |
| `orchestrate start` | Safe write | Run start (confirm) | 2 |
| `orchestrate status` | Read | Runs & History | 1 |
| `orchestrate history` | Read | Runs & History | 1 |
| `orchestrate resume` | Safe write | Resume pipeline (confirm) | 2 |
| `orchestrate retry` | Safe write | Retry pipeline (confirm) | 2 |
| `orchestrate rollback` | Safe write | Rollback pipeline (confirm, escalation review) | 2 |

### `ai-company runtime` group

| CLI command | Category | GUI path | Phase |
|-------------|----------|----------|-------|
| `runtime status` | Read | System Health | 1 |
| `runtime health` | Read | System Health | 1 |
| `runtime metrics` | Read | System Health / telemetry panels | 1 |
| `runtime diagnostics` | Read | System Health diagnostics | 1 |
| `runtime start` | Safe write | Start runtime (confirm) | 2 |
| `runtime stop` | Safe write | Stop runtime (confirm) | 2 |
| `runtime restart` | Safe write | Restart runtime (confirm) | 2 |
| `runtime reload` | Safe write | Reload config (confirm) | 2 |

---

## Coverage summary (v0 baseline)

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

**Guarantees:**
- Every read and every safe write has a GUI path (no "no GUI path" escalations possible → feeds Phase 4 trigger).
- Every destructive/bulk operation stays CLI-only by design (guardrail, not gap).
- The CLI column is the automation contract (ADR 0005) and must never regress.
- Phase 4 demotion trigger additionally requires the **parity test suite** (golden CLI output == API JSON per command) green in CI.

## Update rule

This matrix is the **scope contract**. Any new CLI command or capability must
add its row here in the same change; any row that changes category requires
CTO + CIO sign-off. API + Dashboard columns are Phase 1 work on the FastAPI
backend (ADR 0002) and shared services layer (ADR 0003).
