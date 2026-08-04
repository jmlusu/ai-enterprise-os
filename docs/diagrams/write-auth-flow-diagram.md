# Write-Auth Guard Flow Diagram

Every mutation from any surface (dashboard browser, OpenCode desktop plugin,
curl) flows through the shared `WriteGuard` — the single choke point for write
auth (ADR 0010). Success also feeds the D5 action telemetry numerator
(Sprint 5.5 P5). Sources: `src/ai_company/api/guards.py`, `api/auth.py`,
`api/write_endpoints.py`, `api/operational_endpoints.py`.

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator surface<br/>(browser · desktop plugin · curl)
    participant S as api/app.py (FastAPI)
    participant G as WriteGuard (guards.py)
    participant A as auth.py<br/>WriteTokenService + CsrfService
    participant B as EventBus → audit (fail-open JSONL)
    participant T as telemetry/actions.py (D5)

    Note over Op,S: CSRF handshake — unauthenticated (ADR 0010 §2)
    Op->>S: GET /api/write-csrf
    S-->>Op: 200 {"csrf_token": "<per-run>"}

    Note over Op,S: Mutation — POST /api/&lt;action&gt;
    Op->>S: Authorization: Bearer &lt;token&gt; (optional on loopback)<br/>X-CSRF-Token: &lt;csrf&gt;<br/>body reason (high-impact actions only)
    S->>G: guard(action) dependency
    G->>A: host_allowed(request.host)

    alt Non-loopback host OR --require-loopback-token
        Note over G: token MANDATORY (fail-closed)
        alt Missing or invalid token
            G-->>B: audit.write_rejected (unauthorized)<br/>token/CSRF values never exposed
            G-->>Op: 401 invalid write token
        else Valid token
            Note over G: constant-time verify
        end
    else Loopback + no flag
        Note over G: token optional — validated if present
    end

    G->>A: csrf.verify(x-csrf-token)
    alt CSRF missing or invalid
        G-->>B: audit.write_rejected (csrf_mismatch)
        G-->>Op: 403 invalid CSRF token
    end

    Note over G: action in HIGH_IMPACT_ACTIONS?<br/>(runtime.stop/restart/recover/unisolate,<br/>orchestrate.rollback)
    alt High-impact and reason blank
        G-->>B: audit.write_rejected (missing_reason)
        G-->>Op: 422 reason is required
    end

    S->>S: facade write adapter<br/>(services/runtime_facade.py — ADR 0003)
    S->>G: audited(result, action, reason, extra, source)
    G-->>B: audit.write (result ok|failed, reason, details)
    G->>T: record_action(source, action)<br/>source = "gui" | "desktop" | None (plumbing skip)
    S-->>Op: 200/201 result (+ deep_link where applicable)
```

## Guard semantics

| Check | Failure | Audit event | HTTP |
|---|---|---|---|
| Host allowlist + token mode (non-loopback → mandatory, fail-closed; loopback optional; `--require-loopback-token` forces) | Missing/invalid bearer | `audit.write_rejected` (reason `unauthorized`) | 401 |
| CSRF synchronizer token (per-run, `GET /api/write-csrf`) | Missing/invalid `X-CSRF-Token` | `audit.write_rejected` (reason `csrf_mismatch`) | 403 |
| High-impact action reason (`HIGH_IMPACT_ACTIONS`) | Blank reason | `audit.write_rejected` (reason `missing_reason`) | 422 |
| Success | — | `audit.write` + `record_action(source, action)` | 200/201 |

## Notes

- **Fail-open:** if the EventBus publish raises, the audit record falls back to
  `runtime/.audit.failed.jsonl`; a blocked write never records an action
  (401/403/422 produce no D5 contribution). Rejected payloads never leak the
  submitted token/CSRF values.
- **D5 telemetry (P5):** `source="gui"` (dashboard operator writes), `"desktop"`
  (desktop-originated, e.g. `review.submit`), or `None` (plumbing like
  `telemetry.session.persist`, not an operator action).
- **Reason:** captured in the audit payload; validated for sanity by the service.
- **WS non-loopback:** WebSocket clients use `?token=` query param (cannot set
  headers); channel enforced with close code 1008 (ADR 0010 §1).
- Token storage: `runtime/.write_token` (owner-only, optional SHA-256
  hash-at-rest via `serve --hash-at-rest`), env override
  `AI_ENTERPRISE_WRITE_TOKEN`.

## References

- `docs/adr/0010-phase2-write-auth-csrf-audit.md` — full decision + ratified surface
- `docs/dashboard/phase2-workplan.md` — Wave 2a implementation detail
- `src/ai_company/api/guards.py` — `WriteGuard.guard()` / `require_reason()` / `audited()`
