# Coding Rules

> **Purpose:** The rules every agent must follow when writing code in this
> repo. These are derived from `pyproject.toml`, `.pre-commit-config.yaml`,
> the constitution (`.ai-company/constitution/rules.md`), and ADRs.
> **Update this file whenever the toolchain rules change.**

## 1. Python & Version

1. **Python 3.12 only.** Use modern syntax: `X | None`, built-in generics
   (`list[str]`), `match` where appropriate, `from __future__ import
   annotations` is not required (3.12 handles it natively).
2. **`uv` is the only dependency tool.** Never use pip/Poetry directly.
   Add deps via `uv add --group dev ...`; lockfile `uv.lock` is committed.
3. **No pseudo-code or placeholders in production files** (constitution #3).
   Every module must be complete and runnable.

## 2. Data Validation (Pydantic v2)

4. **Always use Pydantic v2** for all data validation and schemas
   (constitution #2). No `pydantic.v1`, no dataclass-only models where a
   schema is needed.
5. **Use `ConfigDict(frozen=True)` for immutable domain models** (e.g.,
   `CompanyRegistry`). Mutation of registry state is a bug.
6. **Never use `model_dump(mode="json")` for secrets**; keep validated
   models typed end-to-end.

## 3. Typing (mypy `--strict`)

7. **All modules use standard `typing`** (constitution #4): annotate every
   public function signature, class attributes, and `__all__`.
8. **mypy runs `--strict`** in pre-commit and CI. The 13 documented
   `disable_error_code` entries in `pyproject.toml` are **intentional** —
   do not remove them without discussion, and do not add new modules that
   need more disables.
9. **Type `Optional` as `X | None`**; prefer `collections.abc` protocols
   over `typing.Protocol` aliases where possible.

## 4. Linting & Format (ruff)

10. **Zero ruff errors.** `ruff check` (lint) and `ruff format` both run in
    pre-commit and CI. The 14 ignores in `pyproject.toml` are intentional —
    if you think a rule should be removed from the ignore list, explain why.
11. **Import sorting (I001)**: ruff isort rules apply — keep imports sorted;
    stdlib first, third-party, then local; `circuit_breaker` before
    `configuration` etc. Never rely on the editor to fix it.
12. **No `print()` in production code** — use `logging` or the rich console
    (`ai_company.utils.console`).

## 5. Architecture Guardrails (ADR-derived)

13. **CLI tree is frozen (ADR 0006).** New features must back-port CLI
    commands; CI validates `command_map.yaml` ↔ prompts ↔ `opencode.json`.
    Never remove a CLI group without an ADR.
14. **Business logic lives in `services/` (ADR 0003).** CLI, API, and
    OpenCode are thin adapters. Do not duplicate runtime wiring per surface —
    go through `RuntimeFacade`.
15. **Engines never call each other directly.** The Coordinator dispatches
    pipeline tasks by `task_type`. Add handlers to the Coordinator, not
    direct imports.
16. **Config is declarative.** Pipelines, schedules, startup steps, recovery
    policies, engine configs go in `config/**/*.yaml` — not hardcoded in
    Python.
17. **Supervisor restarts before isolating (ADR 0007).** Recovery gets
    `max_recovery_attempts` retries; `isolate` raises if no process record.

## 6. Naming & Structure

18. **Module/package naming:** lowercase, underscore-separated (PEP 8).
    One module per concern under `src/ai_company/<area>/`.
19. **Exports:** every package `__init__.py` exposes `__all__` for its public
    API. Public names are stable; private (`_`-prefixed) names are not.
20. **Tests mirror source:** `tests/test_<module>.py` per source module.
    New features ship with tests (see section 8).

## 7. Security & Data

21. **Never commit secrets.** `.env*` is gitignored (only `.env.example`
    kept); `detect-private-key` hook runs in pre-commit. Config with real
    credentials stays out of the repo.
22. **Dashboard API stays loopback-only (ADR 0009).** Non-loopback exposure
    requires Phase 2 write auth (ADR 0010): bearer token, CSRF, mandatory
    write audit, fail-closed Host checks.
23. **Fail-open observability.** CLI telemetry and event persistence must
    never break the user command — wrap persistence in try/except and
    continue.

## 8. Testing & CI

24. **Tests use `uv run --group dev pytest -xvs`.** `testpaths = tests`,
    `pythonpath = src`. Write tests before/with new behavior.
25. **CI gate:** lint + mypy + tests (Windows matrix) + command-map integrity
    + `uv audit`. A commit that breaks CI is a failed commit.
26. **`uv audit`** runs in CI — keep dependencies current and non-vulnerable.

## 9. Commits & State

27. **Read `.ai-company/state/current_sprint.yaml` first, update it last**
    (constitution #1, #5). Every work session ends by updating sprint state.
28. **Commit messages:** `feat:` / `fix:` / `chore:` / `docs:` prefixes,
    imperative mood, ≤ ~72 chars. Reference ADR numbers when architecture
    is touched.
29. **Update `.ai/` after each commit** — the whole point of this directory
    is that agents don't re-discover the system. Any commit that changes
    architecture, commands, config, or personas must update the matching
    `.ai/` file in the same PR.
30. **Generated output is never committed.** `generated/`, `memory/`,
    `runtime/`, `events/`, `reports/` are gitignored. Pre-commit excludes
    `generated/` and `.ai-company/`.

## 10. Agent-Specific Rules

31. **Constitution is immutable** — no agent may edit
    `.ai-company/constitution/rules.md`.
32. **Personas are YAML source of truth.** Edit `company/*.yaml` and run
    `python -m ai_company.agents sync`. Never hand-edit
    `~/.config/opencode/agents/*.md`.
33. **No fabrication.** Only use provided context; cite files, ADRs, and code
    for every claim (constitution behavior, enforced by agents).
34. **No silent failures** — surface errors immediately with file/line refs.
