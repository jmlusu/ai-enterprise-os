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
| `ai-company validate` | Validate registry data, configuration, and generated output |
| `ai-company validator engine` | Run full Validator Engine (YAML, registry, templates, manifest, output) |
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
| `ai-company serve` | Start the web dashboard at http://127.0.0.1:8000/ (read + guarded writes) |
| `ai-company dashboard token create/list/revoke` | Manage the dashboard write token |

## Web Dashboard

```bash
uv run ai-company serve          # http://127.0.0.1:8000/
uv run ai-company dashboard token create  # optional write-token setup
```

Health, telemetry, generate, decisions, and guarded operator actions in a
browser UI. Full walkthrough: [docs/DASHBOARD_GUIDE.md](docs/DASHBOARD_GUIDE.md).

## Template Engine

Multi-format template rendering system with format-specific handlers.

| Component | Description |
|---|---|
| `TemplateLoader` | Loads templates from files or strings, auto-detects format by extension |
| `TemplateContext` | Key/value context with dot-path support for nested access |
| `Renderer` | Dispatches to format-specific handlers (Jinja2, Python `{key}`, Markdown, JSON, YAML) |
| `Writer` | Writes rendered output to file or stdout |

```python
from ai_company.template_engine import TemplateLoader, TemplateContext, Renderer

loader = TemplateLoader()
content, fmt = loader.load("template.j2")  # fmt = "jinja"
ctx = TemplateContext.from_dict({"name": "World"})
output = Renderer().render(content, ctx.to_dict(), fmt=fmt)
```

## Validator Engine

The Pydantic-based Validator Engine validates 5 targets across the pipeline:

| Target | Checks |
|---|---|
| **YAML** | Syntax, file existence, empty files for all registry YAML files |
| **Registry** | Cross-file consistency, department resolution, vision/board integrity |
| **Templates** | Jinja2 syntax parsing, required template presence, empty templates |
| **Manifest** | Schema compliance, business rules (name, departments, semver) |
| **Generated Output** | File existence, non-empty content, unresolved placeholders |

```python
from ai_company.validator import ValidatorEngine

result = ValidatorEngine().validate_all()
print(
    result.summary()
)  # e.g. "Validator Engine [PASSED]  42 checks, 0 errors, 2 warnings across 5 target(s)"
result.passed  # True if all reports passed
result.total_errors  # total error count
```

## Project structure

```
src/ai_company/
  models/             # Pydantic data models
  registry/           # Registry engine (loader, parser, validator, resolver)
  validator/          # Validator Engine (reports, YAML, registry, templates, manifest, output)
  bootstrap/          # Bootstrap generator (loader, validator, placeholder generator)
  template_engine/    # Template rendering (loader, context, renderer, writer, handlers)
  cli/                # Typer CLI commands and groups
config/company/     # Company manifest (company.yaml)
company/            # Company registry (YAML data files)
prompts/            # OpenCode prompt files
templates/          # Jinja2 templates
tests/              # Unit tests
```
