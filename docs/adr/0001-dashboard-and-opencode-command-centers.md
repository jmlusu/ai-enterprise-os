# ADR 0001 — Dashboard and OpenCode as the primary command centers

Status: Accepted
Date: 2026-08-01
Deciders: CTO, Chief of Staff, Architecture (12-expert team analysis)

## Context

The AI Enterprise OS was originally built CLI-primary. Usage patterns and
the 12-expert team analysis surfaced a need to shift control surfaces:

- The GUI Dashboard should become the major *human* command center.
- The OpenCode desktop app should become the main *agentic* command center
  (agents work from a GUI session, not a terminal).
- The CLI is demoted to a secondary, power-user/automation surface — it is
  retained, never deleted, because CI and scripts depend on it.

## Decision

1. Build a GUI dashboard (see ADR 0002) as the primary human interface.
2. Standardize on OpenCode desktop as the agent command center; all
   `ai-company generate <target>` dispatches render prompts for OpenCode
   (`command_map.yaml` → `opencode run --agent architect`).
3. Keep the CLI fully operational as the automation contract (CI runs
   `ai-company build`, `ai-company validate`; scripts use `--dry-run`).

## Consequences

- Dashboard and OpenCode surfaces share one backend/services layer
  (ADR 0003) so behavior is identical across surfaces.
 - CLI parity is tracked in `docs/dashboard/parity-matrix-v0.md`.
- No CLI command is removed; new features may ship on the dashboard first
  and be back-ported to the CLI.
