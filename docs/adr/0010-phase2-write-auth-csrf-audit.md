# ADR 0010 — Phase 2 write auth: bearer token (loopback-optional) + CSRF + mandatory write audit

Status: **Accepted** (decision D8) — ratified 2026-08-01 with Phase 2 Wave 2a shipment
Date: 2026-08-01
Owner: Chief Architect · Reviewers: CISO, Cybersecurity Architecture, Software Engineering
Related: ADR 0002 (backend), ADR 0003 (services layer), ADR 0009 (API contract, read-vs-write split), ADR 0008 (frontend), `docs/dashboard/parity-matrix-v0.md`

## Context

ADR 0009 deferred all write endpoints (Phase 2) until a write-auth token + CSRF header + audit scheme is designed. The server is loopback-only (binds `127.0.0.1`, Host-header allowlist) and the read-only contract v1 is live (committed in Phase 1, 6d2654b).

**Requirements from ADR 0009:**
- write-auth token (non-loopback → token mode; loopback → optional but supported)
- CSRF header on mutations
- mandatory audit event on every write

**Two critical enhancements from Phase 2 recommendations:**
1. **Fail-closed non-loopback bind:** non-loopback bindings MUST enforce token mode for *every* request; no token → 401.
2. **Optional hash-at-rest tokens:** token file may store SHA-256 digest instead of plaintext; CLI flag `--hash-at-rest` to control.

This ADR ratifies the security scheme (CISO input incorporated) and integrates the two enhancements above as Phase 2 requirements.

## Decision

**Adopt: opaque bearer token + double-submit CSRF + mandatory write audit, with two enhancements:**

### 1. Write token (authentication)

- **Format:** opaque `secrets.token_urlsafe(32)` (256-bit).
- **Storage:** default plain token file (`runtime/.write_token`). Optional hash-at-rest mode (SHA-256), controlled by `ai-company serve --hash-at-rest`. On generation, CLI prints token value **only** for the first-time creation; rotated tokens are not printed.
- **On-disk:** `runtime/.write_token` (owner-only 0o600; no extra ACLs on Windows).
- **Keyring:** NOT used; CISO preference for single-platform portability.
- **API header:** `Authorization: Bearer <token>` (REST), or `?token=` query param for WebSocket clients that cannot set headers.
- **Loopback vs non-loopback:**
  - **Non-loopback bind:** token mode **mandatory** (fail-closed). No token → 401.
  - **Loopback bind:** token optional but supported; if provided, must be valid.

### 2. CSRF protection (defense-in-depth)

- **Synchronizer token:** per-run `secrets.token_urlsafe(16)` issued at boot.
- **Read-only endpoint:** `GET /api/write-csrf` returns `{"csrf_token": "..."}` (no auth required).
- **Mutation header:** `X-CSRF-Token: <value>`; invalid/missing → 403.
- **Rationale:** even though browser cannot forge bearer tokens from cross-origin pages, the double-submit pattern covers accidental navigations, and Host/origin checks close the DNS-rebinding vector.

### 3. Mandatory write audit (non-repudiation)

- **Event type:** `audit.write` (and `audit.write_rejected` for failed auth/CSRF).
- **Bus payload:** same structure as normal runtime events; persisted via `EventBus` and replayable.
- **Dashboard:** Write History panel reads from `audit.write` events.
- **Fail-open:** if bus publish raises, log to `runtime/.audit.failed.jsonl` (fail-open), never blocks localhost writes.
- **Rejection audit:** rejected writes publish `audit.write_rejected` (without exposing the submitted token/CSRF).

### 4. Integration with Phase 1 API

- **RuntimeFacade:** remains Phase 1 read-only; Phase 2 write handlers use the same facade but require auth.
- **CLI command:** `ai-company serve --host X.X.X.X --bind` (or default `127.0.0.1`) now has two new flags:
  - `--hash-at-rest` (optional) – store SHA-256 digest; default off for Phase 2.
  - `--require-loopback-token` (optional) – force token on loopback binds (default off).
- **Auto-start:** token mode is enforced at startup based on bind address; the token service is initialized from the file (or env `AI_ENTERPRISE_WRITE_TOKEN`).

### 5. High-impact actions and reason requirement

- **High-impact:** stop/restart runtime, recover/unisolate engines.
- **Reason field:** required in request body; captured in audit payload; validated for sanity by service.

