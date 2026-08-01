# AI Enterprise OS — Opencode Prompts Guide

How to use, extend, and operate the AI Enterprise OS through Opencode
prompt sessions. This guide covers only the prompt-based workflow; CLI
commands are not included.

---

## 1. Prompt-Based Workflow Overview

The AI Enterprise OS uses a **prompt dispatch system**: each generation phase
corresponds to a Markdown prompt file in `prompts/opencode/`. When you run
a phase, the system:

1. Loads the prompt file
2. Renders it with company context (via the template engine)
3. Writes the rendered prompt to `.ai-company/.tmp_rendered_prompt.md`
4. Invokes `opencode run --file <rendered> --agent <agent> --model <model>`
5. Streams the agent's output to your terminal

This lets you treat the OS as a set of repeatable, versioned prompt
sessions — ideal for Opencode-native development.

---

## 2. Built-in Prompt Files

| File | Phase | Agent | Model |
|---|---|---|---|
| `01_bootstrap_generator.md` | `bootstrap` | architect | opencode/north-mini-code-free |
| `02_registry_engine.md` | `registry` | architect | opencode/north-mini-code-free |
| `03_company_generator.md` | `company` | architect | opencode/north-mini-code-free |
| `04_board_generator.md` | `board` | architect | opencode/north-mini-code-free |
| `05_executive_generator.md` | `exec` | architect | opencode/north-mini-code-free |
| `06_department_generator.md` | `dept` | architect | opencode/north-mini-code-free |
| `07_specialist_generator.md` | `specialist` | architect | opencode/north-mini-code-free |
| `08_workflow_generator.md` | `workflow` | architect | opencode/north-mini-code-free |
| `09_prompt_generator.md` | `prompt` | architect | opencode/north-mini-code-free |
| `10_docs_generator.md` | `docs` | architect | opencode/north-mini-code-free |
| `11_graph_export.md` | `graph` | architect | opencode/north-mini-code-free |
| `08_constitution_loader.md` | (session start) | — | — |

The mapping lives in `src/ai_company/cli/command_map.yaml`. Edit it to
change the agent or model per phase.

---

## 3. Constitution Loader (`08_constitution_loader.md`)

Every Opencode session should begin by reading this prompt. It instructs
the agent to:

**Before any implementation:**
- Load `.ai-company/constitution` — the project's architectural
  constitution
- Load `.ai-company/state` — current sprint, milestone, architecture
  status, technical debt, next actions, project health
- Only then begin work

**At session end:**
- Update `.ai-company/state/`
- Update dashboard
- Update changelog
- Update sprint
- Update technical debt
- Update release notes

This is your **session contract**. Keep `.ai-company/state/` current as
part of every Opencode session. The constitution lives in
`.ai-company/constitution/` (create it if missing).

---

## 4. Prompt Template Rendering

Prompts are rendered through the **Template Engine** before dispatch. The
context passed to every prompt includes:

```python
{
    "company": {
        "name": manifest.name,
        "company_name": manifest.company_name or "",
        "description": manifest.description or "",
        "departments": [d.name for d in manifest.departments],
    }
}
```

The manifest is loaded from `config/company/company.yaml`.

### 4.1 Template Syntax

The engine supports multiple formats; prompts use **Jinja2** (`fmt="jinja"`).
Use standard Jinja2 syntax:

```
Company: {{ company.name }}
Description: {{ company.description }}

{% for dept in company.departments %}
- {{ dept }}
{% endfor %}
```

### 4.2 Custom Context

To add custom context variables, modify `src/ai_company/cli/render.py`:
it builds the `context` dict and calls `Renderer().render(raw, context,
fmt="jinja")`.

---

## 5. Agents

Custom agents are defined in `.opencode/agents/`:

| Agent | File | Role |
|---|---|---|
| `architect` | `architect.md` | Chief Architect — designs robust, scalable architectures |
| `builder` | `builder.md` | Lead Builder — writes production-ready, executable Python |

### 5.1 Agent Definition

Each agent file is a Markdown file with frontmatter:

