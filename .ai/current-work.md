# Current Work State

> **Purpose:** Single source of truth for what's in progress, what's next, and
> what's blocked. Updated at the end of each work session and after each
> significant commit. Agents should read this file first to understand current
> context.

## Sprint Status

| Field | Value |
|---|---|
| **Current Sprint** | Sprint 5.4 â€” Telemetry: durable, bounded, actionable (SQLite store, retention/rollup, isolation alerting, recovery metric) — **COMPLETE 2026-08-03** |
| **Status** | ✅ **COMPLETE** â€” T1 + T2 + T3 + T4 + T5 all SHIPPED; suite **1364 green**; all CI runs 8/8 (T5 post-fix: runs `30799819043` + `30800484976`) |
| **Goal** | Complete the R5/R2 telemetry story before Phase 3: (T1) SQLite **live** telemetry store (incremental sync, read path = ADR 0004 projection), (T2) retention + rollup policies (config-driven, rollup-then-truncate, scheduler job), (T3) isolation alerting (`runtime.engine_isolated` â†’ alerts â†’ dashboard), (T4) recovery-success metric (counters + KPI rate), (T5, stretch) CI segfault root-cause. Zero CLI-surface changes (ADR 0006); R3 parity rows for new reads |
| **Commit** | Sprint 5.4: T1 `294e107` Â· T2 `11fde80` Â· T3 `f690133` Â· T4 `9dba281` Â· T5 `b93a886` Â· tracker hashes `f3c4989`/`314498a`/`345500c` Â· Sprint 5.3: `de9c851` Â· Wave 2b: `2244497` Â· Wave 2a: `131d9d9` |
| **Created** | 2026-08-02 |
| **Completed** | 2026-08-03 (T5 close-out; CI runs `30799819043` + `30800484976` both 8/8 first-try) |
| **Follow-up (in progress)** | Post-Sprint 5.3 risk mitigation completed: R12/R8/R3/R11/R4 â€” see "Dashboard Initiative Follow-up" below |

### Sprint 5.4 Backlog (committed plan â€” 2026-08-02)

**Goal:** telemetry is durable (SQLite live store), bounded (retention/rollup), and actionable (isolation alerting + recovery-success metric) â€” closing the R5/R2 backlog before Phase 3.

| # | Item | Pts | Acceptance summary |
|---|---|---|---|
| **T1** | SQLite **live** telemetry store â€” **SHIPPED** | 8 | `ReadModelStore.sync_from_jsonl()` â€” incremental, watermark-based, idempotent (no dupes on re-sync); synced on the 30s telemetry ticker (single writer via `facade.metrics_persist` â†’ `sync_read_model`); facade `metrics_history_summary` / `provider_usage_summary` read the store with **fail-open to JSONL**; JSONL stays append-only source of truth (ADR 0004). AC met: appends during a live session appear without restart; re-sync idempotent; store-down â†’ JSONL fallback. Suite 1308 â†’ **1320 green** |
| **T2** | Retention + rollup â€” **SHIPPED** | 8 | `telemetry/retention.py` + `config/runtime/telemetry.yaml` (metrics 7d / provider_usage 90d / cli_telemetry 180d defaults); **rollup-then-truncate** hourly/daily aggregates (idempotent: buckets already in the rollup file skipped); `telemetry_retention` recurring scheduler job (3600s, pattern: `memory_consolidation`); `RuntimeFacade.retention_status` + `GET /api/telemetry/retention` (read-only report) + telemetry caption; every path fail-open. AC met: dry-run + apply; rollup math correct; raw never truncated before rollup; corrupt timestamps never truncated. Suite 1344 â†’ **1364 green** |
| **T3** | Isolation alerting (R2 backlog) â€” **SHIPPED** | 3 | Unified `runtime.engine_isolated` event (engine, reason, attempts, ts) from supervisor `isolate()` (the single watchdog/health/recovery funnel; `runtime.engine_unisolated` on re-admission); fail-open `runtime/alerts.jsonl` + `telemetry/alerts.py` + `GET /api/alerts` + pulse/System Health red chip + telemetry KPI line; alert **resolved** on un-isolate (no spam â€” latest record per component wins). AC met: alert visible within one health cycle; persists across restart. Suite 1327 â†’ **1344 green** |
| **T4** | Recovery-success metric (R2 backlog) | 3 | Metrics counters `recovery_attempts` / `recovery_successes` / `recovery_failures` + gauge `recovery_success_rate`; `RecoveryManager` outcome recording (recovered â†’ success; escalated/isolated â†’ failure; **once per outcome**); `/telemetry` KPI line "Self-healing: N% success". AC: counters increment exactly once per outcome; rate persists in snapshot |
| **T5** | CI segfault flake (STRETCH) — **SHIPPED** | 5 | Root-cause: shutdown order stopped engines before workers, so supervisor/health-monitor threads probed closed SQLite connections (segfault on teardown). Fix: `shutdown.py` reorders steps — **stop_workers** (heartbeat_sender, scheduler, watchdog, supervisor) **before** stop_engines. Defense: `ReadModelEngine.health()` catches `sqlite3.Error` on closed connection. AC met: full suite 1364 green locally; CI run reran successfully; 10+ consecutive green runs validated locally. |

**Sequencing:** T1 (foundation) â†’ T4 â€– T3 (small, independent) â†’ T2 (needs T1) â†’ T5 (last, risk-isolated).

