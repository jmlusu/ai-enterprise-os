"""Tests for the enriched executive team functionality."""

from pathlib import Path


from ai_company.generator.context import GeneratorContext
from ai_company.generator.prompt_generator import PromptGenerator
from ai_company.models.company import (
    Agent,
    CompanyManifest,
    CompanyRegistry,
    ExecutiveAgentConfig,
    ExecutiveEntry,
    KPI,
    Budget,
    VisionData,
)
from ai_company.registry.registry import RegistryEngine


class TestExecutiveAgentConfig:
    def test_defaults(self) -> None:
        ac = ExecutiveAgentConfig()
        assert ac.model == "gpt-4o"
        assert ac.tools == ["registry-read", "kpi-dashboard", "budget-view"]
        assert ac.temperature == 0.0
        assert ac.department_scope == []

    def test_full(self) -> None:
        ac = ExecutiveAgentConfig(
            model="gpt-4-turbo",
            instructions="Custom instructions",
            tools=["tool-a", "tool-b"],
            temperature=0.5,
            department_scope=["eng", "platform"],
        )
        assert ac.model == "gpt-4-turbo"
        assert len(ac.tools) == 2
        assert ac.temperature == 0.5
        assert "eng" in ac.department_scope


class TestExecutiveEntry:
    def test_minimal(self) -> None:
        ex = ExecutiveEntry(name="Alice")
        assert ex.name == "Alice"
        assert ex.title is None
        assert ex.bio == ""
        assert ex.department == ""
        assert ex.responsibilities == []
        assert ex.kpis == []
        assert ex.budget_authority == 0.0
        assert ex.direct_reports == []
        assert ex.reports_to == ""
        assert ex.status == "active"
        assert ex.start_date == ""
        assert ex.email == ""
        assert isinstance(ex.agent_config, ExecutiveAgentConfig)

    def test_full(self) -> None:
        ac = ExecutiveAgentConfig(
            model="gpt-4o",
            instructions="Run the company",
            tools=["registry-read", "kpi-dashboard"],
            temperature=0.2,
            department_scope=["general"],
        )
        ex = ExecutiveEntry(
            name="Alice",
            title="CEO",
            bio="Seasoned executive",
            department="general",
            responsibilities=["Set strategy", "Lead team"],
            kpis=["Revenue", "Growth"],
            budget_authority=5000000.0,
            direct_reports=["Bob", "Carol"],
            reports_to="Board",
            status="active",
            start_date="2023-01-01",
            email="alice@company.io",
            agent_config=ac,
        )
        assert ex.title == "CEO"
        assert ex.bio == "Seasoned executive"
        assert ex.budget_authority == 5000000.0
        assert len(ex.direct_reports) == 2
        assert ex.agent_config.model == "gpt-4o"
        assert "registry-read" in ex.agent_config.tools

    def test_agent_config_defaults(self) -> None:
        """ExecutiveEntry should create a default ExecutiveAgentConfig."""
        ex = ExecutiveEntry(name="Bob", title="CTO")
        assert ex.agent_config.model == "gpt-4o"
        assert "registry-read" in ex.agent_config.tools


class TestRegistryExecutiveAgents:
    def test_executive_agents_populated_from_executives(self) -> None:
        """RegistryEngine should create Agent instances from executive agent_config."""
        engine = RegistryEngine()
        result = engine.load(Path("company"), config_dir=Path("config/company"))
        assert result.registry is not None
        assert result.success

        reg = result.registry
        assert len(reg.executives) > 0
        assert len(reg.executive_agents) > 0

        # Check that executive_agents are Agent instances
        for agent in reg.executive_agents:
            assert isinstance(agent, Agent)
            assert agent.name.endswith(" Agent")
            assert agent.model  # should have a model

        # Check that the CEO agent exists
        ceo_agent = next(
            (
                a
                for a in reg.executive_agents
                if "Executive" in a.role and "Officer" in a.role
            ),
            None,
        )
        assert ceo_agent is not None
        assert ceo_agent.model == "gpt-4o"


