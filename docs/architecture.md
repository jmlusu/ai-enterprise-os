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

## Company Manifest

The Company Manifest (`config/company/company.yaml`) is the authoritative
definition of the company identity and department structure. It is loaded,
validated, and normalized before being passed into the Registry Engine.

### Manifest Model

| Model | Fields |
|---|---|
| `ManifestDepartment` | `name`, `display_name`, `description` |
| `CompanyManifest` | `name`, `description`, `company_name`, `version`, `departments` |

The `CompanyManifest` class provides:
- **`load(path)`** — reads and validates the YAML file, raising on missing/empty/invalid files
- **`validate_manifest()`** — runs business-rule checks (non-empty name, unique departments)
- **`normalize()`** — returns a cleaned copy (trimmed whitespace, lowered names, filled defaults)

## Registry Engine

The Registry Engine is the system's single source of truth. It loads YAML
files from `company/`, parses them, validates against Pydantic schemas,
resolves cross-references, accepts an optional `CompanyManifest` for
cross-validation, and returns an immutable `CompanyRegistry`.

### Modules

| Module | Responsibility |
|---|---|
| `models/company.py` | Pydantic models: `VisionData`, `Role`, `DepartmentData`, `BoardEntry`, `ExecutiveEntry`, `PolicyEntry`, `SpecialistEntry`, `WorkflowEntry`, `CompanyRegistry`, `ManifestDepartment`, `CompanyManifest` |
| `registry/loader.py` | Reads YAML files from `company/` directory |
| `registry/parser.py` | Converts raw YAML dicts into structured intermediate dicts |
| `registry/validator.py` | Validates parsed data against Pydantic schemas, collects all errors |
| `registry/resolver.py` | Cross-references department names from `company.yaml` with definitions in `departments.yaml` |
| `registry/registry.py` | Orchestrator (`RegistryEngine`) — accepts optional `CompanyManifest`, calls loader → parser → validator → resolver, returns frozen `CompanyRegistry` |

### Pipeline

```
config/company/company.yaml → CompanyManifest (load → validate → normalize)
                                                                   ↓
company/*.yaml → Loader → Parser → Validator → Resolver → CompanyRegistry (frozen)
```

The `RegistryEngine` is a singleton. Call `load()` with a path to the company
directory and an optional `manifest` parameter. The returned `RegistryLoadResult`
includes the manifest reference. The `CompanyRegistry` has `frozen=True`, making
it immutable.

## CLI Command Groups

| Group | Commands | Purpose |
|---|---|---|
| _root_ | `bootstrap`, `build`, `generate`, `validate`, `doctor`, `targets`, `status` | Core operations |
| `registry` | `list`, `show`, `verify` | Registry management |
| `memory` | `show`, `clear` | Session state management |
| `graph` | `show`, `stats` | Company graph queries |
| `report` | `generate` | Report generation |