**Definition of Done:** suite 1308 â†’ ~1360 green; parity rows + golden tests for new read surfaces (alerts, rollup reads); ruff/mypy/format/command-map/CLI-surface/uv-audit clean; trackers updated with each commit.

### Sprint 5.4 T1 Deliverables â€” SQLite live telemetry store (DONE)

- [x] **`ReadModelStore.sync_from_jsonl()`** â€” watermark-based incremental import: per-source byte offsets stored in `meta` (`sync_offset_events/metrics/provider_usage`); only bytes appended since the last sync are parsed and inserted; events deduped by `event_id` (`INSERT OR IGNORE`); rows + watermarks commit in **one transaction** (crash-safe, no duplicates); missing/truncated/never-synced sources â†’ full stream re-import (projection always mirrors source). `rebuild()` seeds the watermarks so startup rebuild â†’ live incremental sync.
- [x] **`ReadModelEngine.sync()`** â€” engine-level passthrough for the ticker/CLI; `stats()` now reports `last_sync_at`.
- [x] **Facade repoint (fail-open)** â€” `RuntimeFacade.metrics_history_summary` / `provider_usage_summary` prefer the `read_model` engine's store (`persistence_enabled` preserved in the envelope); fall back to JSONL when the engine is absent or the store read fails. New `sync_read_model()`; `metrics_persist()` now persists **and** syncs (the 30s serve ticker drives both â€” single writer).
- [x] **Tests** â€” `tests/unit/readmodel/test_readmodel.py` (+7): sync appends, idempotency, full-import-when-never-rebuilt, truncation mirror, event dedup, missing sources no-op, engine sync. `tests/unit/services/test_facade_wave2b.py` (+5): store-preferring reads, sync catch-up without restart, `metrics_persist` syncs the store, JSONL fallback preserved. Suite 1308 â†’ **1320 green**; ruff/mypy/format/command-map/CLI-surface clean.

### Sprint 5.4 T4 Deliverables â€” Recovery-success metric (DONE, CI green)

- [x] **Counters + gauge in `MetricsRegistry`** â€” `recovery_attempts` / `recovery_successes` / `recovery_failures` counters + `recovery_success_rate` gauge (names as shared constants `RECOVERY_*` in `runtime/metrics.py`); first-class `RuntimeMetrics` fields (`runtime/models.py`) so the rate survives the flattened model-dump persist path.
- [x] **`RecoveryManager` outcome recording** â€” optional `metrics` init param; `recover()` records **exactly once per outcome**: `recovery_attempts += 1` every call; success only when a concrete action (`restart`/`reload_state`) was taken; escalated/isolated/exhausted/all-failed â†’ failure; `recovery_success_rate` gauge derived from counters (0 when no attempts). No registry â†’ zero overhead (no-op, legacy behavior unchanged). Engine wires `metrics=self.metrics_registry` into `RecoveryManager`.
- [x] **Shared tolerant `metrics_trend()`** â€” `runtime/metrics.py` helper that reads **both** persisted snapshot shapes: registry-shaped (`{gauges, counters}`) and the flattened `RuntimeMetrics` model dump the facade `metrics_persist` path actually writes (latent T1 shape bug: gauges were lost â†’ CPU/engine KPI showed `â€”`/0 through the real persist path; now both render). Used by `telemetry/metrics.py` `metrics_summary` **and** `readmodel/store.py` `metrics_summary` (parity).
- [x] **KPI card** â€” `api/templates/views/telemetry.html` grid `cols-4` â†’ `cols-5`, new **Self-healing** card: `N% success` + recovered/failed/attempts subtitle.
- [x] **Tests (+7 â†’ suite 1320 â†’ 1327)** â€” recovery: attempts once-per-call, success via restart factory, rate derivation, isolate counts as failure, no-registry noop; runtime metrics: to_metrics recovery mapping + zero defaults; telemetry: recovery fields in summary trend + flattened-dump shape regression. Facade persist/summary test now asserts recovery fields flow through the persisted snapshot. ruff/mypy/format/command-map/CLI-surface clean; full suite green.

### Sprint 5.4 T5 Deliverables â€” CI segfault flake (DONE, CI green)

- [x] **Root cause identified** — shutdown sequence stopped engines **before** workers. The `read_model` engine closed its SQLite connection in `stop()`, but the supervisor/health-monitor/heartbeat_sender threads continued running and probed the closed connection during teardown, triggering a native `Segmentation fault` (exit 139) on Ubuntu CI (~15% rate, after `test_runtime_boot.py` ~15% mark).
- [x] **Fix: shutdown order** — `shutdown.py` reorders steps: **`stop_workers` now runs before `stop_engines`** (notify → stop_workers → stop_engines → stop_processes → save_state → finalize). This ensures background threads are joined before any engine closes its resources.
- [x] **Defense in depth** — `ReadModelEngine.health()` wraps `store.stats()` in `try/except sqlite3.Error` and returns {"status": "unhealthy", "error": "store unavailable: ..."} instead of crashing. Graceful degradation if shutdown races persist.
- [x] **Tests updated** — `tests/unit/runtime/test_shutdown.py` step-order assertion updated to reflect new sequence (stop_workers before stop_engines). All existing shutdown tests pass.
- [x] **Validation** — full suite **1364 green** locally; **CI run `48` (head `314498a`) all 8 jobs green first try** — the ubuntu `test` job that previously segfaulted (~15%) passed with no rerun; >10 consecutive local runs pass without segfault.

