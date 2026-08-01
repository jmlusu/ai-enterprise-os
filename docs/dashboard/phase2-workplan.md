# Work Plan — Dashboard Initiative, Phase 2: Operational (Write) Dashboard

Status: **IN PROGRESS — Wave 2a (write auth + operational writes) SHIPPED 2026-08-01; Wave 2b (generate dispatcher + approval inbox) next** · Owner: Chief Architect
Last updated: 2026-08-01
Related: `docs/dashboard/initiative.md` (§4 Phase 2), `docs/dashboard/parity-matrix-v0.md`,
ADR 0010 (Phase 2 write auth — Accepted), ADR 0009 (API contract v1), ADR 0003 (services layer),
`.ai/current-work.md` (Sprint 5.2)

---

## 1. Goal & exit criteria

> **Goal:** an operator runs a full **generate → review → validate → approve**
> loop from the browser, without opening a terminal — with every write behind
> a bearer token, CSRF protection, and a mandatory audit trail (ADR 0010).

**Exit criteria (all must hold before `[DONE]`):**

1. Every safe-write row in the parity matrix v0 has a live GUI path (confirm
   dialog; high-impact actions require a reason) and an equivalent API
   endpoint, all behind ADR 0010 auth (token + CSRF + `audit.write`).
2. The Write History panel renders the full audit trail (`audit.write` /
   `audit.write_rejected`) with timestamps, action, result, reason, detail —
   no token/CSRF values ever rendered.
3. Non-loopback Hosts fail closed (401 without a valid token); loopback
   supports token-optional and `--require-loopback-token` strict mode.
4. Generate dispatcher (Wave 2b) streams to OpenCode with run history + live
   logs; the decision/approval inbox renders decision-engine cards
   (risk score, approval matrix, escalation).
5. Full test suite green (≥ current 1171), new auth/write tests added,
   Windows CI green; ruff/mypy/format/lock/audit clean.
6. Trackers updated in the same change that ships the work (project rule):
   ADR 0010 status, parity matrix rows, initiative §4/risk R9, workplan,
   `.ai/current-work.md`.

---

## 2. Scope

### Wave 2a (SHIPPED 2026-08-01)

- **Security scheme (ADR 0010):** bearer token (`runtime/.write_token`,
  env override `AI_ENTERPRISE_WRITE_TOKEN`, optional SHA-256 hash-at-rest),
  per-run CSRF synchronizer token (`GET /api/write-csrf` +
  `X-CSRF-Token`), mandatory write audit (`audit.write` /
  `audit.write_rejected`, fail-open JSONL).
- **Write guard:** non-loopback → token mandatory (fail-closed); loopback →
  token optional / `--require-loopback-token`; invalid token → 401; CSRF
  mismatch → 403; rejected payloads never include submitted token/CSRF.
- **Mutation endpoints (20 POSTs):** runtime start/stop/restart/reload/
  recover/unisolate; orchestrate plan/start/resume/retry/rollback; memory
  save/update/snapshot/restore/export/archive/unarchive; validate; reports
  generate; build; bootstrap. High-impact actions require `reason` (422).
- **Frontend:** operator buttons + native confirm dialogs (reason prompts),
  Write History page with token input and audit table, CSP-safe JS.
- **CLI (additive, ADR 0006):** `ai-company dashboard token
  create|revoke|list|info`; `serve --hash-at-rest --require-loopback-token`.
- **Tests:** `test_auth.py` (18) + `test_write_endpoints.py` (11); suite
  1142 → 1171.

### Wave 2b (NEXT)

- **Generate dispatcher:** `POST /api/generate` → OpenCode (streaming
  subprocess, exit code, files touched), run history + live logs view;
  `ai-company generate <target>` parity row → `1+2`.
- **Decision/approval inbox:** decision engine (risk scoring, approval matrix,
  escalation) rendered as visual approval cards — the governance brain becomes
  the GUI renderer.
- **Remaining safe-write parity rows:** per-artifact company validators
  (`board-validate` … `doc-validate`), graph export, company CRUD write
  (`PUT /api/company`), agent sync, backup, CLI-telemetry write surfaces.
- **WS-channel token enforcement** for non-loopback deployments
  (`?token=` per ADR 0010 §1).

### Out of scope
- Destructive/bulk operations stay CLI-only (parity category rule, R11).
- SQLite derived read model (ADR 0004, Sprint 5.4).
- Telemetry workstream (R5): runtime metrics persistence + provider usage
  instrumentation.
- Svelte 5 (Phase 4, ADR 0008 v2).

---

## 3. Wave 2a — shipped (do not re-plan)

| Piece | Status |
|---|---|
| `api/auth.py` — `WriteTokenService` / `CsrfService` / `host_allowed()` / fail-open audit publisher | ✅ |
| `api/write_endpoints.py` — 20 mutation POSTs + `GET /api/write-csrf` + `GET /api/audit/writes` | ✅ |
| `events/models.py` — `EventType.AUDIT_WRITE` / `AUDIT_WRITE_REJECTED` | ✅ |
| `services/runtime_facade.py` — write adapters (runtime/orchestrate/memory/validate/reports/build/bootstrap) | ✅ |
| `api/app.py` — wiring: tokens/CSRF params, guard registration, `/api` index (read_only: False), `GET /writes` | ✅ |
| CLI `dashboard token create\|revoke\|list\|info` + `serve` flags | ✅ |
| Frontend — write actions, confirm dialogs, Write History page, token input | ✅ |
| Tests — `test_auth.py` (18), `test_write_endpoints.py` (11); suite 1142 → **1171** | ✅ |
| Docs — ADR 0010 Accepted, parity matrix `1+2`/`2b`, initiative §4/R9/D8/§7.8, this workplan, `.ai/current-work.md` | ✅ |

---

## 4. Wave 2b — plan

| Task | Status | Notes |
|---|---|---|
| `POST /api/generate` — OpenCode dispatch (streaming) + run history + live logs | ⬜ | `opencode_runner` refactor (initiative §3); Q2 scope |
| Generate panel frontend (targets, prompt input, live log stream) | ⬜ | Parity `generate` rows → `1+2` |
| Decision/approval inbox — risk cards, approval matrix, escalation | ⬜ | Renderer over existing decision engine |
| Per-artifact company validators via API | ⬜ | `board-validate` … `doc-validate` rows |
| Graph export write, company CRUD write, agent sync, backup, telemetry write | ⬜ | Remaining P2 surfaces |
| WS `?token=` enforcement for non-loopback | ⬜ | ADR 0010 §1 |

---

## 5. Risks & decisions

- **R9 (localhost security):** **[MITIGATED]** with Wave 2a (ADR 0010). Keys
  never rendered; token printed only on first-time creation.
- **R8 (CI regression):** additive-only; engines and CLI surface untouched
  (ADR 0005/0006); full suite green each wave.
- **Rotation semantics (ADR 0010 §1):** `create()` returns the plaintext only
  on first-time creation; rotation invalidates the previous value and never
  echoes it. Env-managed tokens (`AI_ENTERPRISE_WRITE_TOKEN`) refuse CLI
  revoke.
- **Fail-open audit:** publish failures append to `runtime/.audit.failed.jsonl`
  and never block localhost writes (must not change).
- **Decision D8:** ADR 0010 accepted 2026-08-01 (CISO / Cybersecurity
  Architecture / Software Engineering reviewed).
