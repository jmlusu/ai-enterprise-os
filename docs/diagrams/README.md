# Technical Diagrams

P0 + P1 diagram sets (created 2026-08-04). All diagrams are Mermaid and render
in-page on the dashboard (vendored `mermaid 10.9.1`) and on GitHub.

| # | Diagram | File | Priority |
|---|---|---|---|
| 1 | System architecture (full refresh — Sprint 4.5 → 5.5) | `docs/architecture-diagram.md` | P0 |
| 2 | Runtime boot / shutdown lifecycle (phase machine, 11-step boot, 6-step stop) | `docs/diagrams/runtime-lifecycle-diagram.md` | P0 |
| 3 | Dual command-center architecture (workshop / boardroom / CLI) | `docs/diagrams/command-centers-diagram.md` | P0 |
| 4 | Write-auth guard flow (ADR 0010 — token → CSRF → audit → D5) | `docs/diagrams/write-auth-flow-diagram.md` | P0 |
| 5 | Telemetry data-flow (JSONL sources of truth → read model / retention / D5) | `docs/diagrams/telemetry-dataflow-diagram.md` | P1 |
| 6 | Session bridge & telemetry-on-close sequence (P1–P4) | `docs/diagrams/session-bridge-sequence.md` | P1 |
| 7 | Orchestration / COO pipeline + pipeline/task state machines | `docs/diagrams/orchestration-pipeline-diagram.md` | P1 |
| 8 | Supervisor self-healing state machine (restart-before-isolate, alert lifecycle) | `docs/diagrams/supervisor-self-healing-diagram.md` | P1 |
| 9 | Read model / ADR 0004 (rebuild on startup, watermark sync, fail-open reads) | `docs/diagrams/read-model-diagram.md` | P1 |

Planned backlog: generate dispatch + fallback (P2), dashboard
view → endpoint → facade map (P2), deep-link map (P2), event bus internals (P2),
deployment topology (P2).