### Sprint 5.4 T2 Deliverables â€” Retention + rollup (DONE, CI pending)

- [x] **`telemetry/retention.py`** â€” per-source retention policies, hourly/daily rollup aggregates, and truncation. `load_policies(config_section)` merges `config/runtime/telemetry.yaml` over `DEFAULT_POLICIES` (metrics_history 7d, provider_usage 90d, cli_telemetry 180d; granularities `hourly`/`daily`); `apply_retention(dry_run=True default, now)` per source: **rollup-then-truncate** â€” expired records are folded into hourly + daily rollup rows appended to `runtime/rollup_<source>.jsonl` *before* the raw JSONL is truncated (temp + rename atomic rewrite); idempotent (buckets already in the rollup file are skipped); `rollup: false` on a policy truncates without rollup; corrupt/unparseable timestamps are never truncated; every helper fail-open (missing/broken paths are skipped, never raise). Aggregators: metrics = last-sample-wins gauges + integer sum for `engine_healthy`; provider_usage = sum `usage` token counts, average `latency_seconds`; cli_telemetry = count + sum `duration_seconds`.
- [x] **Config + scheduler job** â€” `config/runtime/telemetry.yaml` (retention + rollup settings) registered as the 9th `_CONFIG_SECTIONS` entry in `runtime/configuration.py` (`DEFAULT_TELEMETRY_CONFIG`, `load_telemetry_config`); `config/runtime/scheduler.yaml` adds the **`telemetry_retention`** recurring job (3600s) and `engine.py` registers `_job_telemetry_retention` (reads `self._section("telemetry")`, calls `apply_retention(dry_run=False)`, fail-open logging).
- [x] **Read surface** â€” `RuntimeFacade.retention_status()` (read-only dry-run report: applied=False, per-source raw/expired/keep counts, days, rollup flag, rollup record counts) + `GET /api/telemetry/retention` (`operational_endpoints.py`); `telemetry.html` KPI caption line shows the retention policy summary.
- [x] **Tests (+20 â†’ suite 1344 â†’ 1364)** â€” `tests/unit/telemetry/test_retention.py` (17: policy loading incl. config-file merge, bucket keys, dry-run counts, metrics/provider/cli rollup math, idempotency, rollup-disabled truncates-without-rollup, rollup-failure-keeps-raw via monkeypatched broken path, fail-open missing files, corrupt timestamps never truncated, `read_rollups`/`rollup_summary` filters incl. `limit=0`); `test_engine.py` (+1 `test_job_telemetry_retention_runs_fail_open`); `test_wave2b_endpoints.py` (+1 `test_telemetry_retention_read`); `test_facade_wave2b.py` (+1 `test_retention_status`). Existing integration asserts updated for the 6th scheduler job (`test_runtime_boot.py`: pending queue 5â†’6, jobs 6, config_sections 9; `test_runtime_restart.py`: jobs 6). ruff/mypy/format/command-map/CLI-surface clean; full suite green.

### Sprint 5.4 T3 Deliverables â€” Isolation alerting (DONE, CI green)

- [x] **`telemetry/alerts.py`** â€” fail-open alert log at `runtime/alerts.jsonl`: `record_alert_open(component, reason, attempts, source)` / `record_alert_resolved(component, reason)`; `read_alerts(limit)` (corrupt lines skipped); `alerts_summary(limit)` derives the current open-alert set â€” **latest record per component wins**, so repeated isolates collapse to one open alert until a `resolved` record supersedes it (no-spam contract). All helpers never raise.
- [x] **Supervisor funnel wired** â€” `Supervisor.isolate()` now publishes `runtime.engine_isolated` (component, reason, attempts, source) on the event bus **and** records an open alert; `unisolate()` publishes `runtime.engine_unisolated` and resolves the open alert. `_recover()` passes `result.attempts` through (recovery-failed / isolated-during-recovery isolates carry the attempt count). Watchdog/heartbeat/health failures all route through this single funnel.
- [x] **`RUNTIME_EVENT_MAP` extended** â€” `runtime.engine_isolated` â†’ `SYSTEM_ERROR`, `runtime.engine_unisolated` â†’ `SYSTEM_HEALTH_CHECK` (`runtime/models.py`); contract test now asserts the full 14-type set.
- [x] **API + facade** â€” `RuntimeFacade.alerts_summary()` (fail-open envelope) + `GET /api/alerts` (`operational_endpoints.py`, `limit` 1â€“1000, default 200).
- [x] **Dashboard surfaces** â€” `pulse.html` Health card gains the **open-alerts chip** (`action` red when >0, `ok` when 0); `health.html` adds the **Isolation alerts** card (open-alert table: component/opened/reason/attempts) + summary header chip; `telemetry.html` KPI caption line reports open-alert count. Zero CLI-surface changes (ADR 0006); alerts is an R5 read surface with no parity row (same precedent as metrics history).
- [x] **Tests (+17 â†’ suite 1327 â†’ 1344)** â€” `tests/unit/telemetry/test_alerts.py` (10: roundtrip, no-spam collapse, resolution clears, reopen, multi-component, corrupt-line skip, tail limit, fail-open missing/broken path); `test_supervisor.py` (+5: open/resolved recording via tmp-file fixture, failed-recovery alert with attempts, isolated/unisolated bus events via capturing fake bus); `test_wave2b_endpoints.py` (+1 `test_alerts_read`); `test_facade_wave2b.py` (+1 facade alerts summary); `test_models.py` contract set +2. ruff/mypy/format/command-map/CLI-surface clean; full suite green.

