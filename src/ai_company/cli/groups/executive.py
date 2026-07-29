"""CLI commands for the executive team — list, show, org-chart, agent."""

from pathlib import Path

import typer

from ai_company.generator.prompt_generator import PromptGenerator
from ai_company.models.company import CompanyManifest, CompanyRegistry
from ai_company.registry.registry import RegistryEngine
from ai_company.utils.console import console_print

app = typer.Typer(help="Executive team commands — list, show, org-chart, agent")


def _load_registry() -> tuple[CompanyRegistry, CompanyManifest]:
    """Load the registry and return (registry, manifest)."""
    engine = RegistryEngine()
    result = engine.load(Path("company"), config_dir=Path("config/company"))
    if result.registry is None or not result.success:
        for err in result.errors:
            console_print(f"  [red]✗[/red] {err}")
        raise typer.Exit(1)
    reg = result.registry
    # Build a minimal manifest
    manifest = CompanyManifest(
        name=reg.vision.company_name or reg.vision.name,
        company_name=reg.vision.company_name or reg.vision.name,
        description=reg.vision.description or "",
    )
    return reg, manifest


@app.command()
def list() -> None:
    """List all executives with their titles and status."""
    reg, _manifest = _load_registry()
    console_print("[cyan]Executive Team:[/cyan]\n")
    for ex in reg.executives:
        if not ex.name:
            continue
        status_icon = {
            "active": "[green]●[/green]",
            "interim": "[yellow]●[/yellow]",
            "on_leave": "[red]●[/red]",
        }.get(ex.status or "active", "[green]●[/green]")
        console_print(f"  {status_icon} [bold]{ex.name}[/bold] — {ex.title or 'N/A'}")
        if ex.department:
            console_print(f"      Department: {ex.department}")
        if ex.kpis:
            console_print(f"      KPIs: {', '.join(ex.kpis)}")
        console_print("")


@app.command()
def show(
    name: str = typer.Argument(..., help="Executive name to show details for"),
) -> None:
    """Show detailed profile for a specific executive."""
    reg, _manifest = _load_registry()

    ex = None
    for e in reg.executives:
        if e.name and e.name.lower() == name.lower():
            ex = e
            break

    if ex is None:
        console_print(f"[red]Executive '{name}' not found.[/red]")
        raise typer.Exit(1)

    ac = ex.agent_config

    console_print(f"[cyan]Executive Profile:[/cyan] [bold]{ex.name}[/bold]\n")
    console_print(f"  [bold]Title:[/bold] {ex.title or 'N/A'}")
    console_print(f"  [bold]Department:[/bold] {ex.department or 'N/A'}")
    console_print(f"  [bold]Status:[/bold] {ex.status or 'active'}")
    console_print(f"  [bold]Reports To:[/bold] {ex.reports_to or 'Board of Directors'}")
    console_print(f"  [bold]Start Date:[/bold] {ex.start_date or 'N/A'}")
    console_print(f"  [bold]Email:[/bold] {ex.email or 'N/A'}")

    if ex.bio:
        console_print(f"\n  [bold]Bio:[/bold]\n    {ex.bio}")

    if ex.responsibilities:
        console_print("\n  [bold]Responsibilities:[/bold]")
        for r in ex.responsibilities:
            console_print(f"    - {r}")

    # Per-executive KPIs
    exec_kpis = [
        k
        for k in reg.kpis
        if k.owner
        and (
            k.owner.lower() in (ex.title or "").lower()
            or k.owner.lower() in (ex.name or "").lower()
        )
    ]
    if not exec_kpis:
        exec_kpis = [k for k in reg.kpis if k.name in (ex.kpis or [])]
    if exec_kpis:
        console_print("\n  [bold]KPIs:[/bold]")
        for k in exec_kpis:
            direction = {"up": "↑", "down": "↓", "flat": "→"}.get(k.trend, "→")
            console_print(
                f"    - {k.name}: {k.current}{k.unit} / {k.target}{k.unit} {direction}"
            )

    # Budget
    dept = ex.department or ""
    found_budget = False
    for b in reg.budgets:
        if b.department == dept or b.department.lower() == dept.lower():
            pct = (b.spent / b.total * 100) if b.total > 0 else 0
            console_print(f"\n  [bold]Budget ({b.department}):[/bold]")
            console_print(f"    Total: {b.currency} {b.total:,.0f}")
            console_print(f"    Spent: {b.currency} {b.spent:,.0f} ({pct:.0f}%)")
            found_budget = True
            break
    if not found_budget and ex.budget_authority > 0:
        console_print("\n  [bold]Budget Authority:[/bold]")
        console_print(f"    ${ex.budget_authority:,.0f}")

    if ex.direct_reports:
        console_print("\n  [bold]Direct Reports:[/bold]")
        for r in ex.direct_reports:
            console_print(f"    - {r}")

    console_print("\n  [bold]Agent Configuration:[/bold]")
    console_print(f"    Model: {ac.model}")
    console_print(f"    Temperature: {ac.temperature}")
    console_print(f"    Tools: {', '.join(ac.tools)}")
    if ac.department_scope:
        console_print(f"    Department Scope: {', '.join(ac.department_scope)}")