### 6. Parity matrix scope

- **Safe writes** (Phase 2 dashboard actions): moved from `PLANNED (P2)` to `SHIPPED (P2)` once this implementation lands.
- **Destructive/bulk** (CLI-only) remain untouched.

## Consequences

Positive:
- Fulfils ADR 0009's exact Phase 2 conditions + two enhancements (fail-closed, hash-at-rest).
- Non-repudiable audit events on every write, replayable.
- Hash-at-rest adds a protection layer for config leakage (Phase 3 default-on).
- Fail-closed non-loopback blocks accidental exposure.
- CSRF and bearer token together close all known localhost vectors.
- Parity matrix convergence (dashboard-only writes, CLI-only bulk ops).

Negative / tradeoffs:
- Phase 2 surface is larger (~40 endpoints) — effort allocation required.
- Optional hash-at-rest adds CLI flag complexity (backwards compatible).
- Audit events may grow to ~10k/month in a busy system (Phase 1/2 usage is low).
- Write History panel adds a new data source; still within the Phase 2 scope.

## Alternatives rejected

- **No token on loopback:** rejected by CISO — sibling processes on shared Windows machines could write without token; `--require-loopback-token` flag can enable strictness.
- **Multiple token types (user vs service):** overkill; single operator token is sufficient for Phase 2.
- **JWT with expiry:** not needed; opaque token is stateless, revocable by file replacement.
- **OAuth/OpenID:** beyond scope; localhost only.
- **Push-based token refresh:** stateless model; token rotation is file replacement.

## Ratification (2026-08-01)

Ratified with the Phase 2 Wave 2a shipment (Sprint 5.2). Implemented surface
(see `docs/dashboard/phase2-workplan.md` Wave 2a):

- **`src/ai_company/api/auth.py`** — `WriteTokenService` (create/rotate/revoke/
  verify, constant-time compare, SHA-256 hash-at-rest, env override
  `AI_ENTERPRISE_WRITE_TOKEN`), `CsrfService` (per-run synchronizer token),
  `host_allowed()` (loopback-only Host allowlist), fail-open audit publisher
  to `runtime/.audit.failed.jsonl`.
- **`src/ai_company/api/write_endpoints.py`** — `GET /api/write-csrf`,
  `GET /api/audit/writes`, and 20 mutation POSTs: `/api/runtime/{start,stop,
  restart,reload,recover,unisolate}`, `/api/orchestrate/{plan,start,resume,
  retry,rollback}`, `/api/memory/{save,update,snapshot,restore,export}`,
  `/api/memory/{key}/{archive,unarchive}`, `/api/validate`,
  `/api/reports/generate`, `/api/build`, `/api/bootstrap`. All behind the
  bearer-token + CSRF guard (`audit.write_rejected` published on rejection).
- **High-impact actions** (`HIGH_IMPACT_ACTIONS`): `runtime.stop`,
  `runtime.restart`, `runtime.recover`, `runtime.unisolate`,
  `orchestrate.rollback` — require a `reason` field (422 otherwise); reason
  captured in the audit payload.
- **CLI (additive, ADR 0006):** `ai-company serve --hash-at-rest
  --require-loopback-token`; `ai-company dashboard token create|revoke|list|
  info` (value printed only on first-time creation; rotation never echoes).
- **Tests:** `tests/unit/api/test_auth.py` (18) + `test_write_endpoints.py`
  (11) — host allowlist, CSRF, rotation semantics, audit payloads, fail-open
  JSONL, no token/CSRF leakage in rejected payloads. Suite: 1142 → **1171**.

**Deferred to Wave 2b (unchanged by this ratification):** `POST /api/generate`
(OpenCode dispatch), decision/approval inbox, WS-channel token enforcement for
non-loopback deployments, company CRUD `PUT /api/company`, agent sync, backup,
and CLI-telemetry write surfaces.

## Implementation notes

- **Development:** start Phase 2 with loopback mode (no token required) to test all endpoints; flip `--require-loopback-token` for stricter enforcement.
- **Testing:** add CSRF token endpoints; write-auth dependency for all write handlers; audit verification.
- **Deployment:** first deployment can use `--require-loopback-token` to enforce token on all interfaces; later moves to non-loopback only once token generation and distribution is documented.