### Dashboard Initiative Follow-up (post-Sprint 5.3, in progress)

- [x] **D5 north-star metric signed off** â€” CEO approved 2026-08-02: share of operator actions via Dashboard/OpenCode desktop â‰¥ **80% by month 6**; baseline = CLI telemetry (`runtime/cli_telemetry.jsonl`); GUI/desktop telemetry in Phase 3 (honest numerator); Phase 4 trigger depends on it
- [x] **R4 fallback strategy decided (D9)** â€” CEO approved 2026-08-02: **free/local models** (e.g. `ollama/llama3.1:8b`, D4) are the official fallback
- [x] **R4 end-to-end fallback shipped â†’ R4 `[MITIGATED]`** â€” shared `services/generate_dispatch.py` (`dispatch_generate`: opencode primary â†’ `ollama` fallback on missing / startup failure / non-zero exit); wired into the streaming runner (honest `provider`/`model` in `runtime/generate_runs.jsonl` + append-mode logs) and the frozen CLI `generate` command (surface unchanged, R8 gate still green); tunable via `config/runtime/model_fallback.yaml`; cancellation preserved (`register_proc`); proven by runner e2e tests with stub binaries + dispatch unit tests + CLI wiring tests â€” suite 1289 â†’ **1308 green**
- [x] **R12 canonical status service** â€” `services/status_service.py` (four-state `ok`/`watch`/`action`/`unknown` + timestamp, phase state machine; stopped â†’ watch, never action); CLI `runtime status` Overall line, `GET /api/status` + `/api/health` canonical, dashboard views + app.js unified; golden parity `tests/golden/test_parity_status.py`; **also fixed root cause of misleading unhealthy flags â€” `HeartbeatSender` liveness worker (passive engines were isolated after boot) + read-model `check_same_thread=False`**; R12 â†’ `[MITIGATED]` in initiative.md â€” **committed `147540b` (heartbeat fix) + `75e0595` (status service), pushed 2026-08-02, CI green**
- [x] **R8 CI gate â€” CLI additive-only rule** â€” `integrity/check_cli_surface.py` (typer/click introspection vs committed `cli_surface_contract.json`; removal/rename/change = hard error exit 1; additive drift = exit 2, accept with `--update`); wired into both lint jobs in ci.yml next to the command-map gate; 8 unit tests (`tests/unit/integrity/test_check_cli_surface.py`); verified: real removal â†’ exit 1
- [x] **R3 parity coverage milestone** â€” explicit target in `docs/dashboard/initiative.md` Â§5 R3 + parity-matrix-v0.md: **â‰¥40 of 71 command rows parity-tested by Phase 3 close-out**; every new command adds its parity test in the same change
- [x] **R11 persona onboarding scope â€” D10 SIGNED OFF** (CEO 2026-08-02) in initiative.md Â§6: three personas View/Operate/Develop, one skippable first-run tour each + persistent "Equivalent CLI command" tooltips; no tutorial system; destructive/bulk stays CLI-only, surfaced in Develop persona. **R11 â†’ `[MITIGATED]`**; delivery lands with Phase 2/3 features

### Sprint 5.3 Deliverables

- [x] **`readmodel/` package (ADR 0004)** â€” `ReadModelStore` (SQLite WAL, schema v1) + `ReadModelEngine` (rebuild-on-construct = the **startup** trigger); tables `events`, `metrics_history`, `provider_usage`, `meta`; reads: `recent_events`, `event_counts_by_type`, `metrics_snapshots`, `metrics_summary`, `provider_usage_by_model`
- [x] **Startup wiring** â€” `config/runtime/startup.yaml` step `initialize_read_model` (engine `read_model`, `db_path: "@state_dir"` â†’ `runtime/dashboard.db`) before `start_runtime`; boot sequence is now **11 steps / 6 engines**
- [x] **Agent sync `--scope` default `both`** â€” `agents/sync.py` (`AgentSyncConfig.scope`), `agents/__main__.py` (`--scope`), `api/operational_endpoints.py` (`AgentsSyncBody.scope`), `services/runtime_facade.py` (`agents_sync(scope="both")`); new users get project + global dirs
- [x] **Dashboard port decision documented** â€” `cli/main.py` `serve()` keeps default `127.0.0.1:8000` hardcoded (loopback-only), overridable via `--host/--port`; non-loopback requires ADR 0010 auth
- [x] **Windows CI** â€” `ci.yml` lint + type-check jobs now use a `os: [ubuntu-latest, windows-latest]` matrix (`fail-fast: false`); tests already ran on both
- [x] Tests: `tests/unit/readmodel/test_readmodel.py` (13 new), boot test updated (11 steps / 6 engines incl. `read_model`), agents-sync default + CLI global-dir writes; suite 1252 â†’ **1265 green**; ruff/mypy/format clean
- [x] Pre-existing fixes while green-checking: metrics JSONL writer now guarantees strictly increasing timestamps (Windows coarse clock); parity test asserts Typer 0.27 `target` rendering; ruff SIM117/RUF100 cleanups in wave 2b tests

### Sprint 5.2 Wave 2b Deliverables â€” All Done

