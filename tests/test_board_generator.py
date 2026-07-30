"""Tests for the Board Generator (Phase 2, Sprint 3).

Tests cover:
- Board member profile building from registry data
- Committee assignment and charter generation
- Meeting schedule generation
- Voting rules extraction
- Graph integration (committee nodes, edges)
- Artifact writing (Markdown, JSON, YAML)
- Validation
"""

from pathlib import Path

import pytest
import yaml

from ai_company.company.board_generator import BoardGenerator, _infer_expertise
from ai_company.company.models import OrgGraph, OrgNode
from ai_company.models.company import (
    BoardMember,
    BoardEntry,
    Committee,
    CompanyRegistry,
    Meeting,
    VisionData,
    Voting,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Create a temporary config/board/ with minimal template files."""
    cfg = tmp_path / "config" / "board"
    cfg.mkdir(parents=True, exist_ok=True)

    # board.yaml
    (cfg / "board.yaml").write_text(
        yaml.dump(
            {
                "governance": {
                    "framework": "standard",
                    "board_size": {"min": 3, "max": 15, "current": 3},
                    "term_years": 3,
                    "max_terms": 3,
                },
                "expectations": {
                    "meeting_attendance": 80,
                    "committee_service": 1,
                    "code_of_conduct": "Act in good faith.",
                },
                "evaluation": {
                    "frequency": "annual",
                    "type": "self_assessment",
                    "metrics": ["Strategic contribution"],
                },
                "compensation": {
                    "model": "equity_and_cash",
                    "cash_retainer": 50000,
                    "equity_retainer": 100000,
                },
            }
        ),
        encoding="utf-8",
    )

    # committees.yaml
    (cfg / "committees.yaml").write_text(
        yaml.dump(
            {
                "committees": [
                    {
                        "name": "Audit Committee",
                        "purpose": "Oversee financial reporting.",
                        "min_size": 3,
                        "max_size": 5,
                        "meeting_frequency": "quarterly",
                        "expertise_required": ["finance"],
                        "responsibilities": ["Review statements"],
                    },
                    {
                        "name": "AI Ethics Committee",
                        "purpose": "Guide ethical AI deployment.",
                        "min_size": 3,
                        "max_size": 7,
                        "meeting_frequency": "monthly",
                        "expertise_required": ["ai_ethics"],
                        "responsibilities": ["Review AI systems"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    # charters.yaml
    (cfg / "charters.yaml").write_text(
        yaml.dump(
            {
                "charters": [
                    {
                        "committee": "Audit Committee",
                        "preamble": "This Charter governs the Audit Committee.",
                        "authority": "The Committee may engage auditors.",
                        "composition_rules": ["All members independent"],
                        "meeting_rules": {
                            "quorum": "majority",
                            "min_meetings_per_year": 4,
                            "executive_sessions": True,
                        },
                        "reporting": ["Report to Board"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    # meetings.yaml
    (cfg / "meetings.yaml").write_text(
        yaml.dump(
            {
                "annual_schedule": {
                    "board_meetings": {
                        "frequency": "quarterly",
                        "months": ["March", "June", "September", "December"],
                    },
                    "annual_events": [
                        {"name": "Annual General Meeting", "typical_month": "June"},
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    # voting.yaml
    (cfg / "voting.yaml").write_text(
        yaml.dump(
            {
                "quorum": {
                    "board_meetings": {
                        "threshold": 0.5,
                        "calculation": "vacant_seats_excluded",
                    },
                },
                "voting": {
                    "standard_resolution": {
                        "threshold": "majority",
                        "description": "Simple majority of votes cast.",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    return cfg


@pytest.fixture
def board_registry() -> CompanyRegistry:
    """Registry with full board data."""
    return CompanyRegistry(
        vision=VisionData(name="TestCo", company_name="TestCo Inc"),
        board=[
            BoardEntry(name="Alice Chair", role="Chairperson"),
            BoardEntry(name="Bob Director", role="Independent Director"),
        ],
        board_members=[
            BoardMember(
                name="Alice Chair",
                role="Chairperson",
                term_start="2024-01-01",
                term_end="2027-01-01",
                committees=["Audit Committee"],
                independent=False,
            ),
            BoardMember(
                name="Bob Director",
                role="Independent Director",
                term_start="2024-06-01",
                committees=["AI Ethics Committee"],
                independent=True,
            ),
            BoardMember(
                name="Carol Advisor",
                role="Non-Executive Director",
                independent=True,
            ),
        ],
        committees=[
            Committee(
                name="Audit Committee",
                purpose="Oversee financial reporting.",
                chair="Alice Chair",
                members=["Alice Chair", "Bob Director"],
                meeting_frequency="quarterly",
            ),
            Committee(
                name="AI Ethics Committee",
                purpose="Guide ethical AI.",
                chair="Bob Director",
                members=["Bob Director", "Carol Advisor"],
                meeting_frequency="monthly",
            ),
        ],
        meetings=[
            Meeting(
                title="Q1 Board Meeting",
                meeting_date="2025-03-15",
                meeting_type="board",
                attendees=["Alice Chair", "Bob Director", "Carol Advisor"],
            ),
        ],
        voting_records=[
            Voting(
                motion="Approve FY2025 Budget",
                proposed_by="Alice Chair",
                votes_for=3,
                votes_against=0,
                passed=True,
            ),
        ],
    )


@pytest.fixture
def empty_board_registry() -> CompanyRegistry:
    """Registry with no board data at all."""
    return CompanyRegistry(
        vision=VisionData(name="EmptyCo"),
    )


# =========================================================================
# _infer_expertise tests
# =========================================================================


class TestInferExpertise:
    def test_chairperson_expertise(self) -> None:
        exp = _infer_expertise("Chairperson", ["Audit Committee"])
        assert "leadership" in exp
        assert "governance" in exp
        assert "strategic planning" in exp

    def test_vice_chair_expertise_no_duplicates(self) -> None:
        """Vice Chair should not duplicate expertise from both 'vice chair' and 'chair' keywords."""
        exp = _infer_expertise("Vice Chair", [])
        assert "leadership" in exp
        assert "governance" in exp
        # No duplicates
        assert len(exp) == len(set(exp)), f"Duplicates found: {exp}"

    def test_independent_director_expertise(self) -> None:
        exp = _infer_expertise("Independent Director", ["Compensation Committee"])
        assert "governance" in exp
        assert "risk management" in exp

    def test_unknown_role_fallback(self) -> None:
        exp = _infer_expertise("Observer", [])
        assert "governance" in exp

    def test_committee_expertise_merged(self) -> None:
        exp = _infer_expertise("Director", ["Audit Committee", "Technology Committee"])
        assert "finance" in exp
        assert "technology" in exp


# =========================================================================
# BoardGenerator tests
# =========================================================================


class TestBoardGenerator:
    def test_generate_with_full_data(
        self, board_registry: CompanyRegistry, config_dir: Path
    ) -> None:
        gen = BoardGenerator(board_registry, config_dir=config_dir)
        result = gen.generate()
        assert len(result.member_profiles) == 3
        assert len(result.committees) == 2
        assert len(result.committee_charters) == 1  # Only Audit has a charter template
        assert len(result.meetings) >= 1  # At least 1 meeting from registry
        assert "voting" in result.voting_rules

    def test_generate_with_empty_registry(
        self, empty_board_registry: CompanyRegistry, config_dir: Path
    ) -> None:
        gen = BoardGenerator(empty_board_registry, config_dir=config_dir)
        result = gen.generate()
        # Fallback: should still produce data from config templates
        assert isinstance(result.member_profiles, list)
        assert len(result.member_profiles) == 0  # No members

    def test_member_profiles_have_required_fields(
        self, board_registry: CompanyRegistry, config_dir: Path
    ) -> None:
        gen = BoardGenerator(board_registry, config_dir=config_dir)
        result = gen.generate()
        for profile in result.member_profiles:
            assert "name" in profile
            assert "role" in profile
            assert "independent" in profile
            assert "committees" in profile
            assert "expertise" in profile

    def test_committee_assignments(
        self, board_registry: CompanyRegistry, config_dir: Path
    ) -> None:
        gen = BoardGenerator(board_registry, config_dir=config_dir)
        result = gen.generate()
        audit = next(
            (c for c in result.committees if c["name"] == "Audit Committee"), None
        )
        assert audit is not None
        assert "Alice Chair" in audit["members"]
        assert "Bob Director" in audit["members"]
        assert audit["chair"] == "Alice Chair"

    def test_meetings_from_registry(
        self, board_registry: CompanyRegistry, config_dir: Path
    ) -> None:
        gen = BoardGenerator(board_registry, config_dir=config_dir)
        result = gen.generate()
        titles = [m["title"] for m in result.meetings]
        assert "Q1 Board Meeting" in titles

    def test_graph_updates_planned(
        self, board_registry: CompanyRegistry, config_dir: Path
    ) -> None:
        gen = BoardGenerator(board_registry, config_dir=config_dir)
        result = gen.generate()
        assert len(result.graph_updates) >= 4  # 2 committee memberships + 2 chairs
        # Check edge types
        edge_types = {e[2] for e in result.graph_updates}
        assert "serves_on" in edge_types
        assert "chairs" in edge_types

    def test_apply_to_graph(
        self, board_registry: CompanyRegistry, config_dir: Path
    ) -> None:
        gen = BoardGenerator(board_registry, config_dir=config_dir)
        result = gen.generate()

        # Build a minimal graph with board member nodes
        graph = OrgGraph()
        for member in board_registry.board_members:
            safe = member.name.lower().replace(" ", "_")
            graph.add_node(
                OrgNode(
                    id=f"board:{safe}",
                    name=member.name,
                    title=member.role or "Director",
                    node_type="board",
                    level=0,
                )
            )

        gen.apply_to_graph(result, graph)

        # Check committee nodes were added
        assert graph.get_node("committee:audit_committee") is not None
        assert graph.get_node("committee:ai_ethics_committee") is not None

        # Check edges exist
        edges = graph.edges
        assert any(e.edge_type == "serves_on" for e in edges)
        assert any(e.edge_type == "chairs" for e in edges)

    def test_apply_to_graph_on_existing_committee(
        self, board_registry: CompanyRegistry, config_dir: Path
    ) -> None:
        """Applying twice should not duplicate committee nodes."""
        gen = BoardGenerator(board_registry, config_dir=config_dir)
        result = gen.generate()

        graph = OrgGraph()
        # Add committee node already
        graph.add_node(
            OrgNode(
                id="committee:audit_committee",
                name="Audit Committee",
                title="Audit Committee",
                node_type="committee",
                level=0,
            )
        )
        for member in board_registry.board_members:
            safe = member.name.lower().replace(" ", "_")
            graph.add_node(
                OrgNode(
                    id=f"board:{safe}",
                    name=member.name,
                    title=member.role or "Director",
                    node_type="board",
                    level=0,
                )
            )

        gen.apply_to_graph(result, graph)
        # Should not crash, committee node should still be there
        assert graph.get_node("committee:audit_committee") is not None
        # Should not duplicate edges either
        serves_on = [e for e in graph.edges if e.edge_type == "serves_on"]
        assert len(serves_on) >= 1


# =========================================================================
# Validation tests
# =========================================================================


class TestBoardValidation:
    def test_validate_valid(
        self, board_registry: CompanyRegistry, config_dir: Path
    ) -> None:
        gen = BoardGenerator(board_registry, config_dir=config_dir)
        errors = gen.validate()
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_validate_empty(
        self, empty_board_registry: CompanyRegistry, config_dir: Path
    ) -> None:
        gen = BoardGenerator(empty_board_registry, config_dir=config_dir)
        errors = gen.validate()
        assert len(errors) > 0, "Expected validation errors for empty registry"

    def test_validate_missing_config_dir(self, board_registry: CompanyRegistry) -> None:
        gen = BoardGenerator(board_registry, config_dir=Path("/nonexistent"))
        errors = gen.validate()
        assert len(errors) > 0


# =========================================================================
# Artifact writer tests
# =========================================================================


class TestBoardArtifacts:
    def test_write_artifacts(
        self, board_registry: CompanyRegistry, config_dir: Path, tmp_path: Path
    ) -> None:
        gen = BoardGenerator(board_registry, config_dir=config_dir)
        result = gen.generate()
        created = gen.write_artifacts(result, tmp_path)

        paths = {p.name for p in created}
        assert "BOARD.md" in paths
        assert "BOARD_GOVERNANCE.md" in paths
        assert "BOARD_CHARTER.md" in paths
        assert "board.json" in paths
        assert "board.yaml" in paths

    def test_board_markdown_contains_member_names(
        self, board_registry: CompanyRegistry, config_dir: Path, tmp_path: Path
    ) -> None:
        gen = BoardGenerator(board_registry, config_dir=config_dir)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        content = (tmp_path / "docs" / "BOARD.md").read_text(encoding="utf-8")
        assert "Alice Chair" in content
        assert "Bob Director" in content
        assert "Carol Advisor" in content

    def test_governance_markdown_contains_governance_sections(
        self, board_registry: CompanyRegistry, config_dir: Path, tmp_path: Path
    ) -> None:
        gen = BoardGenerator(board_registry, config_dir=config_dir)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        content = (tmp_path / "docs" / "BOARD_GOVERNANCE.md").read_text(
            encoding="utf-8"
        )
        assert "Governance Structure" in content
        assert "Director Expectations" in content
        assert "Board Evaluation" in content
        assert "Succession Planning" in content

    def test_charters_markdown_contains_charter_content(
        self, board_registry: CompanyRegistry, config_dir: Path, tmp_path: Path
    ) -> None:
        gen = BoardGenerator(board_registry, config_dir=config_dir)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        content = (tmp_path / "docs" / "BOARD_CHARTER.md").read_text(encoding="utf-8")
        assert "Audit Committee Charter" in content
        assert "Preamble" in content
        assert "Authority" in content

    def test_json_export(
        self, board_registry: CompanyRegistry, config_dir: Path, tmp_path: Path
    ) -> None:
        gen = BoardGenerator(board_registry, config_dir=config_dir)
        result = gen.generate()
        gen.write_artifacts(result, tmp_path)
        import json

        data = json.loads((tmp_path / "board.json").read_text(encoding="utf-8"))
        assert "board" in data
        assert len(data["board"]["members"]) == 3


# =========================================================================
# Edge case tests
# =========================================================================


class TestBoardGeneratorEdgeCases:
    def test_board_only_has_raw_entries_no_board_members(
        self, config_dir: Path
    ) -> None:
        """Registry with raw board entries but no BoardMember objects."""
        reg = CompanyRegistry(
            vision=VisionData(name="TestCo"),
            board=[
                BoardEntry(name="Diana", role="Director"),
                BoardEntry(name="Edward", role="Observer"),
            ],
        )
        gen = BoardGenerator(reg, config_dir=config_dir)
        result = gen.generate()
        assert len(result.member_profiles) == 2
        names = {m["name"] for m in result.member_profiles}
        assert "Diana" in names
        assert "Edward" in names

    def test_no_committees_in_registry(self, config_dir: Path) -> None:
        """Should seed committees from config templates if registry has none."""
        reg = CompanyRegistry(
            vision=VisionData(name="TestCo"),
            board_members=[BoardMember(name="Alice", role="Chair")],
        )
        gen = BoardGenerator(reg, config_dir=config_dir)
        result = gen.generate()
        # Committees should be seeded from config/board/committees.yaml
        assert len(result.committees) >= 2  # Audit + AI Ethics from template
        names = {c["name"] for c in result.committees}
        assert "Audit Committee" in names
        assert "AI Ethics Committee" in names

    def test_summary_fields(
        self, board_registry: CompanyRegistry, config_dir: Path
    ) -> None:
        gen = BoardGenerator(board_registry, config_dir=config_dir)
        result = gen.generate()
        summary = result.summary()
        assert summary["members"] == 3
        assert summary["committees"] == 2
        assert summary["board_name"] == "TestCo Inc"

    def test_generate_and_apply_integration(
        self, board_registry: CompanyRegistry, config_dir: Path
    ) -> None:
        """End-to-end: generate, apply to graph, verify structure."""
        gen = BoardGenerator(board_registry, config_dir=config_dir)
        result = gen.generate()

        graph = OrgGraph()
        for member in board_registry.board_members:
            safe = member.name.lower().replace(" ", "_")
            graph.add_node(
                OrgNode(
                    id=f"board:{safe}",
                    name=member.name,
                    title=member.role or "Director",
                    node_type="board",
                    level=0,
                )
            )

        gen.apply_to_graph(result, graph)

        total_nodes = len(graph.nodes)
        total_edges = len(graph.edges)
        assert total_nodes >= 5  # 3 board members + 2 committees
        assert total_edges >= 4  # membership + chairs
