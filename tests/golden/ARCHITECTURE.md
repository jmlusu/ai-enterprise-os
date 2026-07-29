# Architecture — Golden Test Inc

## System Architecture

Golden Test Inc is organized as a multi-agent enterprise operating under the
A company for golden file testing. vision.

## Core Layers

1. **Registry Layer** — YAML-based company configuration loaded into an
   immutable Pydantic registry.
2. **Generator Layer** — Jinja2 / multi-format template rendering pipeline
   with filesystem output.
3. **Validator Layer** — Multi-target validation engine (YAML, templates,
   manifest, generated output).
4. **CLI Layer** — Typer-based command interface with 4 subcommand groups.
5. **Agent Layer** — AI agent definitions for each executive, specialist,
   and department role.

## Data Flow

```
config/company/*.yaml → CompanyManifest
company/*.yaml → RegistryEngine → GeneratorContext
                                        ↓
                          GeneratorEngine / PromptGenerator / DocGenerator
                                        ↓
                                  generated/ (output)
```
