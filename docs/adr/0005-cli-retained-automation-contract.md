# ADR 0005 — CLI retained as the automation contract

Status: Accepted
Date: 2026-08-01
Deciders: CTO, DevOps, Chief of Staff

## Context

The pivot demotes the CLI to a secondary surface. However, CI runs
`ai-company build` / `ai-company validate`, scripts use
`ai-company generate <target> --dry-run`, and the OpenCode dispatcher is
itself CLI-shaped. Deleting or breaking the CLI would break automation.

## Decision

1. The CLI is a **supported, tested, retained** surface (never deleted).
2. CI keeps validating the CLI (`generate`, `validate`, `build` jobs).
3. The CLI gains invocation telemetry (P0-4) so usage informs dashboard
   priorities.

## Consequences

- e2e CLI tests remain a hard CI gate.
- Command-map integrity (P0-1) keeps `generate <target>` reliable.
 - New surfaces must reach CLI parity per `docs/dashboard/parity-matrix-v0.md`.
