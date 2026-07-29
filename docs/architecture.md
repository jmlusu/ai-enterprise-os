# AI Enterprise OS Architecture
**Company:** Lightspeed Limited
**Vision:** AI Enterprise OS Vision

## Overview
Building scalable local AI agent workflows.

## Core Subsystems
1. **Registry Engine:** Loads and validates company YAML data.
2. **Generator Engine:** Renders Jinja2 templates from registry data.
3. **CLI Dispatcher:** Typer-based command routing with command groups.
4. **Docs Engine:** Generates project documentation.
5. **Agents Engine:** Defines OpenCode agent personas.
6. **Dashboard Engine:** Renders state and health dashboards.

## CLI Command Groups

| Group | Commands | Purpose |
|---|---|---|
| _root_ | `bootstrap`, `build`, `generate`, `validate`, `doctor`, `targets`, `status` | Core operations |
| `registry` | `list`, `show`, `verify` | Registry management |
| `memory` | `show`, `clear` | Session state management |
| `graph` | `show`, `stats` | Company graph queries |
| `report` | `generate` | Report generation |
