from pathlib import Path

from ai_company.generator.context import GeneratorContext
from ai_company.template_engine import Renderer


class FilesystemWriter:
    """Writes rendered content to the filesystem, creating parent directories."""

    def write(self, content: str, destination: Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        return destination

    def ensure_dir(self, path: Path) -> Path:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        return path


class PromptGenerator:
    """Generates detailed agent prompts for every executive, specialist,
    and department from templates and the GeneratorContext."""

    EXECUTIVE_TEMPLATE = """# {name} — Executive Agent Prompt

You are **{name}**, *{title}* of **{company}**.

---

## Bio
{bio}

---

## Department
{department}

---

## Responsibilities
{responsibilities}

---

## KPIs (owned by you)
{kpis}

---

## Budget
{budget_table}

---

## Direct Reports
{direct_reports}

## Reports To
{reports_to}

---

## Active Strategy
{strategy}

## Culture & Values
{culture}

---

## Your Agent Configuration
- **Model:** {agent_model}
- **Temperature:** {agent_temperature}
- **Tools:** {agent_tools}

## Department Scope
{department_scope}

---

## Operating Mode
You operate autonomously within your defined authority. Escalate to the board
for decisions exceeding budget or scope boundaries as defined in governance
policies. Use the tools available to you to execute on your responsibilities
and track your KPIs.
"""

    SPECIALIST_TEMPLATE = """# {name} — Specialist Prompt

You are {name}, {expertise} specialist at {company}.

## Context
{vision}

## Expertise Area
{expertise}

## Projects & Tasks
- Apply deep expertise to solve complex problems
- Collaborate with departments on domain-specific challenges
- Maintain state-of-the-art knowledge in {expertise}
- Document findings and contribute to knowledge base

## Tools Available
{tools}

## Operating Mode
You are a subject matter expert. Provide recommendations, implement solutions,
and escalate when issues fall outside your domain.
"""

    DEPARTMENT_TEMPLATE = """# {department} Department — Agent Prompt

You represent the {department_display} department at {company}.

## Mission
{department_description}

## Roles
{roles}

## Responsibilities
- Execute on departmental goals aligned with company strategy
- Collaborate with other departments on cross-functional initiatives
- Track KPIs and report progress

## Active Objectives
{strategy_objectives}

## Operating Mode
Operate within your departmental scope. Coordinate with executives for
strategic decisions and specialists for domain-specific challenges.
"""

    def __init__(self, context: GeneratorContext) -> None:
        self.context = context
        self.writer = FilesystemWriter()
        self.renderer = Renderer()

    def generate_all(self, output_dir: Path | None = None) -> list[Path]:
        base = output_dir or self.context.output_dir / "prompts"
        created: list[Path] = []
        reg = self.context.registry
        if reg is None:
            return created

        for exec_entry in reg.executives:
            if exec_entry.name:
                content = self.generate_executive_prompt(exec_entry.name)
                path = self.writer.write(
                    content,
                    base
                    / "executive"
                    / f"{exec_entry.name.lower().replace(' ', '_')}.md",
                )
                created.append(path)

        for spec_entry in reg.specialists:
            if spec_entry.name:
                content = self.generate_specialist_prompt(spec_entry.name)
                path = self.writer.write(
                    content,
                    base
                    / "specialist"
                    / f"{spec_entry.name.lower().replace(' ', '_')}.md",
                )
                created.append(path)

        for dept in self.context.manifest.departments:
            content = self.generate_department_prompt(dept.name)
            path = self.writer.write(content, base / dept.name / "prompt.md")
            created.append(path)

        return created

    def generate_executive_prompt(self, executive_name: str) -> str:
        ctx = self.context
        reg = ctx.registry
        if reg is None:
            return f"# {executive_name} — Executive\n\nRegistry not available.\n"
        entry = None
        for e in reg.executives:
            if e.name and e.name.lower() == executive_name.lower():
                entry = e
                break
        if entry is None:
            return f"# {executive_name} — Executive\n\nExecutive record not found.\n"

        # Responsibilities
        responsibilities = (
            "\n".join(f"- {r}" for r in entry.responsibilities)
            or "No specific responsibilities defined."
        )

        # Per-executive KPIs (filter registry KPIs by owner match)
        exec_kpis = [
            k
            for k in reg.kpis
            if k.owner
            and (
                k.owner.lower() in (entry.title or "").lower()
                or k.owner.lower() in (entry.name or "").lower()
            )
        ]
        if not exec_kpis:
            # Fallback: show KPIs from the entry's kpi list
            exec_kpis_from_names = [k for k in reg.kpis if k.name in (entry.kpis or [])]
            if exec_kpis_from_names:
                exec_kpis = exec_kpis_from_names
        if exec_kpis:
            kpi_lines = []
            for k in exec_kpis:
                direction = {"up": "↑", "down": "↓", "flat": "→"}.get(k.trend, "→")
                kpi_lines.append(
                    f"- **{k.name}**: {k.current}{k.unit} (target: {k.target}{k.unit}) {direction}"
                )
            kpis_str = "\n".join(kpi_lines)
        elif entry.kpis:
            kpis_str = "\n".join(f"- **{k}**" for k in entry.kpis)
        else:
            kpis_str = "No KPIs assigned."

        # Budget — find budget matching this exec's department or name
        budget_lines: list[str] = []
        exec_dept = entry.department or ""
        for b in reg.budgets:
            if b.department == exec_dept or b.department.lower() == exec_dept.lower():
                pct = (b.spent / b.total * 100) if b.total > 0 else 0
                budget_lines.append(
                    f"- **{b.department}**: {b.currency} {b.total:,.0f} total, "
                    f"{b.spent:,.0f} spent ({pct:.0f}%)"
                )
        if entry.budget_authority > 0 and not budget_lines:
            budget_lines.append(
                f"- **Budget Authority**: ${entry.budget_authority:,.0f}"
            )
        if not budget_lines:
            budget_lines.append("No budget data available.")
        budget_table = "\n".join(budget_lines)

        # Direct reports
        direct_reports = (
            "\n".join(f"- {r}" for r in entry.direct_reports) or "No direct reports."
        )

        # Reports to
        reports_to = entry.reports_to or "Board of Directors"

        # Department scope from agent config
        department_scope = (
            "\n".join(f"- {d}" for d in entry.agent_config.department_scope)
            or "No department scope defined."
        )

        # Agent config
        agent_tools = ", ".join(entry.agent_config.tools) or "Standard tools"
        agent_model = entry.agent_config.model or "gpt-4o"

        # Culture
        culture_vals = reg.culture.values or []
        culture_str = (
            "\n".join(f"- {v}" for v in culture_vals)
            if culture_vals
            else "No culture values defined."
        )

        return self.EXECUTIVE_TEMPLATE.format(
            name=entry.name or executive_name,
            title=entry.title or "Executive",
            company=ctx.manifest.company_name or ctx.manifest.name,
            bio=entry.bio or "No biography available.",
            department=exec_dept or "General",
            responsibilities=responsibilities,
            kpis=kpis_str,
            budget_table=budget_table,
            direct_reports=direct_reports,
            reports_to=reports_to,
            strategy=reg.strategy.description or "No active strategy defined.",
            culture=culture_str,
            agent_model=agent_model,
            agent_temperature=str(entry.agent_config.temperature),
            agent_tools=agent_tools,
            department_scope=department_scope,
        )

    def generate_specialist_prompt(self, specialist_name: str) -> str:
        ctx = self.context
        reg = ctx.registry
        if reg is None:
            return f"# {specialist_name} — Specialist\n\nRegistry not available.\n"
        entry = None
        for s in reg.specialists:
            if s.name and s.name.lower() == specialist_name.lower():
                entry = s
                break
        if entry is None:
            return f"# {specialist_name} — Specialist\n\nSpecialist record not found.\n"

        tool_names = ", ".join(t.name for t in reg.tools) or "Standard toolset"

        return self.SPECIALIST_TEMPLATE.format(
            name=entry.name or specialist_name,
            expertise=entry.expertise or "General",
            company=ctx.manifest.company_name or ctx.manifest.name,
            vision=ctx.manifest.description or "",
            tools=tool_names,
        )

    def generate_department_prompt(self, department_name: str) -> str:
        ctx = self.context
        reg = ctx.registry
        if reg is None:
            return f"# {department_name} — Department\n\nRegistry not available.\n"
        dept_data = reg.departments.get(department_name)
        if dept_data is None:
            return f"# {department_name} — Department\n\nDepartment not found.\n"

        roles_str = "\n".join(f"- {r.title}: {r.description}" for r in dept_data.roles)
        strategy_objectives = (
            "\n".join(f"- {o}" for o in reg.strategy.objectives)
            or "No objectives defined."
        )

        return self.DEPARTMENT_TEMPLATE.format(
            department=department_name,
            department_display=department_name.replace("_", " ").title(),
            company=ctx.manifest.company_name or ctx.manifest.name,
            department_description=next(
                (
                    d.description
                    for d in ctx.manifest.departments
                    if d.name == department_name
                ),
                "",
            ),
            roles=roles_str or "No roles defined",
            strategy_objectives=strategy_objectives,
        )
