# OpenCode project-local agent template

This directory is the committed template for the project-local OpenCode
configuration that lives in `.opencode/` (which is gitignored because it
contains `node_modules/` for plugins).

## Install

Copy the contents into `.opencode/`:

```powershell
Copy-Item -Recurse templates/opencode/* .opencode/
```

or (POSIX):

```bash
cp -r templates/opencode/. .opencode/
```

## Contents

- `agents/` — project subagents used by `ai-company generate` targets and
  persona sync. `architect` is required by `command_map.yaml`.
- `package.json` — the OpenCode plugin dependency (`@opencode-ai/plugin`),
  required for plugin-based tooling. Run `opencode` once after copying to
  install `node_modules`.
- `.gitignore` — mirrors the real `.opencode/.gitignore` so the copied
  directory stays untracked (node_modules + lockfiles + the local config
  files themselves remain machine-local).

## Keeping agents in sync

Agent files are also generated from company personas:

```bash
uv run python -m ai_company.agents sync            # project scope (.opencode/agents)
uv run python -m ai_company.agents sync --dry-run  # preview
uv run python -m ai_company.agents sync --force    # overwrite edited files
```

See `src/ai_company/agents/` for the sync engine.
