# Technical Diagrams

P0 diagram set (created 2026-08-04). All diagrams are Mermaid and render in-page
on the dashboard (vendored `mermaid 10.9.1`) and on GitHub.

| # | Diagram | File | Priority |
|---|---|---|---|
| 1 | System architecture (full refresh — Sprint 4.5 → 5.5) | `docs/architecture-diagram.md` | P0 |
| 2 | Runtime boot / shutdown lifecycle (phase machine, 11-step boot, 6-step stop) | `docs/diagrams/runtime-lifecycle-diagram.md` | P0 |
| 3 | Dual command-center architecture (workshop / boardroom / CLI) | `docs/diagrams/command-centers-diagram.md` | P0 |
| 4 | Write-auth guard flow (ADR 0010 — token → CSRF → audit → D5) | `docs/diagrams/write-auth-flow-diagram.md` | P0 |

Planned backlog: telemetry data-flow (P1), session bridge sequence (P1),
orchestration / COO pipeline (P1), supervisor self-healing state machine (P1),
read model / ADR 0004 (P1), generate dispatch + fallback (P2), dashboard
view → endpoint → facade map (P2), deep-link map (P2), event bus internals (P2),
deployment topology (P2).
