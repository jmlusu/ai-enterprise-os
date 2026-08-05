"""Company Docs Generator — deterministic top-level company documentation.

Produces the eight top-level company documents from the committed
``config/*.yaml`` configuration files and the loaded registry:

  - ``ROADMAP.md`` — strategy, objectives, initiatives
  - ``CHANGELOG.md`` — versioned baseline of the generated documentation set
  - ``PROJECT_STATUS.md`` — KPIs, strategy status, governance, budget
  - ``BOARD.md`` — governance framework, members, committees, meetings, voting
  - ``WORKFLOWS.md`` — workflow registry and definitions
  - ``DECISION_ENGINE.md`` — approval matrix, risk matrix, decision flows
  - ``MEMORY.md`` — memory engine configuration
  - ``GRAPH.md`` — organization graph summary and inventories

All output is **deterministic**: no timestamps and no wall-clock values, so
the emitted documents can be golden-fixture compared byte-for-byte.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ai_company.company.models import OrgGraph
from ai_company.company.organization import OrganizationGenerator
from ai_company.models.company import CompanyManifest, CompanyRegistry

DOC_FILENAMES: tuple[str, ...] = (
    "ROADMAP.md",
    "CHANGELOG.md",
    "PROJECT_STATUS.md",
    "BOARD.md",
    "WORKFLOWS.md",
    "DECISION_ENGINE.md",
    "MEMORY.md",
    "GRAPH.md",
)


class CompanyDocsGenerator:
    """Generate the eight top-level company documents from config + registry.

    Usage::

        gen = CompanyDocsGenerator(registry, manifest)
        result = gen.generate()
        gen.write_artifacts(result, output_dir)

    Args:
        registry: A loaded :class:`~ai_company.models.company.CompanyRegistry`.
        manifest: Optional company manifest (falls back to the registry).
        config_dir: Path to the ``config/`` directory holding the ``company/``,
            ``board/``, ``decision/``, ``memory/``, and ``workflows/`` files.
        graph: Optional pre-built organization graph (built if not provided).
    """

    def __init__(
        self,
        registry: CompanyRegistry,
        manifest: CompanyManifest | None = None,
        config_dir: str | Path = Path("config"),
        graph: OrgGraph | None = None,
    ) -> None:
        self._registry = registry
        self._manifest = manifest or self._build_minimal_manifest()
        self._config_dir = Path(config_dir)
        self._graph = graph
        self._warnings: list[str] = []

    class Result:
        """Container for every generated top-level document."""

        def __init__(self) -> None:
            self.docs: dict[str, str] = {}
            self.warnings: list[str] = []

        def summary(self) -> dict[str, Any]:
            return {"docs": len(self.docs), "warnings": len(self.warnings)}

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def generate(self) -> Result:
        """Render all eight top-level documents deterministically."""
        result = self.Result()
        result.docs["ROADMAP.md"] = self._render_roadmap()
        result.docs["CHANGELOG.md"] = self._render_changelog()
        result.docs["PROJECT_STATUS.md"] = self._render_project_status()
        result.docs["BOARD.md"] = self._render_board()
        result.docs["WORKFLOWS.md"] = self._render_workflows()
        result.docs["DECISION_ENGINE.md"] = self._render_decision_engine()
        result.docs["MEMORY.md"] = self._render_memory()
        result.docs["GRAPH.md"] = self._render_graph()
        result.warnings.extend(self._warnings)
        return result

    def write_artifacts(self, result: Result, output_dir: Path) -> list[Path]:
        """Write every generated document to ``output_dir/docs/``."""
        created: list[Path] = []
        docs_dir = output_dir / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in result.docs.items():
            path = docs_dir / filename
            path.write_text(content, encoding="utf-8")
            created.append(path)

        return created

    def validate(self) -> list[str]:
        """Validate that the config directory and sources exist."""
        errors: list[str] = []
        for sub in ("company", "board", "decision", "memory", "workflows"):
            path = self._config_dir / sub
            if not path.is_dir():
                errors.append(f"Config directory not found: {path}")
        return errors

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_yaml(self, relative: str) -> dict[str, Any]:
        path = self._config_dir / relative
        if not path.exists():
            self._warnings.append(f"Config file not found: {path}")
            return {}
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            self._warnings.append(f"Failed to load {path.name}: {e}")
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def _company_name(self) -> str:
        return (
            self._manifest.company_name
            or self._manifest.name
            or self._registry.vision.company_name
            or self._registry.vision.name
            or "Company"
        )

    def _build_minimal_manifest(self) -> CompanyManifest:
        return CompanyManifest(
            name=self._registry.vision.company_name
            or self._registry.vision.name
            or "Company",
            company_name=self._registry.vision.company_name
            or self._registry.vision.name,
            description=self._registry.vision.description or "",
        )

    # ------------------------------------------------------------------
    # ROADMAP.md
    # ------------------------------------------------------------------

    def _render_roadmap(self) -> str:
        strategy = self._load_yaml("company/strategy.yaml")
        vision = self._load_yaml("company/vision.yaml")

        lines = [
            "# Roadmap",
            "",
            f"**Company:** {self._company_name}",
            "",
            "## Strategy",
            "",
            f"- **Name:** {strategy.get('name', 'N/A')}",
            f"- **Description:** {strategy.get('description', '')}",
            f"- **Timeframe:** {strategy.get('timeframe', 'N/A')}",
            f"- **Owner:** {strategy.get('owner', 'N/A')}",
            f"- **Status:** {strategy.get('status', 'N/A')}",
            "",
        ]

        mission = vision.get("mission", "")
        if mission:
            lines.extend(["## Mission", "", mission, ""])

        objectives = strategy.get("objectives", [])
        if objectives:
            lines.extend(["## Objectives", ""])
            for objective in objectives:
                lines.append(f"- {objective}")
            lines.append("")

        initiatives = strategy.get("initiatives", [])
        if initiatives:
            lines.extend(["## Initiatives", ""])
            for initiative in initiatives:
                lines.append(f"- {initiative}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    # ------------------------------------------------------------------
    # CHANGELOG.md
    # ------------------------------------------------------------------

    def _render_changelog(self) -> str:
        company = self._load_yaml("company/company.yaml")
        version = company.get("version") or self._manifest.version or "0.0.0"
        description = company.get("description") or self._manifest.description or ""

        lines = [
            "# Changelog",
            "",
            f"**Company:** {self._company_name}",
            f"**Version:** {version}",
            "",
            f"## [{version}] - Generated baseline",
            "",
        ]
        if description:
            lines.append(description)
            lines.append("")
        lines.append("Initial generated documentation set:")
        lines.append("")
        for filename in DOC_FILENAMES:
            lines.append(f"- {filename}")

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # PROJECT_STATUS.md
    # ------------------------------------------------------------------

    def _render_project_status(self) -> str:
        kpis = self._load_yaml("company/kpis.yaml")
        strategy = self._load_yaml("company/strategy.yaml")
        governance = self._load_yaml("company/governance.yaml")
        budget = self._load_yaml("company/budget.yaml")

        lines = [
            "# Project Status",
            "",
            f"**Company:** {self._company_name}",
            "",
            (
                f"**Strategy:** {strategy.get('name', 'N/A')} "
                f"({strategy.get('status', 'N/A')})"
            ),
            "",
            "## Key Performance Indicators",
            "",
            "| KPI | Target | Current | Unit | Owner | Frequency |",
            "|---|---|---|---|---|---|",
        ]

        kpi_items = kpis.get("items", [])
        if not kpi_items:
            kpi_items = kpis.get("kpis", [])
        for kpi in kpi_items:
            if not isinstance(kpi, dict):
                continue
            lines.append(
                f"| {kpi.get('name', 'N/A')} "
                f"| {kpi.get('target', 'N/A')} "
                f"| {kpi.get('current', 'N/A')} "
                f"| {kpi.get('unit', '')} "
                f"| {kpi.get('owner', '')} "
                f"| {kpi.get('frequency', '')} |"
            )
        lines.append("")

        lines.extend(["## Governance", ""])
        lines.append(f"- **Framework:** {governance.get('framework', 'N/A')}")
        lines.append(f"- **Review Cycle:** {governance.get('review_cycle', 'N/A')}")
        standards = governance.get("compliance_standards", [])
        if standards:
            lines.append(f"- **Compliance Standards:** {', '.join(standards)}")
        lines.append("")

        budget_departments = budget.get("departments", {})
        if isinstance(budget_departments, dict) and budget_departments:
            lines.extend(
                [
                    "## Budget",
                    "",
                    "| Department | Total | Spent | Currency |",
                    "|---|---|---|---|",
                ]
            )
            for dept_name, dept in budget_departments.items():
                if not isinstance(dept, dict):
                    continue
                lines.append(
                    f"| {dept_name} | {dept.get('total', 0)} | {dept.get('spent', 0)} "
                    f"| {dept.get('currency', 'USD')} |"
                )
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    # ------------------------------------------------------------------
    # BOARD.md
    # ------------------------------------------------------------------

    def _render_board(self) -> str:
        board_cfg = self._load_yaml("board/board.yaml")
        committees_cfg = self._load_yaml("board/committees.yaml")
        meetings_cfg = self._load_yaml("board/meetings.yaml")
        voting_cfg = self._load_yaml("board/voting.yaml")

        governance = board_cfg.get("governance", {})
        expectations = board_cfg.get("expectations", {})

        members = self._registry.board_members or self._registry.board

        lines = [
            "# Board of Directors",
            "",
            f"**Company:** {self._company_name}",
            "",
            "## Governance",
            "",
            f"- **Framework:** {governance.get('framework', 'standard').title()}",
        ]
        size = governance.get("board_size", {})
        if isinstance(size, dict):
            lines.append(
                f"- **Board Size:** {size.get('min', 3)}–{size.get('max', 15)} "
                f"(current: {size.get('current', len(members))})"
            )
        lines.append(f"- **Term Length:** {governance.get('term_years', 3)} years")
        lines.append(f"- **Max Terms:** {governance.get('max_terms', 3)}")
        lines.append(
            f"- **Staggered Terms:** {'Yes' if governance.get('staggered') else 'No'}"
        )
        lines.append("")

        lines.extend(["## Board Members", ""])
        for member in members:
            name = member.name if hasattr(member, "name") and member.name else "Unnamed"
            role = (
                member.role if hasattr(member, "role") and member.role else "Director"
            )
            lines.append(f"- **{name}** — {role}")
        lines.append("")

        committees = committees_cfg.get("committees", [])
        if committees:
            lines.extend(["## Committees", ""])
            for committee in committees:
                if not isinstance(committee, dict):
                    continue
                lines.append(f"### {committee.get('name', 'N/A')}")
                lines.append("")
                if committee.get("purpose"):
                    lines.append(f"- **Purpose:** {committee['purpose']}")
                lines.append(
                    f"- **Size:** {committee.get('min_size', 3)}–"
                    f"{committee.get('max_size', 5)}"
                )
                lines.append(
                    f"- **Frequency:** {committee.get('meeting_frequency', 'quarterly')}"
                )
                lines.append("")

        lines.extend(["## Meetings", ""])
        schedule = meetings_cfg.get("annual_schedule", {})
        board_meetings = schedule.get("board_meetings", {})
        months = board_meetings.get("months", [])
        if months:
            for i, month in enumerate(months, start=1):
                lines.append(f"- **Q{i} Board Meeting** — {month}")
        else:
            lines.append("- *No meeting schedule configured.*")
        lines.append("")

        lines.extend(["## Voting", ""])
        quorum = voting_cfg.get("quorum", {})
        if isinstance(quorum, dict):
            lines.append("- **Quorum (board):**")
            for key, value in quorum.items():
                if isinstance(value, dict):
                    threshold = value.get("threshold", 0.5)
                    lines.append(
                        f"  - {key.replace('_', ' ').title()}: ≥{threshold:.0%}"
                    )
        voting = voting_cfg.get("voting", {})
        if isinstance(voting, dict):
            lines.append("- **Voting rules:**")
            for key, value in voting.items():
                if isinstance(value, dict):
                    threshold = value.get("threshold", "majority")
                    lines.append(
                        f"  - {key.replace('_', ' ').title()}: {threshold.replace('_', ' ').title()}"
                    )
        lines.append("")

        if expectations:
            lines.extend(["## Director Expectations", ""])
            if expectations.get("meeting_attendance"):
                lines.append(
                    f"- **Meeting Attendance:** ≥{expectations['meeting_attendance']}%"
                )
            if expectations.get("committee_service"):
                lines.append(
                    f"- **Committee Service:** ≥{expectations['committee_service']} committee(s)"
                )
            if expectations.get("code_of_conduct"):
                lines.append(
                    f"- **Code of Conduct:** {expectations['code_of_conduct']}"
                )
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    # ------------------------------------------------------------------
    # WORKFLOWS.md
    # ------------------------------------------------------------------

    def _render_workflows(self) -> str:
        registry_cfg = self._load_yaml("workflows/workflow_registry.yaml")

        lines = [
            "# Workflows",
            "",
            f"**Company:** {self._company_name}",
            "",
            "## Workflow Registry",
            "",
            "| Workflow | Category | Version | Enabled |",
            "|---|---|---|---|",
        ]

        workflows = registry_cfg.get("workflows", {})
        if isinstance(workflows, dict):
            for key in sorted(workflows.keys()):
                entry = workflows[key]
                if not isinstance(entry, dict):
                    continue
                lines.append(
                    f"| {entry.get('name', key)} | {entry.get('category', '')} "
                    f"| {entry.get('version', '')} "
                    f"| {'Yes' if entry.get('enabled') else 'No'} |"
                )
        lines.append("")

        lines.extend(["## Workflow Definitions", ""])
        if isinstance(workflows, dict):
            for key in sorted(workflows.keys()):
                entry = workflows[key]
                if not isinstance(entry, dict):
                    continue
                definition = self._load_yaml(f"workflows/{key}.yaml")
                name = definition.get("display_name") or entry.get("name") or key
                lines.append(f"### {name}")
                lines.append("")
                description = definition.get("description") or entry.get(
                    "description", ""
                )
                if description:
                    lines.append(f"{description}")
                    lines.append("")
                states = definition.get("states", {})
                if isinstance(states, dict) and states:
                    lines.append("**States:**")
                    lines.append("")
                    for state_key in states:
                        state = states[state_key]
                        state_name = (
                            state.get("name", state_key)
                            if isinstance(state, dict)
                            else state_key
                        )
                        lines.append(f"- {state_key}: {state_name}")
                    lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    # ------------------------------------------------------------------
    # DECISION_ENGINE.md
    # ------------------------------------------------------------------

    def _render_decision_engine(self) -> str:
        approval = self._load_yaml("decision/approval_matrix.yaml")
        risk = self._load_yaml("decision/risk_matrix.yaml")
        tree = self._load_yaml("decision/decision_tree.yaml")

        lines = [
            "# Decision Engine",
            "",
            f"**Company:** {self._company_name}",
            "",
            "## Approval Matrix",
            "",
            "### Default Approvers",
            "",
            "| Decision Type | Approver |",
            "|---|---|",
        ]

        default_approvers = approval.get("default_approvers", {})
        if isinstance(default_approvers, dict):
            for key in sorted(default_approvers.keys()):
                lines.append(f"| {key} | {default_approvers[key]} |")
        lines.append("")

        rules = approval.get("rules", [])
        if rules:
            lines.extend(
                [
                    "### Approval Rules",
                    "",
                    "| Rule | Decision Type | Approver | Escalation |",
                    "|---|---|---|---|",
                ]
            )
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                lines.append(
                    f"| {rule.get('name', rule.get('rule_id', ''))} "
                    f"| {rule.get('decision_type', '')} "
                    f"| {rule.get('approver', '')} "
                    f"| {rule.get('escalation', '')} |"
                )
            lines.append("")

        lines.extend(["## Risk Matrix", ""])
        risk_levels = risk.get("risk_levels", {})
        if isinstance(risk_levels, dict):
            lines.extend(
                [
                    "### Risk Levels",
                    "",
                    "| Level | Range | Auto-approve | Escalation |",
                    "|---|---|---|---|",
                ]
            )
            for key in sorted(risk_levels.keys()):
                level = risk_levels[key]
                if not isinstance(level, dict):
                    continue
                lines.append(
                    f"| {level.get('name', key)} "
                    f"| {level.get('min_score', 0)}–{level.get('max_score', 1)} "
                    f"| {'Yes' if level.get('auto_approve') else 'No'} "
                    f"| {'Yes' if level.get('requires_escalation') else 'No'} |"
                )
            lines.append("")

        risk_factors = risk.get("risk_factors", {})
        if isinstance(risk_factors, dict):
            lines.extend(
                [
                    "### Risk Factors",
                    "",
                    "| Factor | Weight | Category |",
                    "|---|---|---|",
                ]
            )
            for key in sorted(risk_factors.keys()):
                factor = risk_factors[key]
                if not isinstance(factor, dict):
                    continue
                lines.append(
                    f"| {factor.get('name', key)} | {factor.get('weight', '')} "
                    f"| {factor.get('category', '')} |"
                )
            lines.append("")

        escalation_triggers = risk.get("escalation_triggers", [])
        if escalation_triggers:
            lines.extend(["### Escalation Triggers", ""])
            for trigger in escalation_triggers:
                if not isinstance(trigger, dict):
                    continue
                lines.append(
                    f"- **{trigger.get('name', '')}** — {trigger.get('description', '')}"
                )
            lines.append("")

        lines.extend(["## Decision Flows", ""])
        flows = tree.get("decision_flows", {})
        if isinstance(flows, dict):
            lines.append("| Category | Name | Risk Assessment | Approval Required |")
            lines.append("|---|---|---|---|")
            for key in sorted(flows.keys()):
                flow = flows[key]
                if not isinstance(flow, dict):
                    continue
                lines.append(
                    f"| {key} | {flow.get('name', '')} "
                    f"| {'Yes' if flow.get('initial_risk_assessment') else 'No'} "
                    f"| {'Yes' if flow.get('requires_approval') else 'No'} |"
                )
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    # ------------------------------------------------------------------
    # MEMORY.md
    # ------------------------------------------------------------------

    def _render_memory(self) -> str:
        memory = self._load_yaml("memory/memory.yaml")

        lines = [
            "# Memory Engine",
            "",
            f"**Company:** {self._company_name}",
            "",
        ]
        description = memory.get("description", "")
        if description:
            lines.extend([f"{description}", ""])
        version = memory.get("version", "")
        if version:
            lines.extend([f"**Version:** {version}", ""])

        namespaces = memory.get("namespaces", {})
        if isinstance(namespaces, dict):
            lines.extend(
                [
                    "## Namespaces",
                    "",
                    "| Namespace | Description | Max Entries | Retention (days) |",
                    "|---|---|---|---|",
                ]
            )
            for key in sorted(namespaces.keys()):
                ns = namespaces[key]
                if not isinstance(ns, dict):
                    continue
                lines.append(
                    f"| {key} | {ns.get('description', '')} "
                    f"| {ns.get('max_entries', '')} "
                    f"| {ns.get('retention_days', '')} |"
                )
            lines.append("")

        memory_types = memory.get("memory_types", {})
        if isinstance(memory_types, dict):
            lines.extend(
                [
                    "## Memory Types",
                    "",
                    "| Type | Importance | Retention (days) | Auto-summarize | Max Versions |",
                    "|---|---|---|---|---|",
                ]
            )
            for key in sorted(memory_types.keys()):
                mt = memory_types[key]
                if not isinstance(mt, dict):
                    continue
                lines.append(
                    f"| {key} | {mt.get('importance_default', '')} "
                    f"| {mt.get('retention_days', '')} "
                    f"| {'Yes' if mt.get('auto_summarize') else 'No'} "
                    f"| {mt.get('max_versions', '')} |"
                )
            lines.append("")

        retention = memory.get("retention", {})
        if isinstance(retention, dict):
            lines.extend(["## Retention Policy", ""])
            lines.append(
                f"- **Enabled:** {'Yes' if retention.get('enabled') else 'No'}"
            )
            lines.append(
                f"- **Default Max Age:** {retention.get('default_max_age_days', '')} days"
            )
            lines.append(
                f"- **Archive After:** {retention.get('archive_after_days', '')} days"
            )
            lines.append(
                f"- **Purge After:** {retention.get('purge_after_days', '')} days"
            )
            lines.append("")

        embeddings = memory.get("embeddings", {})
        if isinstance(embeddings, dict):
            lines.extend(["## Embeddings", ""])
            lines.append(
                f"- **Enabled:** {'Yes' if embeddings.get('enabled') else 'No'}"
            )
            lines.append(f"- **Provider:** {embeddings.get('provider', '')}")
            lines.append(f"- **Dimension:** {embeddings.get('dimension', '')}")
            lines.append(
                f"- **Similarity:** {embeddings.get('similarity_function', '')}"
            )
            lines.append("")

        search = memory.get("search", {})
        if isinstance(search, dict):
            lines.extend(["## Search", ""])
            lines.append(
                f"- **Default Max Results:** {search.get('default_max_results', '')}"
            )
            lines.append(
                f"- **Fuzzy Matching:** {'Yes' if search.get('fuzzy_matching') else 'No'}"
            )
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    # ------------------------------------------------------------------
    # GRAPH.md
    # ------------------------------------------------------------------

    def _build_graph(self) -> OrgGraph:
        if self._graph is not None:
            return self._graph
        return OrganizationGenerator(self._registry).generate().graph

    def _render_graph(self) -> str:
        graph = self._build_graph()
        metadata = graph.compute_metadata()

        lines = [
            "# Organization Graph",
            "",
            f"**Company:** {self._company_name}",
            "",
            "## Summary",
            "",
            f"- **Total Nodes:** {metadata.total_nodes}",
            f"- **Total Edges:** {metadata.total_edges}",
            f"- **Max Depth:** {metadata.max_depth} levels",
            "",
            "## Node Types",
            "",
            "| Type | Count |",
            "|---|---|",
        ]
        for ntype, count in sorted(metadata.node_type_counts.items()):
            lines.append(f"| {ntype} | {count} |")
        lines.append("")

        nodes = sorted(graph.nodes.values(), key=lambda n: n.id)
        if nodes:
            lines.extend(["## Node Inventory", ""])
            for node in nodes:
                lines.append(
                    f"- `{node.id}` — **{node.name}** ({node.title}) "
                    f"[{node.node_type}, level {node.level}]"
                )
            lines.append("")

        graph_edges = sorted(
            graph.edges, key=lambda e: (e.edge_type, e.source_id, e.target_id)
        )
        by_type: dict[str, list[str]] = {}
        for edge in graph_edges:
            by_type.setdefault(edge.edge_type, []).append(
                f"- `{edge.source_id}` → `{edge.target_id}`"
            )
        if by_type:
            lines.extend(["## Edge Inventory", ""])
            for etype, edge_lines in sorted(by_type.items()):
                lines.append(f"### {etype} ({len(edge_lines)})")
                lines.append("")
                lines.extend(edge_lines)
                lines.append("")

        return "\n".join(lines).rstrip() + "\n"