@app.command()
def org_chart() -> None:
    """Generate a Mermaid org chart of the executive team."""
    reg, _manifest = _load_registry()

    lines = ["```mermaid", "graph TD", ""]
    # Board → CEO
    lines.append("    Board[Board of Directors] --> CEO")
    lines.append("")

    ceo_name = ""
    ceo_title = "CEO"
    for ex in reg.executives:
        if ex.name and "ceo" in (ex.title or "").lower():
            ceo_name = ex.name
            ceo_title = ex.title or "CEO"
            lines.append(f"    CEO[{ceo_name} - {ceo_title}]")
            break

    if not ceo_name:
        # Fallback: first executive is assumed CEO
        if reg.executives and reg.executives[0].name:
            ceo_name = reg.executives[0].name
            ceo_title = reg.executives[0].title or "CEO"
            lines.append(f'    CEO["{ceo_name} - {ceo_title}"]')
        else:
            lines.append('    CEO["Chief Executive Officer"]')

    # Map executives to their reports_to
    for ex in reg.executives:
        if not ex.name:
            continue
        if "ceo" in (ex.title or "").lower():
            continue
        safe_name = ex.name.replace(" ", "_").replace(".", "")
        manager = "CEO"
        if ex.reports_to:
            # Find matching executive
            for e2 in reg.executives:
                if e2.name and e2.name.lower() in ex.reports_to.lower():
                    manager = e2.name.replace(" ", "_").replace(".", "")
                    break
        lines.append(f'    {manager} --> {safe_name}["{ex.name} - {ex.title}"]')

    lines.append("")
    lines.append("```")

    chart = "\n".join(lines)
    console_print(chart)

    # Write to file
    org_dir = Path("generated")
    org_dir.mkdir(parents=True, exist_ok=True)
    chart_path = org_dir / "org_chart.md"
    chart_path.write_text(chart, encoding="utf-8")
    console_print(f"\n[green]Org chart written to {chart_path}[/green]")


@app.command()
def agent(
    name: str = typer.Argument(..., help="Executive name to generate agent prompt for"),
) -> None:
    """Generate and display the full agent prompt for an executive."""
    reg, manifest = _load_registry()

    from ai_company.generator.context import GeneratorContext

    ctx = GeneratorContext(manifest, reg)
    gen = PromptGenerator(ctx)
    prompt = gen.generate_executive_prompt(name)

    if "not found" in prompt.lower():
        console_print(f"[red]Executive '{name}' not found.[/red]")
        console_print("[yellow]Available: [/yellow]")
        for ex in reg.executives:
            if ex.name:
                console_print(f"  - {ex.name}")
        raise typer.Exit(1)

    # Print the prompt
    from ai_company.utils.console import console_print_plain

    console_print_plain(prompt)