- [x] `services/generate_runner.py` â€” thread-safe streaming OpenCode dispatcher (`start/cancel/get/list_runs/log_tail`), child stdout streamed to `runtime/generate_logs/<run_id>.log`, runs persisted to `runtime/generate_runs.jsonl`, boot replay marks queued/running as `interrupted by restart`, shell=False, fail-open
- [x] `api/guards.py` â€” shared `WriteGuard` (`guard()/require_reason()/audited()/reject()`) + `HIGH_IMPACT_ACTIONS`; `write_endpoints.py` migrated to it (ADR 0010 semantics unchanged)
- [x] Decision/approval inbox â€” `decisions_list/get/create/approve/reject/escalate/cancel` facade adapters; inbox survives restarts via `DecisionHistory.import_decisions()`; `engine.reject()` added; `create_decision`/`make_decision` record-once (no facade double-record)
- [x] Per-artifact company validators via API (`validate_artifacts` wraps per-artifact `ValidationReport` in `ValidatorResult`)
- [x] Remaining P2 write surfaces: graph export write, company CRUD write (files/departments/manifest), agent sync (`AgentSyncEngine(config=...)`), backup create/status, telemetry persist
- [x] Frontend: `/generate` (dispatch + live logs + history), `/decisions` (approval inbox), `/telemetry` (KPI / Model Usage / Agent Health live panels), pulse backup tile; CSP-safe `data-write`/`data-action` wire helpers
- [x] R5 telemetry workstream: `telemetry/metrics.py` + `telemetry/provider.py` (JSONL persistence, aggregated summaries) + `providers/usage.py` `UsageTrackingProvider` + `ProviderFactory(..., track_usage=False)`; 30s persistence ticker in app lifespan
- [x] WS `?token=` enforcement for non-loopback (close 1008, ADR 0010 Â§1)
- [x] Tests: telemetry (10), generate runner (9), facade wave 2b (24), API wave 2b (24 incl. page renders + guard/audit parity), golden parity wave 2b; suite 1171 â†’ **1252 green**; ruff/mypy/format/command-map clean

### Sprint 5.2 Wave 2a Deliverables â€” All Done

- [x] ADR 0010 ratified (Proposed â†’ Accepted, decision D8) â€” opaque 256-bit bearer token, per-run CSRF, mandatory `audit.write` / `audit.write_rejected` (fail-open JSONL)
- [x] `api/auth.py` â€” `WriteTokenService` (create/rotate/revoke/verify, hash-at-rest, env override `AI_ENTERPRISE_WRITE_TOKEN`), `CsrfService`, `host_allowed()`, fail-open audit publisher
- [x] `api/write_endpoints.py` â€” 20 mutation POSTs + `GET /api/write-csrf` + `GET /api/audit/writes`; guard = Host policy â†’ token (401) â†’ CSRF (403) â†’ `audit.write_rejected`; high-impact actions (stop/restart/recover/unisolate/rollback) require `reason` (422)
- [x] `services/runtime_facade.py` write adapters (runtime/orchestrate/memory/validate/reports/build/bootstrap); engines untouched (ADR 0005/0006)
- [x] Frontend: operator buttons + native confirm dialogs (reason prompts), Write History page (`/writes`) with token input + audit table, CSP-safe JS (textContent only)
- [x] CLI additive (ADR 0006): `ai-company dashboard token create|revoke|list|info` (value printed only on first-time creation; rotation never echoes); `serve --hash-at-rest --require-loopback-token`
- [x] Tests: `test_auth.py` (18) + `test_write_endpoints.py` (11); suite 1142 â†’ **1171 green**; ruff/mypy/format/lock/audit/build clean
- [x] Docs: parity-matrix P2 rows â†’ `1+2` (generate rows â†’ `2b`), initiative Phase 2 `[IN PROGRESS]` / R9 `[MITIGATED]` / D8 `[DECIDED]` / Â§7.8, `docs/dashboard/phase2-workplan.md`, `.ai/` knowledge base

---

## Completed â€” Phase 2 Wave 2a: Write Auth + Operational Writes (COMMITTED)

**Commit:** `131d9d9` â€” **done and live.** Do NOT re-plan this. Work plan: `docs/dashboard/phase2-workplan.md` (Wave 2a).

| Deliverable | Status |
|---|---|
| `api/auth.py` â€” `WriteTokenService` / `CsrfService` / `host_allowed()` / fail-open audit publisher | âœ… |
| `api/write_endpoints.py` â€” 20 mutation POSTs + `GET /api/write-csrf` + `GET /api/audit/writes` | âœ… |
| `events/models.py` â€” `EventType.AUDIT_WRITE` / `AUDIT_WRITE_REJECTED` | âœ… |
| Write guard: non-loopback Host â†’ token mandatory (fail-closed); loopback â†’ optional / `--require-loopback-token`; invalid token 401; CSRF mismatch 403; rejected payloads never leak token/CSRF | âœ… |
| High-impact `reason` requirement (`HIGH_IMPACT_ACTIONS`): runtime stop/restart/recover/unisolate, orchestrate rollback | âœ… |
| CLI `dashboard token create\|revoke\|list\|info` + `serve --hash-at-rest` / `--require-loopback-token` (additive, ADR 0006) | âœ… |
| Frontend: write actions + confirm dialogs, Write History page, token input, CSP-safe | âœ… |
| Tests 1142 â†’ **1171** (18 auth + 11 write-endpoint tests); ruff/mypy/format/lock/audit/build clean | âœ… |
| Docs: ADR 0010 Accepted, parity matrix `1+2`/`2b`, initiative Â§4/R9/D8/Â§7.8, phase2-workplan.md | âœ… |

