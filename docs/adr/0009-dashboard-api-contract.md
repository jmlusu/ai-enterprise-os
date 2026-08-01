# ADR 0009 — Dashboard API contract: REST + WebSocket, replay-based reconnect

Status: **Proposed** (decision D3)
Date: 2026-08-01
Owner: Chief Architect · Reviewers: SWE, Cybersecurity Architecture
Related: ADR 0002 (backend), ADR 0003 (services layer), ADR 0008 (frontend),
`docs/dashboard/parity-matrix-v0.md`

## Context

The dashboard and OpenCode desktop both need a stable, versioned surface over
the runtime. Pydantic models are already JSON-ready — they become API schemas
for free. Security matters: the web server is a new attack surface on a
localhost machine (R9).

## Decision

**Contract v1 (ratified shape, details finalized in Phase 1):**

- **Transport:** REST (JSON) for commands/queries; WebSocket for live push
  (EventBus subscriber → per-client `asyncio.Queue`). Snapshot ticker 1–5s.
- **Reconnect:** client sends `?since=<event_id>`; server answers with
  `EventBus.replay()` from that id. No custom message bus.
- **Pydantic models are the schemas.** Every endpoint returns/accepts the
  existing runtime models; no parallel DTO layer in v1.
- **Read vs write split:** all read endpoints available in Phase 1 (read-only);
  write endpoints (Phase 2) require:
  - write-auth token (non-loopback → token mode; loopback → optional but
    supported), CSRF header on mutations, and an **audit event** on every write.
- **Security baseline (R9):** bind `127.0.0.1` only; Host-header + CORS checks;
  CSP headers; DOMPurify on all Markdown before render; keys in OS keyring,
  never rendered; honest status vocab (four-state: All good / Watch / Needs
  action / Unknown — color+icon+text, never color alone).

## Consequences

- Frontend-agnostic: Jinja2/htmx (ADR 0008 v1), Svelte (v2), and OpenCode
  desktop all consume the same contract.
- Parity test suite: golden CLI output == API JSON per command (Phase 4 gate).
- Versioning: `Accept: application/vnd.aios.v1+json` once endpoints stabilize
  in Phase 1; contract stability is a release blocker from Phase 2 onward.
