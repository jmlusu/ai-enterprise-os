# Agent Roles & Persona Catalog

> **Purpose:** Complete reference for every agent persona in the AI Enterprise OS —
> executives, specialists, and board members. Maps each role to its slug,
> department, Opencode agent file, and sync behavior. This is the single
> source of truth for "who is who" in the system.

## Sync Mechanism

Agents are synchronized from YAML source files to the Opencode agent
directory by running:

```bash
# From repo root
python -m ai_company.agents sync
```

This command:
1. Reads `company/executives.yaml`, `company/specialists.yaml`, `company/board.yaml`
2. Generates deterministic slugs via `AgentSlugIndex` (collision detection included)
3. Renders Jinja2 templates (`templates/opencode/agents/` render path; prompts built in `agents/template.py`)
4. Writes `.md` files to the sync directory (`--scope` flag: `project` | `global` | `both`; default `global`)
5. **Omits `model` frontmatter** — Opencode inherits the active model of the invoking agent
6. Prints a summary table (created / updated / unchanged)

**Important:** The sync is a standalone `argparse` entry point — NOT part of the
frozen Typer CLI tree. It is not invokable as `ai-company agents sync`.

## Slug Rules (`agents/slug_map.py`)

- **Executives** use an explicit title → slug table (titles are too long for
  @-mention ergonomics): `ceo`, `cto`, `cfo`, `coo`, `cmo`, `caio`, `chro`,
  `clo`, `ciso`, `cio`, `cdo`, `cso`, `chief-of-staff`. Final slug =
  `<exec-slug>-<name>` (e.g. `ceo-jack-mlusu`).
- **Specialists & board** are slugified from their expertise/role + name.
- **Built-in agent names can never be shadowed:** `build`, `plan`, `explore`,
  `general`, `architect`, `builder`, `compaction`, `title`, `summary`.
- Collisions get a deterministic numeric suffix.

---

## Executive Agents (13)

| # | Role | Name | Slug | Department | Focus |
|---|---|---|---|---|---|
| 1 | **CEO** | Jack Mlusu | `ceo-jack-mlusu` | Office of the CEO | Vision, strategy, governance, board liaison |
| 2 | **CTO** | Maria Santos | `cto-maria-santos` | Technology | Technical architecture, engineering, platform |
| 3 | **CFO** | Robert Kim | `cfo-robert-kim` | Finance | Financial planning, budgeting, fiscal strategy |
| 4 | **COO** | Priya Patel | `coo-priya-patel` | Operations | Operational execution, process optimization, scaling |
| 5 | **CMO** | Jordan Blake | `cmo-jordan-blake` | Marketing | Brand, marketing, go-to-market strategy |
| 6 | **CAIO** | Dr. Wei Chen | `caio-wei-chen` | AI Research | AI research, model strategy, responsible AI |
| 7 | **CHRO** | Samantha Rivers | `chro-samantha-rivers` | People | Talent, culture, people operations |
| 8 | **CIO** | Daniel Brooks | `cio-daniel-brooks` | IT | Enterprise IT strategy, internal technology |
| 9 | **CISO** | Elena Vasquez | `ciso-elena-vasquez` | Security | Security strategy, risk, incident response |
| 10 | **CLO** | Marcus Johnson | `clo-marcus-johnson` | Legal | Legal, compliance, governance |
| 11 | **CDO** | Dr. Amara Osei | `cdo-amara-osei` | Data | Data strategy, pipelines, analytics |
| 12 | **CSO** | Victoria Chen | `cso-victoria-chen` | Strategy | Corporate strategy, market analysis, M&A |
| 13 | **Chief of Staff** | Grace Liu | `chief-of-staff-grace-liu` | Office of the CEO | Executive office operations, cross-functional coordination |

---

## Specialist Agents (17)

