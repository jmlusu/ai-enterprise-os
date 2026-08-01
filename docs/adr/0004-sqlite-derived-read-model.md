# ADR 0004 — SQLite (WAL) derived read model for dashboard reads

Status: Accepted
Date: 2026-08-01
Deciders: CDO, Data Engineering, Cloud Architecture

## Context

The runtime persists single-writer JSONL/JSON state (memory/, events/,
generated/, runtime/). Dashboard views need fast, consistent reads across
many state files (metrics, heartbeats, health, events, generated
artifacts).

## Decision

1. Derive a **SQLite (WAL mode)** read model from the JSONL/JSON source
   of truth.
2. The JSONL/JSON files remain the source of truth; SQLite is a derived,
   rebuildable projection for dashboard queries (never written by the
   CLI/services directly except through the sync/replay path).
3. WAL mode for concurrent dashboard reads while the runtime writes.

## Consequences

- `runtime/dashboard.db` (gitignored) can be rebuilt at any time from the
  event log — no data-loss risk.
- The read model is built in Phase 1; until then the dashboard reads the
  JSONL/JSON sources directly.