---

## Completed â€” Phase 1 (COMMITTED)

**Wave 1 API:** `6d2654b`, `b6d5a26` Â· **Wave 2 frontend:** `d0b1385` â€” **Phase 1 is DONE.** Do NOT re-plan this. Work plan: `docs/dashboard/phase1-workplan.md`.

| Deliverable | Status |
|---|---|
| FastAPI app (`api/app.py`) â€” REST + WebSocket, loopback-only, security headers | âœ… |
| `RuntimeFacade` (`services/runtime_facade.py`) â€” shared surface (ADR 0003), 16 read methods | âœ… |
| 19 read-only API endpoints (ADR 0009) + WS `/api/ws?since=` replay | âœ… |
| Jinja2 + htmx frontend (ADR 0008 v1): `base.html` + 8 views | âœ… |
| Vendored assets `static/vendor/` + provenance README | âœ… |
| Scoped page CSP (`script-src 'self'`, no `unsafe-inline`) | âœ… |
| Parity test suite seed `tests/golden/test_parity_read.py` (9 tests) | âœ… |
| Suite 1070 â†’ **1142 tests green**; no CLI or engine changes | âœ… |

---

## Next Sprint Candidates (Prioritized)

### 1. Sprint 5.5 â€” Phase 3: OpenCode desktop as first-class command center ðŸ–¥ï¸
Initiative Phase 3 `[NOT STARTED]` — **kickoff draft (2026-08-03):**

**Goal:** make the OpenCode desktop session a first-class operator surface — every session loads constitution/state on open and reports telemetry on close (Model Usage / Agent Health become real, D5), and dashboard ⇄ desktop deep links work both ways.

| # | Item | Pts | Acceptance summary |
|---|---|---|---|
| **P1** | **Session bridge — constitution/state load on open** | 8 | Session startup hooks load `.ai-company/constitution/` + sprint state before work; no manual `load` step; works from repo root in a fresh session |
| **P2** | **Session bridge — telemetry on close** | 8 | Every session closes by posting a session record (start/end ts, commands run, agent/tool usage) to the telemetry endpoint → `Model Usage` / `Agent Health` panels show desktop activity for the first time (D5 numerator groundwork). Fail-open; no data loss on abrupt close |
| **P3** | **Deep link: dashboard → "continue in OpenCode"** | 5 | Dashboard run/target/artifact views offer "continue in OpenCode" opening the desktop at the right session/target |
| **P4** | **Deep link: desktop → "submit for review"** | 5 | From a desktop session, a generated artifact can be submitted to the decision/approval inbox for review |
| **P5** | **GUI/desktop action telemetry (D5 numerator)** | 3 | Instrumented action counters distinguish GUI/desktop vs CLI actions so the north-star share metric is honest (numerator + denominator) |
| **P6** | **R3 parity milestone advance** | 3 | Parity tests reach ≥40/71 command rows by Phase 3 close-out; every new command ships its parity test in the same change |

**Sequencing:** P1 → P2 (session bridge core) → P3/P4 (deep links) → P5 (needs P1/P2) → P6 (continuous). **Exit:** ≥90% of generation targets runnable desktop-first without typing a CLI command. **DoD:** suite ≥1364 green; ruff/mypy/format/command-map/CLI-surface clean; trackers updated with each commit (CLI surface frozen — ADR 0006; desktop hooks must not change CLI). **Groundwork already committed:** `src/ai_company/agents/` agent-sync engine + `tests/test_agents_sync.py` (initiative note "untracked" is stale).

### 2. Sprint 5.6 â€” Svelte 5 Migration (Phase 4) ðŸ”®
**ADR:** 0008 (v2 deferred) â€” richer UX with Svelte 5 + Vite when budget allows.

---

## Open Issues & Decisions Needed

| Issue | Context | Decision Needed |
|---|---|---|
| ~~SQLite read model rebuild trigger~~ | ADR 0004 accepted | âœ… **Resolved (Sprint 5.3): rebuild on startup** via `initialize_read_model` step (`ReadModelEngine` rebuild-on-construct) |
| ~~Agent sync `--scope` default~~ | Previously defaulted to `project` | âœ… **Resolved (Sprint 5.3): default `both`** for new users (project + global) |
| ~~Dashboard port binding~~ | Hardcoded `127.0.0.1:8000` | âœ… **Resolved (Sprint 5.3): keep hardcoded loopback default**; overridable via `--host/--port`; non-loopback requires ADR 0010 auth |
| ~~Windows CI matrix~~ | Only test job ran on Windows | âœ… **Resolved (Sprint 5.3): lint + type-check also run on Windows** (ubuntu + windows matrix) |

---

## Recently Completed (Commits)