| # | Role | Name | Slug | Department | Focus |
|---|---|---|---|---|---|
| 1 | **NLP** | Dr. Nina Voss | `nlp-nina-voss` | AI Research | Natural Language Processing |
| 2 | **Reinforcement Learning** | Kenji Tanaka | `reinforcement-learning-kenji-tanaka` | AI Research | Reinforcement Learning |
| 3 | **Cybersecurity Architecture** | Olivia Foster | `cybersecurity-architecture-olivia-foster` | Security | Cybersecurity Architecture |
| 4 | **Distributed Systems** | Samuel Abebe | `distributed-systems-samuel-abebe` | Engineering | Distributed Systems |
| 5 | **UX Research & Human Factors** | Lena Karlsson | `ux-research-human-factors-lena-karlsson` | Design | UX Research & Human Factors |
| 6 | **Computer Vision** | Wei Zhang | `computer-vision-wei-zhang` | AI Research | Computer Vision |
| 7 | **Software Engineering** | Ethan Cole | `software-engineering-ethan-cole` | Engineering | Software Engineering |
| 8 | **Data Engineering** | Maya Patel | `data-engineering-maya-patel` | Data | Data Engineering |
| 9 | **DevOps Engineering** | Sofia Marino | `devops-engineering-sofia-marino` | Operations | DevOps Engineering |
| 10 | **Cloud Architecture** | James Okonkwo | `cloud-architecture-james-okonkwo` | Technology | Cloud Architecture |
| 11 | **Financial Analysis** | Aisha Rahman | `financial-analysis-aisha-rahman` | Finance | Financial Analysis |
| 12 | **Business Analysis** | Tom Becker | `business-analysis-tom-becker` | Operations | Business Analysis |
| 13 | **Content Strategy** | Rachel Nguyen | `content-strategy-rachel-nguyen` | Marketing | Content Strategy |
| 14 | **Growth Marketing** | Diego Ramirez | `growth-marketing-diego-ramirez` | Marketing | Growth Marketing |
| 15 | **Sales Operations** | Hannah Weiss | `sales-operations-hannah-weiss` | Operations | Sales Operations |
| 16 | **Legal & Compliance** | Liam O'Connor | `legal-compliance-liam-oconnor` | Legal | Legal & Compliance |
| 17 | **Customer Success** | Zoe Martin | `customer-success-zoe-martin` | Operations | Customer Success |

---

## Board Agents (5)

| # | Role | Name | Slug | Focus |
|---|---|---|---|---|
| 1 | **Chairperson** | Sarah Chen | `chairperson-sarah-chen` | Board oversight, governance, CEO accountability |
| 2 | **Vice Chair** | James Mitchell | `vice-chair-james-mitchell` | Board oversight, governance, succession planning |
| 3 | **Independent Director** | Elena Rodriguez | `independent-director-elena-rodriguez` | Independent oversight, audit committee |
| 4 | **Non-Executive Director** | David Park | `non-executive-director-david-park` | Strategic oversight, compensation committee |
| 5 | **Non-Executive Director** | Amara Okafor | `non-executive-director-amara-okafor` | Strategic oversight, risk committee |

---

## Non-Persona Agents (Project-Level)

These live in `.opencode/agents/` (project scope), NOT in the global sync.
They are NOT generated from YAML — they are hand-authored and committed.

| Agent File | Role | Purpose |
|---|---|---|
| `.opencode/agents/architect.md` | **Chief Architect** | Design robust, scalable Python architectures; guardrails on architecture changes |
| `.opencode/agents/builder.md` | **Lead Builder** | Write production-ready Python code |

**Why not in global sync?** These are project-specific operational agents,
not company personas. They have different tool permissions and mandates.

---

## Invoking Agents

In Opencode, agents are invoked by their slug:

```text
> @ceo-jack-mlusu What's our Q3 strategy?
> @cto-maria-santos Review this architecture proposal
> @nlp-nina-voss Help me design this prompt pipeline
```

The `@` prefix triggers the agent with its full prompt context.

---

## Updating Personas

1. Edit the source YAML in `company/`:
   - `company/executives.yaml`, `company/specialists.yaml`, `company/board.yaml`
2. Run `python -m ai_company.agents sync`
3. Verify output shows `updated` for changed entries
4. Test in Opencode: `@<slug> help` should reflect the new prompt

**Do not edit** `~/.config/opencode/agents/*.md` directly — changes will be
overwritten on next sync.

---

## Constitutional Compliance

All persona agents inherit these directives from
`.ai-company/constitution/rules.md`:

1. **Read State First** — read `.ai-company/state/current_sprint.yaml` before writing code.
2. **Pydantic v2** — for all data validation and schemas.
3. **No pseudo-code/placeholders** in production files.
4. **Strict typing** — standard `typing` everywhere.
5. **Update State Last** — update sprint state on completion.

Plus the agent-behavior norms in `.ai/coding-rules.md` §10: no fabrication,
evidence-based answers, no silent failures, single source of truth (`.ai/`).

---

## Related Files

- `company/executives.yaml`, `company/specialists.yaml`, `company/board.yaml` — persona source of truth
- `src/ai_company/agents/sync.py` — sync engine (`AgentSyncEngine`)
- `src/ai_company/agents/slug_map.py` — `AgentSlugIndex`, `EXECUTIVE_SLUGS`, `BUILTIN_AGENT_SLUGS`
- `src/ai_company/agents/template.py` — `render_agent_markdown`, `build_trigger`
- `.opencode/agents/architect.md`, `.opencode/agents/builder.md` — project agents
- `.ai-company/constitution/rules.md` — constitutional rules
