"""Tests for the persona agent sync (slug map, template, sync engine).

All sync-engine tests write into ``tmp_path`` fixtures — never into the
real ``.opencode/agents`` directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ai_company.agents.slug_map import (
    BUILTIN_AGENT_SLUGS,
    EXECUTIVE_SLUGS,
    AgentSlugCollisionError,
    AgentSlugIndex,
    AgentSlugItem,
    slugify,
)
from ai_company.agents.sync import (
    AgentSyncConfig,
    AgentSyncEngine,
    print_plan_summary,
)
from ai_company.agents.template import (
    AgentRenderContext,
    build_trigger,
    render_agent_markdown,
)

CEO_INSTRUCTIONS = (
    "You are Jack Mlusu, CEO of TestCo. Set strategic direction, lead the "
    "executive team, and communicate with the board."
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def company_fixture(tmp_path: Path) -> Path:
    """A minimal company registry in a temp directory."""
    company_dir = tmp_path / "company"
    _write(
        company_dir / "company.yaml",
        "name: TestCo Vision\n"
        "description: A minimal test company\n"
        "company_name: TestCo Ltd\n"
        "departments:\n"
        "  - executive\n"
        "  - ai\n",
    )
    _write(
        company_dir / "executives.yaml",
        "members:\n"
        "  - name: Jack Mlusu\n"
        "    title: Chief Executive Officer\n"
        "    bio: Visionary enterprise leader.\n"
        "    department: executive\n"
        "    responsibilities:\n"
        "      - Set overall company vision\n"
        "      - Board and investor relations\n"
        "    kpis:\n"
        "      - Revenue Growth\n"
        "    agent_config:\n"
        f"      instructions: >\n        {CEO_INSTRUCTIONS}\n"
        "      tools:\n"
        "        - registry-read\n"
        "        - kpi-dashboard\n"
        "      temperature: 0.2\n"
        "  - name: Jordan Blake\n"
        "    title: Chief Marketing Officer\n"
        "    bio: Growth and brand expert.\n"
        "    department: marketing\n"
        "    agent_config:\n"
        "      instructions: You are Jordan Blake, CMO of TestCo.\n"
        "      temperature: 0.3\n",
    )
    _write(
        company_dir / "specialists.yaml",
        "list:\n"
        "  - name: Dr. Nina Voss\n"
        "    expertise: Natural Language Processing\n"
        "    department: ai\n"
        "    bio: Builds and evaluates LLM-based agent systems.\n",
    )
    _write(
        company_dir / "board.yaml",
        "members:\n  - name: Sarah Chen\n    role: Chairperson\n",
    )
    return company_dir


@pytest.fixture
def engine(company_fixture: Path, tmp_path: Path) -> AgentSyncEngine:
    return AgentSyncEngine(
        config=AgentSyncConfig(
            output_dir=tmp_path / "agents",
            registry_dir=company_fixture,
            config_dir=tmp_path / "config",
        )
    )


def _frontmatter(rendered: str) -> dict[str, object]:
    parts = rendered.split("---", 2)
    assert len(parts) == 3
    block = yaml.safe_load(parts[1])
    assert isinstance(block, dict)
    return block


# ---------------------------------------------------------------------------
# slug_map
# ---------------------------------------------------------------------------


class TestExecutiveSlugs:
    def test_exact_mapping(self) -> None:
        assert EXECUTIVE_SLUGS == {
            "Chief Executive Officer": "ceo",
            "Chief Technology Officer": "cto",
            "Chief Financial Officer": "cfo",
            "Chief Operating Officer": "coo",
            "Chief Marketing Officer": "cmo",
            "Chief AI Officer": "caio",
            "Chief Human Resources Officer": "chro",
            "Chief Legal Officer": "clo",
            "Chief Information Security Officer": "ciso",
            "Chief Information Officer": "cio",
            "Chief Data Officer": "cdo",
            "Chief Strategy Officer": "cso",
            "Chief of Staff": "chief-of-staff",
        }

    def test_covers_thirteen_required_entries(self) -> None:
        assert len(EXECUTIVE_SLUGS) == 13
        required = [
            "Chief Executive Officer",
            "Chief Technology Officer",
            "Chief Financial Officer",
            "Chief Operating Officer",
            "Chief Marketing Officer",
            "Chief AI Officer",
            "Chief Human Resources Officer",
            "Chief Legal Officer",
            "Chief Information Security Officer",
            "Chief Information Officer",
            "Chief Data Officer",
            "Chief Strategy Officer",
            "Chief of Staff",
        ]
        for title in required:
            assert title in EXECUTIVE_SLUGS


class TestSlugify:
    def test_lowercase_hyphenated(self) -> None:
        assert slugify("Dr. Nina Voss") == "dr-nina-voss"
        assert slugify("UX Research & Human Factors") == "ux-research-human-factors"
        assert slugify("Chief of Staff") == "chief-of-staff"
        assert slugify("  Legal & Compliance  ") == "legal-compliance"

    def test_collapses_separators(self) -> None:
        assert (
            slugify("Natural  Language...Processing") == "natural-language-processing"
        )
        assert slugify("Liam O'Connor") == "liam-o-connor"


class TestAgentSlugIndex:
    def test_resolves_in_deterministic_order(self) -> None:
        index = AgentSlugIndex(
            items=[
                AgentSlugItem(name="Jack Mlusu", title="Chief Executive Officer"),
                AgentSlugItem(name="Sarah Chen", title="", role="Chairperson"),
                AgentSlugItem(
                    name="Dr. Nina Voss", title="Natural Language Processing"
                ),
            ]
        )
        assert index.resolved_slugs() == [
            "ceo",
            "chairperson",
            "natural-language-processing",
        ]

    def test_collision_raises_for_duplicate_personas(self) -> None:
        index = AgentSlugIndex(
            items=[
                AgentSlugItem(name="Alice", title="Chief Technology Officer"),
                AgentSlugItem(name="Alice", title="Chief Technology Officer"),
            ]
        )
        with pytest.raises(AgentSlugCollisionError, match="duplicate persona entry"):
            index.raise_for_collisions()

    def test_collision_raises_for_builtin_name(self) -> None:
        index = AgentSlugIndex(items=[AgentSlugItem(name="Bob", title="Build")])
        with pytest.raises(AgentSlugCollisionError, match="built-in opencode agent"):
            index.raise_for_collisions()

    def test_collision_message_lists_all_offenders(self) -> None:
        index = AgentSlugIndex(
            items=[
                AgentSlugItem(name="Build Bot", title="Build"),
                AgentSlugItem(name="Alice", title="Chief Technology Officer"),
                AgentSlugItem(name="Alice", title="Chief Technology Officer"),
            ]
        )
        with pytest.raises(AgentSlugCollisionError) as excinfo:
            index.raise_for_collisions()
        message = str(excinfo.value)
        assert "build" in message
        assert "cto" in message

    def test_different_people_share_role_disambiguated(self) -> None:
        index = AgentSlugIndex(
            items=[
                AgentSlugItem(name="David Park", role="Non-Executive Director"),
                AgentSlugItem(name="Amara Okafor", role="Non-Executive Director"),
            ]
        )
        assert index.resolved_slugs() == [
            "non-executive-director",
            "non-executive-director-amara-okafor",
        ]
        assert index.collisions() == []

    def test_builtin_names_are_guarded(self) -> None:
        for name in BUILTIN_AGENT_SLUGS:
            index = AgentSlugIndex(items=[AgentSlugItem(name="X", title=name)])
            with pytest.raises(AgentSlugCollisionError):
                index.raise_for_collisions()


# ---------------------------------------------------------------------------
# template
# ---------------------------------------------------------------------------


class TestTemplate:
    def _ceo_context(self) -> AgentRenderContext:
        return AgentRenderContext(
            slug="ceo",
            name="Jack Mlusu",
            title="Chief Executive Officer",
            trigger=build_trigger(
                kind="executive", slug="ceo", title="Chief Executive Officer"
            ),
            temperature=0.2,
            instructions=CEO_INSTRUCTIONS,
            kind="executive",
            bio="Visionary enterprise leader.",
            responsibilities=["Set overall company vision", "Board relations"],
            kpis=["Revenue Growth"],
            tools=["registry-read", "kpi-dashboard"],
        )

    def test_valid_frontmatter(self) -> None:
        rendered = render_agent_markdown(self._ceo_context(), "TestCo Ltd")
        frontmatter = _frontmatter(rendered)
        assert frontmatter["name"] == "ceo"
        assert frontmatter["mode"] == "subagent"
        assert frontmatter["temperature"] == 0.2
        assert frontmatter["permission"] == {"edit": "deny", "bash": "deny"}

    def test_contains_ceo_instructions(self) -> None:
        rendered = render_agent_markdown(self._ceo_context(), "TestCo Ltd")
        assert "You are Jack Mlusu, Chief Executive Officer of TestCo Ltd." in rendered
        assert CEO_INSTRUCTIONS in rendered

    def _specialist_context(self) -> AgentRenderContext:
        return AgentRenderContext(
            slug="natural-language-processing",
            name="Dr. Nina Voss",
            title="Natural Language Processing",
            trigger=build_trigger(
                kind="specialist",
                slug="natural-language-processing",
                title="Natural Language Processing",
            ),
            temperature=0.2,
            instructions=(
                "As the company's Natural Language Processing specialist, provide "
                "expert, actionable guidance on Natural Language Processing "
                "across the organization."
            ),
            kind="specialist",
            bio="Builds and evaluates LLM-based agent systems.",
        )

    def _board_context(self) -> AgentRenderContext:
        return AgentRenderContext(
            slug="chairperson",
            name="Sarah Chen",
            title="Chairperson",
            trigger=build_trigger(
                kind="board", slug="chairperson", title="Chairperson"
            ),
            temperature=0.2,
            instructions=(
                "Provide independent board-level oversight and governance as "
                "Chairperson, advising the executive team and representing "
                "shareholder interests."
            ),
            kind="board",
        )

    def test_no_model_line(self) -> None:
        contexts = [
            self._ceo_context(),
            self._specialist_context(),
            self._board_context(),
        ]
        for ctx in contexts:
            rendered = render_agent_markdown(ctx, "TestCo Ltd")
            assert "model:" not in rendered
            assert "model:" not in yaml.safe_dump(_frontmatter(rendered))

    def test_generated_marker(self) -> None:
        rendered = render_agent_markdown(self._ceo_context(), "TestCo Ltd")
        assert (
            "Generated by ai_company.agents — edit the source YAML, not this file."
            in rendered
        )

    def test_description_has_trigger(self) -> None:
        rendered = render_agent_markdown(self._ceo_context(), "TestCo Ltd")
        frontmatter = _frontmatter(rendered)
        description = str(frontmatter["description"])
        assert description.startswith("Jack Mlusu — Chief Executive Officer.")
        assert "Invoke for company-wide vision" in description

    def test_rendering_is_deterministic(self) -> None:
        ctx = self._ceo_context()
        first = render_agent_markdown(ctx, "TestCo Ltd")
        second = render_agent_markdown(ctx, "TestCo Ltd")
        assert first == second


# ---------------------------------------------------------------------------
# sync engine
# ---------------------------------------------------------------------------


class TestSyncEngine:
    def test_first_run_creates_all_files(self, engine: AgentSyncEngine) -> None:
        result = engine.run()
        assert result.errors == []
        assert result.conflicts == []
        assert sorted(result.created) == [
            "ceo",
            "chairperson",
            "cmo",
            "natural-language-processing",
        ]
        output_dir = engine.config.output_dir
        assert output_dir.exists()
        for slug in result.created:
            assert (output_dir / f"{slug}.md").exists()

    def test_second_run_skips_everything(self, engine: AgentSyncEngine) -> None:
        engine.run()
        second = engine.run()
        assert second.created == []
        assert second.updated == []
        assert second.conflicts == []
        assert sorted(second.skipped) == [
            "ceo",
            "chairperson",
            "cmo",
            "natural-language-processing",
        ]

    def test_plan_actions_match_second_run(self, engine: AgentSyncEngine) -> None:
        engine.run()
        plan = engine.plan()
        assert all(e.action == "skip" for e in plan.entries)
        assert plan.counts == {"create": 0, "update": 0, "skip": 4, "conflict": 0}

    def test_edited_file_conflicts_without_force(self, engine: AgentSyncEngine) -> None:
        engine.run()
        target = engine.config.output_dir / "ceo.md"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n# user edit\n", encoding="utf-8"
        )
        result = engine.run()
        assert "ceo" in result.conflicts
        assert "ceo" not in result.created
        assert "ceo" not in result.updated
        assert "# user edit" in target.read_text(encoding="utf-8")

    def test_force_overwrites_edited_file(self, engine: AgentSyncEngine) -> None:
        engine.run()
        target = engine.config.output_dir / "ceo.md"
        target.write_text("completely different content\n", encoding="utf-8")
        forced = AgentSyncEngine(
            config=engine.config.model_copy(update={"force": True})
        )
        result = forced.run()
        assert "ceo" in result.updated
        assert "ceo" not in result.conflicts
        assert "completely different content" not in target.read_text(encoding="utf-8")

    def test_conflict_never_overwrites_silently(self, engine: AgentSyncEngine) -> None:
        engine.run()
        target = engine.config.output_dir / "cmo.md"
        user_content = "user-authored content\n"
        target.write_text(user_content, encoding="utf-8")
        engine.run()
        assert target.read_text(encoding="utf-8") == user_content

    def test_include_departments_is_phase_two(self, engine: AgentSyncEngine) -> None:
        phase_two = AgentSyncEngine(
            config=engine.config.model_copy(update={"include_departments": True})
        )
        with pytest.raises(NotImplementedError, match="Phase 2"):
            phase_two.plan()

    def test_plan_does_not_write(self, engine: AgentSyncEngine) -> None:
        plan = engine.plan()
        assert not engine.config.output_dir.exists()
        assert len(plan.entries) == 4

    def test_plan_summary_is_printable(self, engine: AgentSyncEngine) -> None:
        plan = engine.plan()
        print_plan_summary(plan, dry_run=True)
        print_plan_summary(plan)


# ---------------------------------------------------------------------------
# CLI (python -m ai_company.agents sync)
# ---------------------------------------------------------------------------


class TestCli:
    def test_cli_dry_run_creates_nothing(
        self,
        company_fixture: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)
        # Default scope is "both" — pin the global agents dir to tmp_path so
        # the dry run can never touch the real user-global directory.
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        from ai_company.agents.__main__ import main

        code = main(["sync", "--dry-run"])
        assert code == 0
        assert not (tmp_path / ".opencode" / "agents").exists()
        assert not (tmp_path / ".config" / "opencode" / "agents").exists()
        captured = capsys.readouterr().out
        assert "Dry run" in captured
        assert "ceo" in captured

    def test_cli_sync_writes_files(
        self,
        company_fixture: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        from ai_company.agents.__main__ import main

        code = main(["sync"])
        assert code == 0
        assert (tmp_path / ".opencode" / "agents" / "ceo.md").exists()
        assert (tmp_path / ".opencode" / "agents" / "chairperson.md").exists()
        # Default scope "both" also persists personas globally.
        global_dir = tmp_path / ".config" / "opencode" / "agents"
        assert (global_dir / "ceo.md").exists()
        assert (global_dir / "chairperson.md").exists()
        captured = capsys.readouterr().out
        assert "Sync complete" in captured

    def test_cli_conflicts_exit_nonzero(
        self,
        company_fixture: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        from ai_company.agents.__main__ import main

        assert main(["sync"]) == 0
        edited = tmp_path / ".opencode" / "agents" / "ceo.md"
        edited.write_text("user edit\n", encoding="utf-8")
        assert main(["sync"]) == 1
        assert main(["sync", "--force"]) == 0


# ---------------------------------------------------------------------------
# scope (project / global / both)
# ---------------------------------------------------------------------------


class TestScope:
    def test_default_scope_is_both(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        assert AgentSyncConfig().output_dirs() == [
            Path(".opencode/agents"),
            tmp_path / ".config" / "opencode" / "agents",
        ]

    def test_global_scope_resolves_user_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        config = AgentSyncConfig(scope="global")
        assert config.output_dirs() == [tmp_path / ".config" / "opencode" / "agents"]

    def test_both_scope_returns_project_and_global(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        config = AgentSyncConfig(scope="both")
        assert config.output_dirs() == [
            Path(".opencode/agents"),
            tmp_path / ".config" / "opencode" / "agents",
        ]

    def test_explicit_output_dir_overrides_scope(self, tmp_path: Path) -> None:
        config = AgentSyncConfig(scope="global", output_dir=tmp_path / "custom")
        assert config.output_dirs() == [tmp_path / "custom"]

    def test_global_sync_writes_to_global_dir(
        self,
        company_fixture: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        engine = AgentSyncEngine(
            config=AgentSyncConfig(
                scope="global",
                registry_dir=company_fixture,
                config_dir=tmp_path / "config",
            )
        )
        result = engine.run()
        assert result.errors == []
        assert "ceo" in result.created
        global_dir = tmp_path / ".config" / "opencode" / "agents"
        assert (global_dir / "ceo.md").exists()
        assert not (tmp_path / ".opencode" / "agents").exists()
