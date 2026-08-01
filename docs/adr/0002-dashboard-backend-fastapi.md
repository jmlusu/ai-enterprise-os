# ADR 0002 — Dashboard backend: FastAPI + uvicorn (plain) + WebSocket

Status: Accepted
Date: 2026-08-01
Deciders: CTO, Cloud Architecture, Software Engineering

## Context

The dashboard needs a local-first HTTP + WebSocket backend that:

- exposes REST endpoints for the parity matrix (ADR 0001),
- streams runtime events to live views,
- runs on Windows (the primary dev platform) and Linux (CI),
- integrates with the existing threaded runtime (EventBus, heartbeats).

The repo currently has no web/async dependencies (pure sync, thread-based).

## Decision

1. **FastAPI** for REST + WebSocket endpoints.
2. **uvicorn (plain, not `[standard]`)** as the server — the `standard`
   extra installs `uvloop`, which breaks on Windows.
3. Add FastAPI + uvicorn to project dependencies; keep the runtime
   thread-based and bridge async ↔ sync via a thread executor.
4. The EventBus is the WebSocket subscription substrate: dashboard views
   subscribe to `runtime.*` events (persistence, replay, dead-letter
   already exist).

## Consequences

- First web/async dependencies enter the repo (audited via `uv audit`).
- Async handlers must never block on runtime locks directly; use the
  thread executor for sync calls.
- Frontend choice (Jinja2+htmx vs Svelte 5) remains open — the API
  contract is frontend-agnostic.