```markdown
---
name: architect
description: The Chief Architect for Lightspeed Limited. Plans system design and scaffolding.
---
You are the Chief Architect. Your goal is to design robust, scalable Python architectures.
```

The `name` must match the `agent` field in `command_map.yaml`. The body
after `---` is the system prompt given to the LLM.

### 5.2 Model Assignment

Models are assigned per phase in `command_map.yaml` (e.g.
`opencode/north-mini-code-free`). The agents' default models in
`opencode.json` are for *interactive* Opencode sessions; generation phases
override via the command map.

---

## 6. Running a Prompt Phase

```powershell
# Dispatch a phase to Opencode
ai-company generate company

# Dry run — shows the rendered prompt and opencode command without executing
ai-company generate company --dry-run
```

The rendered prompt is always written to
`.ai-company/.tmp_rendered_prompt.md` — you can inspect it before/after
runs.

---

## 7. Writing Custom Prompts

### 7.1 Add a New Prompt File

Create `prompts/opencode/12_my_custom_phase.md` with Jinja2 template
content.

### 7.2 Register the Target

Add an entry to `src/ai_company/cli/command_map.yaml`:

```yaml
my_custom:
  prompt_file: prompts/opencode/12_my_custom_phase.md
  agent: architect
  model: opencode/north-mini-code-free
  description: Generate my custom artifacts
```

### 7.3 Run It

```powershell
ai-company generate my_custom
```

---

## 8. Prompt Library (Generated)

The `prompt` phase (`09_prompt_generator.md`) generates a **prompt
library** under `generated/prompts/` — one Markdown file per executable
prompt. These are standalone prompts you can run directly with Opencode
without the CLI:

```powershell
opencode run --file generated/prompts/03_company_generator.md
```

They are pre-rendered with the current company context at generation time.

---

## 9. Session Workflow Best Practices

1. **Start every session** by having the agent read
   `.ai-company/constitution` and `.ai-company/state/`
2. **Work in phases** — run one `generate` target at a time, inspect
   output, then proceed
3. **Update state at end** — explicitly write to `.ai-company/state/`:
   sprint status, technical debt changes, next actions
4. **Regenerate prompt library** after major registry changes:
   `ai-company generate prompt`
5. **Use dry-run** to preview prompts before dispatching
6. **Version prompts** — they live in git; changes are tracked

---

## 10. Directory Reference

| Path | Purpose |
|---|---|
| `prompts/opencode/` | Source prompt templates (versioned) |
| `.ai-company/constitution/` | Project constitution (architecture principles, constraints) |
| `.ai-company/state/` | Session state (sprint, milestone, debt, health) |
| `.ai-company/.tmp_rendered_prompt.md` | Last rendered prompt (ephemeral) |
| `.opencode/agents/` | Agent definitions (architect, builder) |
| `generated/prompts/` | Pre-rendered prompt library (after `generate prompt`) |
| `src/ai_company/cli/command_map.yaml` | Phase → prompt/agent/model mapping |
| `config/company/company.yaml` | Manifest used for prompt rendering context |

---

## 11. Troubleshooting Prompts

| Issue | Fix |
|---|---|
| Prompt renders with empty company fields | Ensure `config/company/company.yaml` exists and has `name`, `company_name`, `description`, `departments` |
| `opencode` not found | Install Opencode; verify `which opencode` works |
| Model errors | Check model id in `command_map.yaml`; ensure Ollama/remote provider has the model |
| Agent not found | Check `.opencode/agents/<agent>.md` exists and `name:` matches `command_map.yaml` |
| Template syntax error | Validate Jinja2 in the prompt file; test with `generate --dry-run` |

---

## 12. Extending the System

- **New phase** → add prompt + register in `command_map.yaml`
- **New agent** → add `.opencode/agents/<name>.md` + reference in `command_map.yaml`
- **Different model per phase** → change `model` in `command_map.yaml`
- **Extra template variables** → modify `render_prompt()` in `src/ai_company/cli/render.py`
- **Add constitution docs** → write Markdown files in `.ai-company/constitution/`

The prompt system is deliberately minimal: prompt files + a mapping table +
a renderer. All extensibility happens by editing those three pieces.
