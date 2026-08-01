"""Sync company personas into opencode agent markdown files.

The engine mirrors the registry loading pattern used by the (frozen) CLI
group ``ai_company.cli.groups.executive``: ``RegistryEngine().load(...)``
followed by ``CompanyManifest`` construction from the vision data.

Persona agent files deliberately declare no ``model`` frontmatter: opencode
subagents without a model inherit the active model of the primary agent that
invoked them, so personas follow the globally selected model instead of being
pinned to one. Do not add a ``model`` line to the render template.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ai_company.agents.slug_map import AgentSlugIndex, AgentSlugItem
from ai_company.agents.template import (
    AgentRenderContext,
    build_trigger,
    render_agent_markdown,
)
from ai_company.models.company import (
    CompanyRegistry,
    ExecutiveEntry,
    SpecialistEntry,
)
from ai_company.registry.registry import RegistryEngine
from ai_company.utils.console import console_print

DEFAULT_PERSONA_TEMPERATURE = 0.2

Action = Literal["create", "update", "skip", "conflict"]

SyncScope = Literal["project", "global", "both"]

PROJECT_AGENTS_DIR = Path(".opencode/agents")


def global_agents_dir() -> Path:
    """Return the user-global opencode agents directory (resolved per call)."""
    return Path.home() / ".config" / "opencode" / "agents"


class AgentSyncConfig(BaseModel):
    """Runtime options for :class:`AgentSyncEngine`.

    ``scope`` controls where generated agent files are written so personas
    persist globally (available in every project) or stay project-local:

    - ``"project"`` — write to ``PROJECT_AGENTS_DIR`` (default, backward
      compatible with the original behavior)
    - ``"global"`` — write to the user-global opencode agents directory
      (``~/.config/opencode/agents``) so the agents are loaded by opencode
      from every working directory
    - ``"both"`` — write to both locations

    An explicit ``output_dir`` always wins over ``scope``.
    """

    dry_run: bool = False
    force: bool = False
    include_departments: bool = False
    scope: SyncScope = "project"
    output_dir: Path | None = None
    registry_dir: Path = Path("company")
    config_dir: Path = Path("config/company")

    def output_dirs(self) -> list[Path]:
        """Resolve the directories this config writes agent files to."""
        if self.output_dir is not None:
            return [self.output_dir]
        if self.scope == "project":
            return [PROJECT_AGENTS_DIR]
        if self.scope == "global":
            return [global_agents_dir()]
        return [PROJECT_AGENTS_DIR, global_agents_dir()]


class AgentPlanEntry(BaseModel):
    """One persona's planned sync outcome."""

    slug: str
    name: str
    title: str
    path: Path
    content: str
    action: Action


class AgentSyncPlan(BaseModel):
    """The full set of persona files that WOULD be written."""

    entries: list[AgentPlanEntry] = Field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        """Return action -> number of entries, in stable key order."""
        result: dict[str, int] = {}
        for action in ("create", "update", "skip", "conflict"):
            result[action] = sum(1 for e in self.entries if e.action == action)
        return result


class AgentSyncResult(BaseModel):
    """Outcome of a sync run, keyed by persona slug."""

    created: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class _PersonaSource(BaseModel):
    """Raw persona identity used for slug resolution."""

    name: str
    title: str
    role: str
    kind: Literal["executive", "specialist", "board"] = "executive"


def print_plan_summary(plan: AgentSyncPlan, *, dry_run: bool = False) -> None:
    """Print a readable summary of a plan (used for ``--dry-run``)."""
    counts = plan.counts
    total = len(plan.entries)
    mode = "Dry run — no files written." if dry_run else "Plan"
    console_print(f"[cyan]{mode}[/cyan]")
    console_print(
        f"[bold]{total} persona agent(s):[/bold] "
        f"{counts['create']} to create, {counts['update']} to update, "
        f"{counts['skip']} unchanged, {counts['conflict']} conflict(s)."
    )
    for entry in plan.entries:
        if entry.action == "conflict":
            console_print(
                f"  [yellow]conflict[/yellow] {entry.slug}.md — existing file "
                "differs; rerun with --force to overwrite"
            )
        elif entry.action in ("create", "update"):
            verb = {
                "create": "would create" if dry_run else "create",
                "update": "would update" if dry_run else "update",
            }[entry.action]
            console_print(f"  [yellow]{verb}[/yellow] {entry.slug}.md")


