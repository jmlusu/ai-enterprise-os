# ADR 0003 — Shared services layer (CLI, API, dashboard are thin adapters)

Status: Accepted
Date: 2026-08-01
Deciders: CTO, Software Engineering, Data Engineering

## Context

With three surfaces (CLI, OpenCode `generate` pipeline, dashboard API),
business logic must live exactly once. Duplicating logic per surface is
the main drift risk (the command-map drift this P0 fixed is the symptom).

## Decision

1. Introduce a shared `services/` layer under `src/ai_company/services/`.
2. The CLI, the dashboard API, and OpenCode prompt execution are thin
   adapters that call services; they contain no business logic.
3. New features are implemented in services first, then exposed per
   surface.

## Consequences

- Single source of truth for validation, generation, orchestration.
- Parity matrix (P0-6) tracks which service each surface exposes.
- Migration is incremental: existing CLI code moves into services as
  dashboard endpoints are built (Phase 1), not all at once.
