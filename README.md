# AI Enterprise OS

Building scalable local AI agent workflows.

## Quickstart

```bash
# Install uv (if not installed)
powershell -c "irm https://get.uv.io/install.ps1 | iex"

# Sync dependencies
uv sync --group dev

# Run the CLI
uv run python -m ai_company.cli.main --help

# List available targets
uv run python -m ai_company.cli.main targets

# Generate a phase
uv run python -m ai_company.cli.main generate <target>

# Run tests
uv run --group dev pytest

# Lint
uv run --group dev ruff check

# Type-check
uv run --group dev mypy src
```

## Project structure

```
src/ai_company/     # Package source
company/            # Company registry (YAML)
prompts/            # OpenCode prompt files
templates/          # Jinja2 templates
```