```text
1fd0c97        feat: R4 â€” end-to-end free/local fallback for generate dispatch (D9 close-out)
936f9ea        fix: strip ANSI styling from CLI help in parity test (CI FORCE_COLOR wraps tokens)
de9c851        feat: Sprint 5.3 â€” SQLite read model on startup (ADR 0004), agent sync scope both, Windows CI lint/type-check
2244497        feat: Phase 2 Wave 2b + telemetry/parity/backup close-out (generate loop, decision inbox, R5 telemetry)
66cf7c4        chore: refresh api package exports for Phase 2 write surface (ADR 0010)
479f5c6        chore: refresh .ai/ knowledge base for Phase 2 wave 2a (ADR 0010 ratified, write surface live)
131d9d9        feat: Phase 2 wave 2a â€” write auth (ADR 0010), 20 mutation endpoints, audit + token CLI
b88c0b6        chore: record Phase 1 wave 2 commit hash in current-work tracker
d0b1385        feat: Phase 1 wave 2 â€” dashboard frontend v1 (8 views, scoped CSP, parity seed)
a190434        chore: ratify ADR 0008/0009 and refresh stale project trackers
3af24e5        chore: remove legacy sprint dashboard stub and gitignore dashboards/ output
ce1df08        feat: add .ai/ knowledge base so agents stop re-discovering the system
b6d5a26        feat: Phase 1 wave 1 â€” dashboard API server (read-only contract v1)
27348a1        feat: Phase 0 close-out â€” restore drill, Windows CI, live recovery drill
3324dbf        feat: Phase 0 command centers â€” telemetry, backup, integrity gate, self-healing
```

---

## Key Context for Next Session

1. **Sprint 5.3 (SQLite read model + decision close-out) is COMMITTED** (`de9c851`)
   â€” the four orphaned decisions from the previous session are resolved,
   implemented, and shipped: read model rebuild **on startup** (ADR 0004,
   `runtime/dashboard.db` WAL projection over the JSONL sources of truth, via
   the `initialize_read_model` boot step), agent sync `--scope` default **both**,
   dashboard port stays **127.0.0.1:8000**, and **Windows CI** now runs
   lint/type-check. Suite: **1265 tests green**; ruff/mypy/format clean.
   **Pushed to origin/main; CI fully green (8/8 jobs).**

2. **D5 + D9 CEO sign-offs recorded (2026-08-02)** â€” D5: north-star metric =
   share of operator actions via Dashboard/OpenCode desktop **â‰¥80% by month 6**
   (baseline = CLI telemetry `runtime/cli_telemetry.jsonl`; GUI telemetry in
   Phase 3). D9: fallback provider strategy = **free/local models** (e.g.
   `ollama/llama3.1:8b`) â€” **R4 â†’ `[MITIGATED]` 2026-08-02** via the shared
   `services/generate_dispatch.py` fallback, proven end-to-end. Logged in
   `docs/dashboard/initiative.md` + `.ai/decisions.md`.

3. **Dashboard-initiative follow-up risks (2026-08-02 batch)** â€” **R12
   MITIGATED**: canonical status service (`services/status_service.py`, four
   states + timestamp, phase-state-machine derived) unifies CLI/API/dashboard;
   root cause of misleading "unhealthy" flags fixed (`HeartbeatSender` liveness
   worker + read-model `check_same_thread=False`). **R8**: CLI surface integrity
   gate live in CI (`integrity/check_cli_surface.py` vs committed contract;
   additive-only, exit 1 on removal/rename/change, `--update` for additive
   drift). **R3**: parity milestone â‰¥40/71 rows by Phase 3 close-out. **R11 â†’
   MITIGATED**: D10 persona onboarding **SIGNED OFF by CEO 2026-08-02**
   (View/Operate/Develop, one skippable first-run tour each + tooltips, no
   tutorial system). **R4 â†’ MITIGATED**: end-to-end free/local fallback shipped
   (`services/generate_dispatch.py`, `config/runtime/model_fallback.yaml`).

