# AI Enterprise OS

Building scalable local AI agent workflows.

## Quickstart

```bash
# Install uv (if not installed)
powershell -c "irm https://get.uv.io/install.ps1 | iex"

# Sync dependencies
uv sync --group dev

# Show CLI help
uv run ai-company --help

# Run tests
uv run --group dev pytest

# Lint
uv run --group dev ruff check

# Type-check
uv run --group dev mypy src
```

## CLI Commands

| Command | Description |
|---|---|
| `ai-company bootstrap` | Scaffold initial repository structure |
| `ai-company build` | Build generated artifacts |
| `ai-company generate <target>` | Dispatch a phase to OpenCode |
| `ai-company validate` | Validate registry data and configuration |
| `ai-company doctor` | Diagnose environment and configuration |
| `ai-company targets` | List available generate targets |
| `ai-company status` | Show system status overview |
| `ai-company registry list` | List registry entries |
| `ai-company registry show <name>` | Show a registry entry |
| `ai-company registry verify` | Verify registry integrity |
| `ai-company memory show` | Display memory state |
| `ai-company memory clear` | Clear session memory |
| `ai-company graph show` | Display company graph structure |
| `ai-company graph stats` | Show graph statistics |
| `ai-company report generate <type>` | Generate a report |

## Project structure

```
src/ai_company/     # Package source
company/            # Company registry (YAML)
prompts/            # OpenCode prompt files
templates/          # Jinja2 templates
tests/              # Unit tests
```