def print_result_summary(result: AgentSyncResult) -> None:
    """Print a readable summary of a completed sync run."""
    console_print(
        f"[green]Sync complete:[/green] {len(result.created)} created, "
        f"{len(result.updated)} updated, {len(result.skipped)} skipped, "
        f"{len(result.conflicts)} conflict(s), {len(result.errors)} error(s)."
    )
    for label, slugs in (
        ("Created", result.created),
        ("Updated", result.updated),
        ("Skipped", result.skipped),
        ("Conflicts", result.conflicts),
    ):
        if slugs:
            console_print(f"  [bold]{label}:[/bold]")
            for slug in slugs:
                console_print(f"    - {slug}.md")
    for error in result.errors:
        console_print(f"  [red]✗ {error}[/red]")


class AgentSyncEngine(BaseModel):
    """Plans and executes persona -> agent file synchronization."""

    config: AgentSyncConfig = Field(default_factory=AgentSyncConfig)

    def _load_registry(self) -> CompanyRegistry:
        """Load the company registry exactly like the frozen executive CLI."""
        engine = RegistryEngine()
        result = engine.load(
            self.config.registry_dir, config_dir=self.config.config_dir
        )
        if result.registry is None or not result.success:
            raise RuntimeError("Registry failed to load:\n" + "\n".join(result.errors))
        return result.registry

    def _persona_sources(self, reg: CompanyRegistry) -> list[_PersonaSource]:
        """Collect every Phase 1 persona in deterministic registry order."""
        sources: list[_PersonaSource] = []
        for ex in reg.executives:
            if not ex.name:
                continue
            sources.append(
                _PersonaSource(
                    name=ex.name,
                    title=ex.title or "Executive",
                    role="executive",
                    kind="executive",
                )
            )
        for sp in reg.specialists:
            if not sp.name:
                continue
            sources.append(
                _PersonaSource(
                    name=sp.name,
                    title=sp.expertise or "Specialist",
                    role=sp.department or "specialist",
                    kind="specialist",
                )
            )
        for bm in reg.board:
            if not bm.name:
                continue
            sources.append(
                _PersonaSource(
                    name=bm.name,
                    title=bm.role or "Director",
                    role="board",
                    kind="board",
                )
            )
        return sources

    def _render_contexts(self, reg: CompanyRegistry) -> list[AgentRenderContext]:
        """Build render contexts, validating slugs across all personas."""
        sources = self._persona_sources(reg)
        index = AgentSlugIndex(
            items=[
                AgentSlugItem(name=s.name, title=s.title, role=s.role) for s in sources
            ]
        )
        slugs = index.resolved_slugs()
        index.raise_for_collisions()

        exec_by_name = {ex.name: ex for ex in reg.executives if ex.name}
        spec_by_name = {sp.name: sp for sp in reg.specialists if sp.name}

        contexts: list[AgentRenderContext] = []
        for source, slug in zip(sources, slugs):
            if source.kind == "executive":
                contexts.append(self._executive_context(exec_by_name, source, slug))
            elif source.kind == "specialist":
                contexts.append(self._specialist_context(spec_by_name, source, slug))
            else:
                contexts.append(self._board_context(source, slug))
        return contexts

    def _executive_context(
        self,
        by_name: dict[str, ExecutiveEntry],
        source: _PersonaSource,
        slug: str,
    ) -> AgentRenderContext:
        ex = by_name[source.name]
        ac = ex.agent_config
        return AgentRenderContext(
            slug=slug,
            name=source.name,
            title=source.title,
            trigger=build_trigger(kind="executive", slug=slug, title=source.title),
            temperature=ac.temperature,
            instructions=ac.instructions,
            kind="executive",
            bio=ex.bio,
            responsibilities=list(ex.responsibilities),
            kpis=list(ex.kpis),
            tools=list(ac.tools),
        )

    def _specialist_context(
        self,
        by_name: dict[str, SpecialistEntry],
        source: _PersonaSource,
        slug: str,
    ) -> AgentRenderContext:
        sp = by_name[source.name]
        return AgentRenderContext(
            slug=slug,
            name=source.name,
            title=source.title,
            trigger=build_trigger(kind="specialist", slug=slug, title=source.title),
            temperature=DEFAULT_PERSONA_TEMPERATURE,
            instructions=(
                f"As the company's {source.title} specialist, provide expert, "
                f"actionable guidance on {source.title} across the organization."
            ),
            kind="specialist",
            bio=sp.bio or "",
        )

    def _board_context(
        self,
        source: _PersonaSource,
        slug: str,
    ) -> AgentRenderContext:
        return AgentRenderContext(
            slug=slug,
            name=source.name,
            title=source.title,
            trigger=build_trigger(kind="board", slug=slug, title=source.title),
            temperature=DEFAULT_PERSONA_TEMPERATURE,
            instructions=(
                f"Provide independent board-level oversight and governance as "
                f"{source.title}, advising the executive team and representing "
                "shareholder interests."
            ),
            kind="board",
            bio="",
        )

    def _company_name(self, reg: CompanyRegistry) -> str:
        return reg.vision.company_name or reg.vision.name or "the company"

    def _action_for(self, path: Path, content: str) -> Action:
        """Decide create/update/skip/conflict for one existing-or-new file."""
        if not path.exists():
            return "create"
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            return "conflict"
        if existing == content:
            return "skip"
        return "update" if self.config.force else "conflict"

    def plan(self) -> AgentSyncPlan:
        """Compute what WOULD happen without writing anything."""
        if self.config.include_departments:
            raise NotImplementedError(
                "Department role agents are Phase 2 and not implemented yet; "
                "remove --include-departments for Phase 1 sync."
            )
        reg = self._load_registry()
        company_name = self._company_name(reg)
        entries: list[AgentPlanEntry] = []
        for ctx in self._render_contexts(reg):
            content = render_agent_markdown(ctx, company_name)
            for out_dir in self.config.output_dirs():
                path = out_dir / f"{ctx.slug}.md"
                entries.append(
                    AgentPlanEntry(
                        slug=ctx.slug,
                        name=ctx.name,
                        title=ctx.title,
                        path=path,
                        content=content,
                        action=self._action_for(path, content),
                    )
                )
        return AgentSyncPlan(entries=entries)

    def run(self) -> AgentSyncResult:
        """Execute the plan: write only create/update entries, never silently."""
        plan = self.plan()
        result = AgentSyncResult()
        seen: set[str] = set()

        def record(collection: list[str], slug: str) -> None:
            if slug not in seen:
                seen.add(slug)
                collection.append(slug)

        for out_dir in self.config.output_dirs():
            out_dir.mkdir(parents=True, exist_ok=True)
        for entry in plan.entries:
            if entry.action == "create":
                try:
                    entry.path.write_text(entry.content, encoding="utf-8")
                    record(result.created, entry.slug)
                except OSError as exc:
                    result.errors.append(f"{entry.path}: {exc}")
            elif entry.action == "update":
                try:
                    entry.path.write_text(entry.content, encoding="utf-8")
                    record(result.updated, entry.slug)
                except OSError as exc:
                    result.errors.append(f"{entry.path}: {exc}")
            elif entry.action == "skip":
                record(result.skipped, entry.slug)
            else:
                record(result.conflicts, entry.slug)
        print_result_summary(result)
        return result