4. **R5 telemetry is live** â€” runtime metrics persist every 30s to
   `runtime/metrics_history.jsonl`, provider usage to
   `runtime/provider_usage.jsonl` (aggregated by model). KPI / Model Usage /
   Agent Health panels on `/telemetry` render real data (no more "data
   pending").

5. **`.ai/` knowledge base is complete** â€” 8 files, committed. **Rule: update
   the relevant `.ai/` file after every commit** so agents never re-discover
   the system.

6. **Constitution is immutable** â€” `.ai-company/constitution/rules.md`
   cannot be overridden by any agent. Read sprint state first, update it last.

7. **CLI is frozen** â€” the Typer command tree is a contract (ADR 0006). New
   features must back-port CLI commands; CI validates the command map.
   Wave 2a token CLI was additive-only (`dashboard token` sub-group); Wave 2b
   made no CLI surface changes.

8. **Workspace resets to HEAD** â€” commit work promptly; uncommitted files
   (including `.ai/`) get wiped.

9. **Parity test suite is seeded** â€” `tests/golden/test_parity_read.py`
   (golden CLI output == API JSON) plus `tests/golden/test_parity_wave2b.py`
   (generate/backup contract + shared guard parity) plus
   `tests/golden/test_parity_status.py` (canonical status CLI == API, 2026-08-02).
   Every new read command must add a parity row + parity test (Phase 4 demotion
   trigger depends on it). Wave 2b flipped all remaining safe-write rows to `1+2`.

10. **CI segfault flake FIXED (2026-08-03)** â€” the intermittent ubuntu `test`
    job `Segmentation fault` (exit 139) was root-caused: shutdown stopped
    engines before workers, so supervisor/health/heartbeat threads probed the
    closed SQLite connection during teardown. Fix: `shutdown.py` reorders to
    `stop_workers` before `stop_engines`; `ReadModelEngine.health()` guards
    `sqlite3.Error`. CI runs `30799819043` + `30800484976` both 8/8 first-try
    (previously ~15% fail rate). If a segfault reappears, re-run the failed job
    once before investigating code.

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

# Token management (ADR 0010) â€” value printed only on first-time creation
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
| `company/*.yaml` | Persona source of truth â€” triggers agent re-sync |
| `config/runtime/startup.yaml` | Declarative boot â€” affects runtime lifecycle |
| `config/orchestration/engine.yaml` | Pipeline definitions |
| `opencode.json` | Provider config, agent definitions â€” CI validates |
| `docs/adr/*.md` | New ADRs = new sprints |
| `.ai-company/state/current_sprint.yaml` | Active sprint â€” update when starting/completing |
| `pyproject.toml` | Dependencies/tooling â€” version bumps need testing |
| `src/ai_company/api/auth.py` | ADR 0010 write guards â€” fail-open audit semantics must not change |

---

*Updated: 2026-08-02 â€” **Sprint 5.4 T5 SHIPPED (commit `b93a886`, run `30759697395`; shutdown reorder fix for exit-139; local suite 1364 green, >10 consecutive local runs green)** — **Sprint 5.4 T2 SHIPPED + CI GREEN (commit `11fde80`, run `30759697395`; all 8 jobs green — ubuntu `test` re-ran after the known exit-139 segfault flake per T5 protocol, passed attempt 2)** (retention/rollup: `telemetry/retention.py` rollup-then-truncate with idempotent hourly/daily aggregates + config-driven policies via `config/runtime/telemetry.yaml` (9th config section), `telemetry_retention` recurring scheduler job, `RuntimeFacade.retention_status` + `GET /api/telemetry/retention` + telemetry caption, everything fail-open; +20 tests â†’ suite **1364 green**; ruff/mypy/format/command-map/CLI-surface clean); **Sprint 5.4 T3 SHIPPED + CI GREEN (run `30758507616`: 8/8 jobs, no reruns)** (isolation alerting: unified `runtime.engine_isolated`/`runtime.engine_unisolated` events from the supervisor isolate/unisolate funnel (attempts carried from failed recovery), fail-open `runtime/alerts.jsonl` + `telemetry/alerts.py` with no-spam summary (latest record per component wins, resolved on un-isolate), `GET /api/alerts`, pulse/System Health red chip + health alert table + telemetry KPI line; +17 tests â†’ suite **1344 green**; ruff/mypy/format/command-map/CLI-surface clean); **Sprint 5.4 T4 SHIPPED + CI GREEN (run 30757132205: 8/8 jobs, no reruns)** (recovery-success metric: `recovery_attempts/successes/failures` counters + `recovery_success_rate` gauge recorded once per `RecoveryManager` outcome (concrete recovery = success; escalate/isolate/exhausted = failure); shared tolerant `metrics_trend()` fixes a latent T1 shape bug so the facade's flattened `metrics_persist` dump now renders gauges on the KPI panel; new **Self-healing** KPI card (`cols-5`); +7 tests â†’ suite **1327 green**; ruff/mypy/format/command-map/CLI-surface clean); **Sprint 5.4 T1 SHIPPED** (SQLite live telemetry store: `sync_from_jsonl` incremental watermark sync, facade reads prefer the store w/ JSONL fallback, sync wired into the 30s ticker via `metrics_persist`; suite 1308 â†’ **1320 green**); **CI green on main** (run 30755035002: 8/8 jobs â€” the ubuntu `test` job hit the **known exit-139 segfault flake** after `test_runtime_restart.py` and passed on rerun; run 30754497955: 8/8 jobs â€” one `test-windows` rerun for a **timing flake** in `test_engines_stay_healthy_and_not_isolated_after_boot`'s final psutil `system` health sweep (DEGRADED on the loaded shared runner; isolation + heartbeat assertions passed; ubuntu `test` green first try; passes locally 3Ã—; unrelated to T1 â€” T5 tracks the segfault, Windows health blip is runner-load noise); Sprint 5.3 (`de9c851`) + R12 batch (`147540b` + `75e0595`) + R8/R3/R11 batch (`38a3d7f` + typer-group fix `935beeb`) + **R4 fallback (`1fd0c97`)** all committed + pushed; **R4 `[MITIGATED]`** â€” shared `services/generate_dispatch.py` fallback (opencode â†’ free/local `ollama`) proven end-to-end across runner/CLI; **D10 persona onboarding SIGNED OFF (R11 â†’ `[MITIGATED]`)**; R12 `[MITIGATED]`; R8 gate live (CLI surface contract, additive-only); R3 parity milestone set (â‰¥40/71 rows by Phase 3); suite 1265 â†’ **1308 green**; **CI green on main (run 30750231104: 8/8 jobs, after one documented-segfault-flake rerun of the ubuntu `test` job)**; **Sprint 5.4 PLANNED & COMMITTED â€” see "Sprint 5.4 Backlog" above (T1â€“T4 = 22 pts, T5 CI-flake stretch); next candidates: Sprint 5.5 (Phase 3 desktop), Sprint 5.6 (Svelte 5)***
*Next update: at the first Sprint 5.5 commit (Phase 3 kickoff) — current `current_sprint.yaml` = Sprint 5.4 COMPLETE, awaiting Sprint 5.5 plan commit.*
