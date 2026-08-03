# AI Enterprise OS

Local AI agent platform for Lightspeed Holdings Limited (v0.1.0).
Python 3.12-only (`X | None` syntax, Pydantic v2); `hatchling` wheel from
`src/ai_company`; Typer CLI entry `ai-company`; `uv` for dependencies.

## Session Bridge (P1) — load constitution and state on every open

OpenCode auto-loads this file into every session. At the start of the session,
BEFORE writing any code:

1. **Read `.ai-company/constitution/rules.md`** — the immutable Core Directives.
   They are:
   1. **Read State First:** every session MUST read
      `.ai-company/state/current_sprint.yaml` before writing code.
   2. **Always use Pydantic v2** for all data validation and schemas.
   3. **Never use pseudo-code or placeholders** in production files.
   4. **Strict Typing:** all Python modules must use standard `typing`.
   5. **Update State Last:** update the sprint state upon completion.
2. **Read `.ai-company/state/current_sprint.yaml`** — the active sprint and its
   committed plan. Do not work outside the current sprint without noting it.
3. **Read `.ai/current-work.md`** — the committed current-work tracker (what's
   in progress, next steps, blockers). It is the single source of truth for
   session state; `.ai/` knowledge base files are committed and authoritative.
4. On completion, **update `.ai/current-work.md` and the sprint state last**
   (constitution directive 5), then commit promptly (workspace resets to HEAD).

`.ai-company/` is machine-local and gitignored. If any file above is missing,
proceed without blocking — do not fabricate its contents.

## Commands

```bash
uv sync --group dev                      # install
uv run --group dev pytest -xvs           # tests (full suite ~1364)
uv run --group dev ruff check src/       # lint
uv run --group dev mypy --strict src/    # type-check
pre-commit run --all-files               # all hooks
python -m ai_company.agents sync         # sync personas after company/*.yaml changes
ai-company runtime start                 # boot runtime kernel
ai-company serve                         # dashboard API on 127.0.0.1:8000 (loopback)
```

## Conventions

- **CLI is frozen** (ADR 0006): the Typer tree and the command map are enforced
  contracts. New features must back-port CLI commands; never change existing
  command surface. `python -m ai_company.cli.command_map validate` checks the
  command-map integrity gate.
- **Services layer is the single surface** (ADR 0003): CLI, API, and dashboard
  are thin adapters over `services/`; engines stay untouched (ADR 0005).
- **R3 parity rule:** every new read/write surface adds a golden parity test
  (CLI output == API JSON) in the same change; parity matrix:
  `docs/dashboard/parity-matrix-v0.md`.
- **Write auth** (ADR 0010): all mutations go through the shared `WriteGuard` —
  loopback token optional unless `--require-loopback-token`; high-impact
  actions need a `reason`. Never log or render tokens.
- **Dashboard** is loopback-only by default (ADR 0002); statuses use the
  canonical four-state vocabulary `ok`/`watch`/`action`/`unknown` (R12).
- **Quality gates must be green:** full pytest suite, ruff, mypy `--strict`,
  format, command-map, CLI-surface, `uv audit`. CI runs these on ubuntu +
  windows.
- **Trackers:** update `.ai/` and `.ai-company/state/` with each commit so the
  next session never re-discovers the system.