class TestExecutivePromptGeneration:
    def _make_context(self) -> GeneratorContext:
        manifest = CompanyManifest(
            name="TestCo",
            company_name="TestCo Inc",
            description="A test company",
            departments=[],
        )
        registry = CompanyRegistry(
            vision=VisionData(name="TVision", company_name="TestCo Inc"),
            executives=[
                ExecutiveEntry(
                    name="Alice",
                    title="CEO",
                    bio="Test bio",
                    department="general",
                    responsibilities=["Strategy", "Leadership"],
                    kpis=["Revenue Growth"],
                    budget_authority=5000000.0,
                    direct_reports=["Bob"],
                    reports_to="Board",
                    email="alice@test.com",
                )
            ],
            kpis=[
                KPI(
                    name="Revenue Growth",
                    target=100.0,
                    current=85.0,
                    unit="M",
                    owner="CEO",
                ),
            ],
            budgets=[
                Budget(
                    department="general",
                    total=5000000.0,
                    spent=2000000.0,
                    currency="USD",
                ),
            ],
        )
        return GeneratorContext(manifest, registry)

    def test_prompt_contains_bio(self) -> None:
        ctx = self._make_context()
        gen = PromptGenerator(ctx)
        prompt = gen.generate_executive_prompt("Alice")
        assert "Test bio" in prompt

    def test_prompt_contains_kpis(self) -> None:
        ctx = self._make_context()
        gen = PromptGenerator(ctx)
        prompt = gen.generate_executive_prompt("Alice")
        assert "Revenue Growth" in prompt
        assert "85.0" in prompt

    def test_prompt_contains_budget(self) -> None:
        ctx = self._make_context()
        gen = PromptGenerator(ctx)
        prompt = gen.generate_executive_prompt("Alice")
        assert "5,000,000" in prompt

    def test_prompt_contains_direct_reports(self) -> None:
        ctx = self._make_context()
        gen = PromptGenerator(ctx)
        prompt = gen.generate_executive_prompt("Alice")
        assert "Bob" in prompt

    def test_prompt_contains_agent_config(self) -> None:
        ctx = self._make_context()
        gen = PromptGenerator(ctx)
        prompt = gen.generate_executive_prompt("Alice")
        assert "gpt-4o" in prompt
        assert "registry-read" in prompt


class TestExecutiveContextSerialization:
    def test_executives_serialized_with_new_fields(self) -> None:
        manifest = CompanyManifest(
            name="TestCo",
            company_name="TestCo Inc",
            description="Test",
            departments=[],
        )
        registry = CompanyRegistry(
            vision=VisionData(name="TVision"),
            executives=[
                ExecutiveEntry(
                    name="Alice",
                    title="CEO",
                    bio="Bio text",
                    department="general",
                    responsibilities=["R1", "R2"],
                    kpis=["KPI1"],
                    budget_authority=1000000.0,
                    direct_reports=["Bob"],
                    reports_to="Board",
                    email="alice@test.com",
                )
            ],
        )
        ctx = GeneratorContext(manifest, registry)
        d = ctx.to_dict()

        execs = d["company"]["executives"]
        assert len(execs) == 1
        ex = execs[0]
        assert ex["name"] == "Alice"
        assert ex["title"] == "CEO"
        assert ex["bio"] == "Bio text"
        assert ex["department"] == "general"
        assert ex["responsibilities"] == ["R1", "R2"]
        assert ex["kpis"] == ["KPI1"]
        assert ex["budget_authority"] == 1000000.0
        assert ex["direct_reports"] == ["Bob"]
        assert ex["reports_to"] == "Board"
        assert ex["email"] == "alice@test.com"

    def test_executive_agents_serialized(self) -> None:
        manifest = CompanyManifest(
            name="TestCo",
            company_name="TestCo Inc",
            description="Test",
            departments=[],
        )
        registry = CompanyRegistry(
            vision=VisionData(name="TVision"),
            executives=[ExecutiveEntry(name="Alice", title="CEO")],
        )
        ctx = GeneratorContext(manifest, registry)
        d = ctx.to_dict()

        # executive_agents should be present in the dict
        assert "executive_agents" in d["company"]
        # Since no Agent instances were explicitly set, it should be empty
        assert d["company"]["executive_agents"] == []
