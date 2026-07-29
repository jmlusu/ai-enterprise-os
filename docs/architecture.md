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

## Registry Engine

The Registry Engine is the system's single source of truth. It loads YAML
files from `company/`, parses them, validates against Pydantic schemas,
resolves cross-references, and returns an immutable `CompanyRegistry`.

### Modules

| Module | Responsibility |
|---|---|
| `models/company.py` | Pydantic models: `VisionData`, `Role`, `DepartmentData`, `BoardEntry`, `ExecutiveEntry`, `PolicyEntry`, `SpecialistEntry`, `WorkflowEntry`, `CompanyRegistry` |
| `registry/loader.py` | Reads YAML files from `company/` directory |
| `registry/parser.py` | Converts raw YAML dicts into structured intermediate dicts |
| `registry/validator.py` | Validates parsed data against Pydantic schemas, collects all errors |
| `registry/resolver.py` | Cross-references department names from `company.yaml` with definitions in `departments.yaml` |
| `registry/registry.py` | Orchestrator (`RegistryEngine`) — calls loader → parser → validator → resolver, returns frozen `CompanyRegistry` |

### Pipeline

```
YAML files → Loader → Parser → Validator → Resolver → CompanyRegistry (frozen)
```

The `RegistryEngine` is a singleton. Call `load()` with a path to the company
directory. The returned `CompanyRegistry` has `frozen=True`, making it immutable.

## CLI Command Groups

| Group | Commands | Purpose |
|---|---|---|
| _root_ | `bootstrap`, `build`, `generate`, `validate`, `doctor`, `targets`, `status` | Core operations |
| `registry` | `list`, `show`, `verify` | Registry management |
| `memory` | `show`, `clear` | Session state management |
| `graph` | `show`, `stats` | Company graph queries |
| `report` | `generate` | Report generation |
