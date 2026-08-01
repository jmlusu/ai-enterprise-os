# ADR 0006 — Command map is an enforced contract (CI integrity check)

Status: Accepted
Date: 2026-08-01
Deciders: Software Engineering, CTO

## Context

`src/ai_company/cli/command_map.yaml` maps every `ai-company generate`
target to a prompt file, agent, and model. Drift accumulated: 9 of 11
targets pointed at prompt files that did not exist, and every target
referenced an `architect` agent that was not defined in `opencode.json`.
Runtime impact: `generate` failed on real targets, and the supervisor
isolated engines instead of restarting them.

## Decision

1. `command_map.yaml` targets now resolve to the 8 real prompt files under
   `prompts/opencode/`; all 8 prompts are reachable (no orphans).
2. `opencode.json` defines the `architect` agent used by every target.
3. CI runs `uv run python -m ai_company.integrity.check_command_map`,
   which fails the build on: missing prompt file, unknown agent, malformed
   model, or orphan prompt (ADR contract enforced automatically).

## Consequences

- Drift is caught in CI instead of at runtime.
- Adding a target or prompt file now requires updating the map (or the
  check fails).
- The supervisor recovery fix (P0-3) is tracked separately in ADR 0007.
