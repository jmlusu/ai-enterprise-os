# Work Plan — Dashboard Initiative, Phase 2: Operational (Write) Dashboard

Status: **DONE — Waves 2a (2026-08-01) + 2b (2026-08-02) SHIPPED; exit criteria 1–6 all met (full generate → review → validate → approve loop from the browser)** · Owner: Chief Architect
Last updated: 2026-08-02
Related: `docs/dashboard/initiative.md` (§4 Phase 2), `docs/dashboard/parity-matrix-v0.md`,
ADR 0010 (Phase 2 write auth — Accepted), ADR 0009 (API contract v1), ADR 0003 (services layer),
`.ai/current-work.md` (Sprint 5.2)

---

## 1. Goal & exit criteria

> **Goal:** an operator runs a full **generate → review → validate → approve**
> loop from the browser, without opening a terminal — with every write behind
> a bearer token, CSRF protection, and a mandatory audit trail (ADR 0010).

**Exit criteria (all met — verified 2026-08-02):**

1. ✅ Every safe-write row in the parity matrix v0 has a live GUI path (confirm
   dialog; high-impact actions require a reason) and an equivalent API
   endpoint, all behind ADR 0010 auth (token + CSRF + `audit.write`) — parity
   matrix safe-write rows now **`1+2`**.
2. ✅ The Write History panel renders the full audit trail (`audit.write` /
   `audit.write_rejected`) with timestamps, action, result, reason, detail —
   no token/CSRF values ever rendered.
3. ✅ Non-loopback Hosts fail closed (401 without a valid token); loopback
   supports token-optional and `--require-loopback-token` strict mode.
4. ✅ Generate dispatcher (Wave 2b) streams to OpenCode with run history + live
   logs; the decision/approval inbox renders decision-engine cards (risk score,
   approval matrix, escalation).
5. ✅ Full test suite green (**1252** ≥ current 1171), new auth/write tests
   added, Windows CI green; ruff/mypy/format/lock/audit/command-map clean.
6. ✅ Trackers updated in the same change that ships the work (project rule):
   ADR 0010 status, parity matrix rows, initiative §4/risks R5–R6/finding #4,
   this workplan, `.ai/current-work.md`.

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

### Wave 2b (SHIPPED 2026-08-02)

- **Generate dispatcher:** `services/generate_runner.py` → OpenCode (streaming
  subprocess, exit code, files touched, live logs), run history persisted to
  `runtime/generate_runs.jsonl`; `ai-company generate <target>` parity row → **`1+2`**.
- **Decision/approval inbox:** decision engine (risk scoring, approval matrix,
  escalation) rendered as visual approval cards — the governance brain is now
  the GUI renderer (`/decisions`); inbox survives restarts via `import_decisions()`.
- **Remaining safe-write parity rows:** per-artifact company validators
  (`board-validate` … `doc-validate`), graph export, company CRUD write
  (files/departments/manifest), agent sync, backup, telemetry persist — all
  `1+2` behind the shared `api/guards.py` `WriteGuard`.
- **WS-channel token enforcement** for non-loopback deployments (`?token=`,
  close 1008) per ADR 0010 §1.
- **R5 telemetry (landed with Wave 2b):** runtime metrics persistence
  (`runtime/metrics_history.jsonl`, 30s ticker) + provider usage
  (`runtime/provider_usage.jsonl`, `UsageTrackingProvider`) → `/telemetry`
  KPI / Model Usage / Agent Health panels live.
- **Backup tile (R6):** pulse view backup action + status (`POST /api/backup`,
  `GET /api/backup/status`).

### Out of scope
- Destructive/bulk operations stay CLI-only (parity category rule, R11).
- SQLite derived read model (ADR 0004, Sprint 5.3).
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

## 4. Wave 2b — shipped (do not re-plan)

| Task | Status | Notes |
|---|---|---|
| `services/generate_runner.py` — OpenCode dispatch (streaming) + run history (`runtime/generate_runs.jsonl`) + live logs (`runtime/generate_logs/`) | ✅ | 9 unit tests (`test_generate_runner.py`, `_FakeProc`); boot replay `interrupted by restart` |
| Generate panel frontend (`/generate` — targets, prompt, live log tail, history) | ✅ | Parity `generate` rows → `1+2` |
| Decision/approval inbox (`/decisions` — risk cards, approve/reject/escalate/cancel) | ✅ | `DecisionHistory.import_decisions()` restart survival; record-once semantics |
| Per-artifact company validators via API (`validate_artifacts`) | ✅ | `board-validate` … `doc-validate` rows → `1+2` |
| Graph export write, company CRUD write, agent sync, backup, telemetry persist | ✅ | Remaining P2 surfaces → `1+2`; shared `WriteGuard` |
| WS `?token=` enforcement for non-loopback | ✅ | close 1008, ADR 0010 §1 |
| R5 telemetry: metrics + provider usage JSONL persistence + `/telemetry` live panels | ✅ | 10 tests; 30s ticker |
| Backup tile (R6): pulse backup action + status | ✅ | ADR 0001 |

---

## 5. Risks & decisions

- **R9 (localhost security):** **[MITIGATED]** with Wave 2a (ADR 0010). Keys
  never rendered; token printed only on first-time creation.
- **R5 (no data):** **[MITIGATED]** with Wave 2b — telemetry workstream landed;
  `/telemetry` KPI / Model Usage / Agent Health panels render real data.
- **R6 (data loss):** **[MITIGATED]** — backup tile shipped with Wave 2b.
- **R8 (CI regression):** additive-only; engines and CLI surface untouched
  (ADR 0005/0006); full suite green each wave (1142 → 1171 → **1252**).
- **Rotation semantics (ADR 0010 §1):** `create()` returns the plaintext only
  on first-time creation; rotation invalidates the previous value and never
  echoes it. Env-managed tokens (`AI_ENTERPRISE_WRITE_TOKEN`) refuse CLI
  revoke.
- **Fail-open audit:** publish failures append to `runtime/.audit.failed.jsonl`
  and never block localhost writes (must not change).
- **Decision D8:** ADR 0010 accepted 2026-08-01 (CISO / Cybersecurity
  Architecture / Software Engineering reviewed).
