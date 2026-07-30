"""Board Generator — produces board governance artifacts from registry and templates.

The :class:`BoardGenerator` reads:
  - registry data (``CompanyRegistry.board_members``, ``committees``, etc.)
  - ``config/board/*.yaml`` templates (governance settings, committee definitions,
    charter templates, meeting schedule, voting rules)

It generates:
  - **Board member profiles** (``docs/BOARD.md``)
  - **Committee charters** (``docs/BOARD_CHARTER.md``)
  - **Governance framework** (``docs/BOARD_GOVERNANCE.md``)
  - **Meeting schedules, voting rules, integration with OrgGraph**
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ai_company.company.models import OrgEdge, OrgGraph, OrgNode
from ai_company.models.company import BoardMember, CompanyRegistry

# ---------------------------------------------------------------------------
# Data holder
# ---------------------------------------------------------------------------


class BoardResult:
    """Container for everything the BoardGenerator produces."""

    def __init__(self) -> None:
        self.member_profiles: list[dict[str, Any]] = []
        self.committees: list[dict[str, Any]] = []
        self.committee_charters: list[dict[str, Any]] = []
        self.meetings: list[dict[str, Any]] = []
        self.voting_rules: dict[str, Any] = {}
        self.graph_updates: list[
            tuple[str, str, str]
        ] = []  # (source, target, edge_type)
        self.warnings: list[str] = []
        self.board_name: str = ""
        self.governance: dict[str, Any] = {}

    def summary(self) -> dict[str, Any]:
        return {
            "board_name": self.board_name,
            "members": len(self.member_profiles),
            "committees": len(self.committees),
            "charters": len(self.committee_charters),
            "meetings": len(self.meetings),
            "graph_updates": len(self.graph_updates),
            "warnings": len(self.warnings),
        }


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class BoardGenerator:
    """Generate board governance artifacts from a CompanyRegistry.

    Usage::

        gen = BoardGenerator(registry)
        result = gen.generate()
        gen.write_artifacts(result, output_dir)
        gen.apply_to_graph(result, org_graph)
    """

    def __init__(
        self,
        registry: CompanyRegistry,
        config_dir: str | Path = Path("config/board"),
    ) -> None:
        self._registry = registry
        self._config_dir = Path(config_dir)
        self._warn_cache: list[str] = []

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def generate(self) -> BoardResult:
        """Run the full board generation pipeline."""
        result = BoardResult()

        # 1. Load config templates
        config = self._load_configs()
        result.governance = config.get("board", {}).get("governance", {})

        # 2. Build member profiles from registry
        result.member_profiles = self._build_member_profiles(config)

        # 3. Build committee assignments
        result.committees = self._build_committees(config)

        # 4. Build committee charters
        result.committee_charters = self._build_charters(config)

        # 5. Build meeting schedule
        result.meetings = self._build_meetings(config)

        # 6. Build voting rules
        result.voting_rules = config.get("voting", {})

        # 7. Determine board display name
        result.board_name = (
            self._registry.vision.company_name
            or self._registry.vision.name
            or "Company"
        )

        # 8. Prepare graph updates (committees → members)
        result.graph_updates = self._build_graph_updates(result)

        # 9. Attach cached warnings
        result.warnings.extend(self._warn_cache)

        return result

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_configs(self) -> dict[str, Any]:
        """Load all config/board/*.yaml files into a single dict."""
        config: dict[str, Any] = {}
        for fname in ("board", "committees", "charters", "meetings", "voting"):
            path = self._config_dir / f"{fname}.yaml"
            if path.exists():
                try:
                    data = yaml.safe_load(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        config[fname] = data
                except yaml.YAMLError as e:
                    self._warn_cache.append(f"Failed to load {path.name}: {e}")
        return config

    # ------------------------------------------------------------------
    # Member profiles
    # ------------------------------------------------------------------

    def _build_member_profiles(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        profiles: list[dict[str, Any]] = []
        expectations = config.get("board", {}).get("expectations", {})
        compensation = config.get("board", {}).get("compensation", {})

        for member in self._registry.board_members:
            profile = self._enrich_member(member, expectations, compensation)
            profiles.append(profile)

        # Fall back to raw board entries if no board_members
        if not profiles:
            for entry in self._registry.board:
                role = entry.role or "Director"
                profiles.append(
                    {
                        "name": entry.name or "Unnamed",
                        "role": role,
                        "term_start": "",
                        "term_end": "",
                        "committees": [],
                        "independent": False,
                        "bio": "",
                        "expertise": _infer_expertise(role, []),
                    }
                )

        return profiles

    @staticmethod
    def _enrich_member(
        member: BoardMember,
        expectations: dict[str, Any],
        compensation: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "name": member.name,
            "role": member.role or "Director",
            "term_start": member.term_start or "",
            "term_end": member.term_end or "",
            "committees": list(member.committees),
            "independent": member.independent,
            "expertise": _infer_expertise(member.role, member.committees),
            "meeting_attendance_target": expectations.get("meeting_attendance", 75),
            "compensation": {
                "cash_retainer": compensation.get("cash_retainer", 0),
                "equity_retainer": compensation.get("equity_retainer", 0),
            },
        }

    # ------------------------------------------------------------------
    # Committees
    # ------------------------------------------------------------------

    def _build_committees(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Match registry committees with config templates, fill in members."""
        committees: list[dict[str, Any]] = []
        template_map: dict[str, dict[str, Any]] = {
            c["name"].lower(): c
            for c in config.get("committees", {}).get("committees", [])
        }

        # Map registry committee names → config templates
        for committee in self._registry.committees:
            key = committee.name.lower().replace(" ", "_").replace("-", "_")
            tmpl = template_map.get(committee.name.lower(), template_map.get(key, {}))
            member_names = list(committee.members)
            committees.append(
                {
                    "name": committee.name,
                    "purpose": committee.purpose or tmpl.get("purpose", ""),
                    "chair": committee.chair or "",
                    "members": member_names,
                    "meeting_frequency": committee.meeting_frequency
                    or tmpl.get("meeting_frequency", "quarterly"),
                    "min_size": tmpl.get("min_size", 3),
                    "max_size": tmpl.get("max_size", 5),
                    "expertise_required": tmpl.get("expertise_required", []),
                    "independence_required": tmpl.get("independence_required", False),
                    "responsibilities": tmpl.get("responsibilities", []),
                }
            )

        # If no committees in registry, seed from config templates
        if not committees:
            for tmpl in config.get("committees", {}).get("committees", []):
                committees.append(
                    {
                        "name": tmpl["name"],
                        "purpose": tmpl.get("purpose", ""),
                        "chair": "",
                        "members": [],
                        "meeting_frequency": tmpl.get("meeting_frequency", "quarterly"),
                        "min_size": tmpl.get("min_size", 3),
                        "max_size": tmpl.get("max_size", 5),
                        "expertise_required": tmpl.get("expertise_required", []),
                        "independence_required": tmpl.get(
                            "independence_required", False
                        ),
                        "responsibilities": tmpl.get("responsibilities", []),
                    }
                )

        return committees

    # ------------------------------------------------------------------
    # Charters
    # ------------------------------------------------------------------

    def _build_charters(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        charters: list[dict[str, Any]] = []
        charter_templates = config.get("charters", {}).get("charters", [])

        for tmpl in charter_templates:
            committee_name = tmpl.get("committee", "")
            committee_info = next(
                (c for c in self._registry.committees if c.name == committee_name),
                None,
            )
            charters.append(
                {
                    "committee": committee_name,
                    "preamble": tmpl.get("preamble", ""),
                    "authority": tmpl.get("authority", ""),
                    "composition_rules": tmpl.get("composition_rules", []),
                    "meeting_rules": tmpl.get("meeting_rules", {}),
                    "reporting": tmpl.get("reporting", []),
                    "current_chair": committee_info.chair if committee_info else "",
                    "current_members": (
                        list(committee_info.members) if committee_info else []
                    ),
                }
            )

        return charters

    # ------------------------------------------------------------------
    # Meetings
    # ------------------------------------------------------------------

    def _build_meetings(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        meetings: list[dict[str, Any]] = []

        # Registry meetings take priority
        for meeting in self._registry.meetings:
            meetings.append(
                {
                    "title": meeting.title,
                    "date": meeting.meeting_date,
                    "type": meeting.meeting_type,
                    "attendees": list(meeting.attendees),
                    "minutes": meeting.minutes,
                    "action_items": list(meeting.action_items),
                }
            )

        # If no meetings in registry, seed from config template
        if not meetings:
            schedule = config.get("meetings", {}).get("annual_schedule", {})
            board_meetings = schedule.get("board_meetings", {})
            months = board_meetings.get("months", [])
            for month in months:
                meetings.append(
                    {
                        "title": f"Q{months.index(month) + 1} Board Meeting",
                        "date": f"{month} {datetime.now().year}",
                        "type": "board",
                        "attendees": [m.name for m in self._registry.board_members]
                        or [e.name or "" for e in self._registry.board],
                        "minutes": "",
                        "action_items": [],
                    }
                )

            events = schedule.get("annual_events", [])
            for event in events:
                meetings.append(
                    {
                        "title": event.get("name", "Annual Event"),
                        "date": f"{event.get('typical_month', 'TBD')} {datetime.now().year}",
                        "type": "annual",
                        "attendees": [m.name for m in self._registry.board_members]
                        or [e.name or "" for e in self._registry.board],
                        "minutes": "",
                        "action_items": [],
                    }
                )

        return meetings

    # ------------------------------------------------------------------
    # Graph integration
    # ------------------------------------------------------------------

    def _build_graph_updates(self, result: BoardResult) -> list[tuple[str, str, str]]:
        """Plan OrgGraph updates: create committee nodes, link members to committees.

        Member node ID resolution is done in ``apply_to_graph`` which has
        access to the actual OrgGraph. This method just marks intent.
        """
        updates: list[tuple[str, str, str]] = []

        for committee in result.committees:
            com_id = f"committee:{committee['name'].lower().replace(' ', '_')}"
            for member_name in committee["members"]:
                updates.append((member_name, com_id, "serves_on"))
            if committee["chair"]:
                updates.append((committee["chair"], com_id, "chairs"))

        return updates

    # ------------------------------------------------------------------
    # Apply to OrgGraph
    # ------------------------------------------------------------------

    def apply_to_graph(self, result: BoardResult, graph: OrgGraph) -> None:
        """Add committee nodes and serving/chairs edges to an existing OrgGraph."""
        # Add committee nodes first
        for committee in result.committees:
            com_id = f"committee:{committee['name'].lower().replace(' ', '_')}"
            if com_id not in graph.nodes:
                graph.add_node(
                    OrgNode(
                        id=com_id,
                        name=committee["name"],
                        title=f"{committee['name']} Committee",
                        node_type="committee",
                        level=0,
                    )
                )

        # Resolve member names to node IDs and add edges
        known_ids = set(graph.nodes.keys())
        for member_name, com_id, edge_type in result.graph_updates:
            source_id = self._resolve_node_id(member_name, known_ids)
            if source_id and com_id in known_ids:
                graph.add_edge(OrgEdge(source_id, com_id, edge_type))

    @staticmethod
    def _resolve_node_id(member_name: str, known_ids: set[str]) -> str | None:
        """Convert a board member name to a node ID used in the OrgGraph."""
        safe = member_name.lower().replace(" ", "_").replace("-", "_")
        # Check various ID patterns
        for pattern in ("board:", "board_member:"):
            candidate = f"{pattern}{safe}"
            if candidate in known_ids:
                return candidate
        # Fallback: find any node id ending with the safe name
        for nid in known_ids:
            if nid.endswith(f":{safe}"):
                return nid
        return None

    # ------------------------------------------------------------------
    # Artifact writers
    # ------------------------------------------------------------------

    def write_artifacts(self, result: BoardResult, output_dir: Path) -> list[Path]:
        """Write all board artifacts to the given output directory.

        Returns a list of created file paths.
        """
        created: list[Path] = []
        docs_dir = output_dir / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        # 1. Board member profiles
        profiles_path = docs_dir / "BOARD.md"
        profiles_path.write_text(self._render_board_markdown(result), encoding="utf-8")
        created.append(profiles_path)

        # 2. Governance framework
        gov_path = docs_dir / "BOARD_GOVERNANCE.md"
        gov_path.write_text(self._render_governance_markdown(result), encoding="utf-8")
        created.append(gov_path)

        # 3. Committee charters
        charter_path = docs_dir / "BOARD_CHARTER.md"
        charter_path.write_text(
            self._render_charters_markdown(result), encoding="utf-8"
        )
        created.append(charter_path)

        # 4. JSON export
        json_path = output_dir / "board.json"
        json_path.write_text(
            json.dumps(self._to_json(result), indent=2, default=str),
            encoding="utf-8",
        )
        created.append(json_path)

        # 5. YAML export
        yaml_path = output_dir / "board.yaml"
        yaml_path.write_text(
            yaml.dump(self._to_json(result), default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        created.append(yaml_path)

        return created

    # ------------------------------------------------------------------
    # Renderers
    # ------------------------------------------------------------------

    def _render_board_markdown(self, result: BoardResult) -> str:
        """Render board member profiles document."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# Board of Directors",
            "",
            f"**Company:** {result.board_name}",
            f"**Generated:** {now}",
            "",
            "---",
            "",
            "## Board Members",
            "",
        ]
        for m in result.member_profiles:
            expertise_str = (
                ", ".join(m["expertise"]) if m["expertise"] else "General governance"
            )
            lines.extend(
                [
                    f"### {m['name']} — {m['role']}",
                    "",
                    f"- **Term:** {m['term_start'] or 'Current'} — {m['term_end'] or 'Ongoing'}",
                    f"- **Independent:** {'Yes' if m['independent'] else 'No'}",
                    f"- **Committees:** {', '.join(m['committees']) if m['committees'] else 'None assigned'}",
                    f"- **Expertise:** {expertise_str}",
                    "",
                ]
            )

        if result.governance:
            lines.extend(
                [
                    "## Governance Summary",
                    "",
                    f"- **Framework:** {result.governance.get('framework', 'standard').title()}",
                    f"- **Board Size:** {result.governance.get('board_size', {}).get('current', len(result.member_profiles))}",
                    f"- **Term Length:** {result.governance.get('term_years', 3)} years",
                    f"- **Max Terms:** {result.governance.get('max_terms', 3)}",
                    f"- **Code of Conduct:** {result.governance.get('expectations', {}).get('code_of_conduct', 'N/A')}",
                    "",
                ]
            )

        lines.extend(
            [
                "## Meetings",
                "",
            ]
        )
        for m in result.meetings:
            lines.append(f"- **{m['title']}** — {m['date']} ({m['type']})")

        lines.extend(
            [
                "",
                "---",
                "",
                f"*Board composition generated on {now}*",
            ]
        )
        return "\n".join(lines)

    def _render_governance_markdown(self, result: BoardResult) -> str:
        """Render governance framework document."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        gov = result.governance
        lines = [
            "# Board Governance Framework",
            "",
            f"**Company:** {result.board_name}",
            f"**Generated:** {now}",
            "",
            "---",
            "",
            "## 1. Governance Structure",
            "",
            f"- **Framework:** {gov.get('framework', 'standard').title()}",
            f"- **Board Size:** {gov.get('board_size', {}).get('min', 3)}–{gov.get('board_size', {}).get('max', 15)} "
            f"(current: {gov.get('board_size', {}).get('current', len(result.member_profiles))})",
            f"- **Term Length:** {gov.get('term_years', 3)} years, "
            f"max {gov.get('max_terms', 3)} terms",
            f"- **Staggered Terms:** {'Yes' if gov.get('staggered') else 'No'}",
            "",
            "## 2. Director Expectations",
            "",
        ]
        expectations = gov.get("expectations", {})
        lines.append(
            f"- **Meeting Attendance:** ≥{expectations.get('meeting_attendance', 75)}%"
        )
        lines.append(
            f"- **Committee Service:** ≥{expectations.get('committee_service', 1)} committee(s)"
        )
        lines.append(
            f"- **Independence Ratio:** ≥{expectations.get('independence_ratio', 0.5):.0%}"
        )
        lines.append(
            f"- **Code of Conduct:** {expectations.get('code_of_conduct', 'N/A')}"
        )
        lines.append("")

        # Evaluation
        eval_section = gov.get("evaluation", {})
        lines.extend(
            [
                "## 3. Board Evaluation",
                "",
                f"- **Frequency:** {eval_section.get('frequency', 'annual').title()}",
                f"- **Type:** {eval_section.get('type', 'self_assessment').replace('_', ' ').title()}",
                "",
                "**Metrics:**",
            ]
        )
        for metric in eval_section.get("metrics", []):
            lines.append(f"  - {metric}")
        lines.append("")

        # Succession
        succession = gov.get("succession", {})
        lines.extend(
            [
                "## 4. Succession Planning",
                "",
                f"**Policy:** {succession.get('policy', 'N/A')}",
                "",
                "**Criteria:**",
            ]
        )
        for c in succession.get("criteria", []):
            lines.append(f"  - {c}")
        lines.append("")

        # Compensation
        comp = gov.get("compensation", {})
        lines.extend(
            [
                "## 5. Director Compensation",
                "",
                f"- **Model:** {comp.get('model', 'N/A')}",
                f"- **Cash Retainer:** {comp.get('currency', 'USD')} {comp.get('cash_retainer', 0):,}",
                f"- **Equity Retainer:** {comp.get('currency', 'USD')} {comp.get('equity_retainer', 0):,}",
                f"- **Committee Chair Extra:** {comp.get('currency', 'USD')} {comp.get('committee_chair_extra', 0):,}",
                f"- **Board Chair Extra:** {comp.get('currency', 'USD')} {comp.get('board_chair_extra', 0):,}",
                f"- **Meeting Fee:** {comp.get('currency', 'USD')} {comp.get('meeting_fee', 0):,}",
                "",
                "## 6. Committees",
                "",
            ]
        )
        for cm in result.committees:
            lines.extend(
                [
                    f"### {cm['name']}",
                    "",
                    f"- **Purpose:** {cm['purpose']}",
                    f"- **Chair:** {cm['chair'] or 'TBD'}",
                    f"- **Members ({len(cm['members'])}):** {', '.join(cm['members']) if cm['members'] else 'TBD'}",
                    f"- **Meeting Frequency:** {cm['meeting_frequency'].title()}",
                    "",
                ]
            )

        lines.extend(
            [
                "## 7. Voting & Quorum",
                "",
            ]
        )
        voting = result.voting_rules.get("voting", {})
        quorum = result.voting_rules.get("quorum", {})
        for q_key, q_val in quorum.items():
            if isinstance(q_val, dict):
                lines.append(
                    f"- **{q_key.replace('_', ' ').title()}:** "
                    f"≥{q_val.get('threshold', 0.5):.0%} of "
                    f"{q_val.get('calculation', 'members').replace('_', ' ')}"
                )
        lines.append("")
        for v_key, v_val in voting.items():
            if isinstance(v_val, dict):
                threshold = v_val.get("threshold", "majority")
                desc = v_val.get("description", "")
                lines.append(
                    f"- **{v_key.replace('_', ' ').title()}:** "
                    f"{threshold.replace('_', ' ').title()} — {desc}"
                )

        lines.append("")
        lines.append("---")
        lines.append(f"*Governance framework generated on {now}*")
        return "\n".join(lines)

    def _render_charters_markdown(self, result: BoardResult) -> str:
        """Render committee charters document."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# Board Committee Charters",
            "",
            f"**Company:** {result.board_name}",
            f"**Generated:** {now}",
            "",
            "---",
            "",
        ]
        for charter in result.committee_charters:
            lines.extend(
                [
                    f"## {charter['committee']} Charter",
                    "",
                    "### Preamble",
                    "",
                    charter.get("preamble", "").strip(),
                    "",
                    "### Authority",
                    "",
                    charter.get("authority", "").strip(),
                    "",
                    "### Composition",
                    "",
                ]
            )
            for rule in charter.get("composition_rules", []):
                lines.append(f"- {rule}")
            lines.append("")
            lines.append(
                f"- **Current Chair:** {charter.get('current_chair') or 'TBD'}"
            )
            members = charter.get("current_members", [])
            lines.append(
                f"- **Current Members ({len(members)}):** "
                f"{', '.join(members) if members else 'To be appointed'}"
            )
            lines.append("")

            meeting_rules = charter.get("meeting_rules", {})
            lines.extend(
                [
                    "### Meetings",
                    "",
                    f"- **Quorum:** {meeting_rules.get('quorum', 'majority').replace('_', ' ').title()}",
                    f"- **Minimum Meetings/Year:** {meeting_rules.get('min_meetings_per_year', 4)}",
                    f"- **Executive Sessions:** {'Yes' if meeting_rules.get('executive_sessions') else 'No'}",
                    "",
                    "### Reporting",
                    "",
                ]
            )
            for r in charter.get("reporting", []):
                lines.append(f"- {r}")
            lines.append("")
            lines.append("---")
            lines.append("")

        lines.append(f"*Charters generated on {now}*")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # JSON serialization
    # ------------------------------------------------------------------

    def _to_json(self, result: BoardResult) -> dict[str, Any]:
        return {
            "board": {
                "name": result.board_name,
                "governance": result.governance,
                "members": result.member_profiles,
                "committees": result.committees,
                "charters": result.committee_charters,
                "meetings": result.meetings,
                "voting_rules": result.voting_rules,
                "warnings": result.warnings,
                "graph_updates": [
                    {"source": s, "target": t, "type": e}
                    for s, t, e in result.graph_updates
                ],
            }
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Validate that the registry can produce board artifacts."""
        errors: list[str] = []
        if not self._registry.board and not self._registry.board_members:
            errors.append("No board members defined in registry")
        if not self._config_dir.exists():
            errors.append(f"Board config directory not found: {self._config_dir}")
        return errors


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: Mapping of role keywords to expertise areas for board members.
_ROLE_EXPERTISE: dict[str, list[str]] = {
    "chair": ["leadership", "governance", "strategic planning"],
    "vice chair": ["leadership", "governance"],
    "independent director": ["governance", "risk management"],
    "non-executive director": ["governance", "industry expertise"],
}

_COMMITTEE_EXPERTISE: dict[str, list[str]] = {
    "audit": ["finance", "accounting", "risk management"],
    "compensation": ["hr", "compensation", "governance"],
    "ai ethics": ["ai ethics", "machine learning", "policy"],
    "nominating": ["governance", "leadership", "diversity"],
    "technology": ["technology", "cybersecurity"],
}


def _infer_expertise(role: str, committees: list[str]) -> list[str]:
    """Infer a board member's expertise from their role and committees."""
    expertise: list[str] = []
    seen: set[str] = set()
    role_lower = role.lower()
    for keyword, skills in sorted(_ROLE_EXPERTISE.items(), key=lambda kv: -len(kv[0])):
        if keyword in role_lower:
            for s in skills:
                if s not in seen:
                    expertise.append(s)
                    seen.add(s)
    if not expertise:
        expertise.append("governance")
        seen.add("governance")
    for cm in committees:
        cm_lower = cm.lower()
        for keyword, skills in _COMMITTEE_EXPERTISE.items():
            if keyword in cm_lower:
                for s in skills:
                    if s not in seen:
                        expertise.append(s)
                        seen.add(s)
    return expertise
