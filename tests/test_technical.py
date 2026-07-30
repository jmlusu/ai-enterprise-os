"""Tests for the 16 new Pydantic models introduced in Sprint 2."""

from pydantic import ValidationError

from ai_company.models.company import (
    KPI,
    Agent,
    BoardMember,
    Budget,
    Committee,
    Culture,
    Decision,
    Governance,
    Integration,
    Meeting,
    Permission,
    Policy,
    Risk,
    Strategy,
    Tool,
    Voting,
)


class TestBoardMember:
    def test_minimal(self) -> None:
        bm = BoardMember(name="Alice")
        assert bm.name == "Alice"
        assert bm.role == ""
        assert bm.independent is False
        assert bm.committees == []

    def test_full(self) -> None:
        bm = BoardMember(
            name="Bob",
            role="Chair",
            term_start="2026-01-01",
            term_end="2028-12-31",
            committees=["Audit", "Compensation"],
            independent=True,
        )
        assert bm.role == "Chair"
        assert bm.independent is True
        assert len(bm.committees) == 2


class TestCommittee:
    def test_minimal(self) -> None:
        c = Committee(name="Audit")
        assert c.name == "Audit"
        assert c.meeting_frequency == "monthly"
        assert c.members == []

    def test_full(self) -> None:
        c = Committee(
            name="Compensation",
            purpose="Set executive pay",
            chair="Alice",
            members=["Bob", "Carol"],
            meeting_frequency="quarterly",
        )
        assert c.purpose == "Set executive pay"
        assert c.chair == "Alice"
        assert len(c.members) == 2


class TestMeeting:
    def test_minimal(self) -> None:
        m = Meeting(title="Standup")
        assert m.title == "Standup"
        assert m.meeting_type == "standup"
        assert m.attendees == []

    def test_full(self) -> None:
        m = Meeting(
            title="Board Review",
            meeting_date="2026-07-29",
            meeting_type="board",
            attendees=["Alice", "Bob"],
            minutes="Reviewed Q2 results",
            action_items=["Send report", "Schedule follow-up"],
        )
        assert len(m.action_items) == 2
        assert m.minutes == "Reviewed Q2 results"


class TestVoting:
    def test_minimal(self) -> None:
        v = Voting(motion="Approve budget")
        assert v.motion == "Approve budget"
        assert v.passed is False
        assert v.votes_for == 0

    def test_passed(self) -> None:
        v = Voting(
            motion="Hire new CTO",
            proposed_by="Board Chair",
            seconds_by="CEO",
            votes_for=7,
            votes_against=1,
            votes_abstain=1,
            passed=True,
            vote_date="2026-06-15",
        )
        assert v.passed is True
        assert v.votes_for == 7
        assert v.vote_date == "2026-06-15"


class TestAgent:
    def test_minimal(self) -> None:
        a = Agent(name="Helper")
        assert a.name == "Helper"
        assert a.tools == []

    def test_full(self) -> None:
        a = Agent(
            name="CodeAgent",
            role="Developer",
            model="gpt-4",
            instructions="Write Python code",
            tools=["python", "git"],
            department="technical",
        )
        assert a.model == "gpt-4"
        assert len(a.tools) == 2
        assert a.department == "technical"


class TestPolicy:
    def test_minimal(self) -> None:
        p = Policy(name="Test Policy")
        assert p.name == "Test Policy"
        assert p.version == "1.0.0"
        assert p.rules == []

    def test_full(self) -> None:
        p = Policy(
            name="Security",
            description="Security rules",
            scope="All systems",
            version="2.1.0",
            effective_date="2026-01-01",
            owner="CISO",
            rules=["Use MFA", "Audit logs"],
        )
        assert p.scope == "All systems"
        assert len(p.rules) == 2


class TestBudget:
    def test_minimal(self) -> None:
        b = Budget(department="eng")
        assert b.department == "eng"
        assert b.total == 0.0
        assert b.currency == "USD"

    def test_full(self) -> None:
        b = Budget(
            department="technical",
            fiscal_year="2026",
            total=1000000.0,
            spent=250000.0,
            currency="USD",
            categories={"cloud": 500000.0, "tools": 500000.0},
        )
        assert b.total == 1000000.0
        assert b.categories["cloud"] == 500000.0


class TestKPI:
    def test_minimal(self) -> None:
        k = KPI(name="Uptime", target=99.9)
        assert k.name == "Uptime"
        assert k.target == 99.9
        assert k.current == 0.0
        assert k.trend == "flat"

    def test_full(self) -> None:
        k = KPI(
            name="Coverage",
            target=95.0,
            current=78.0,
            unit="percent",
            owner="CTO",
            frequency="monthly",
            trend="up",
        )
        assert k.current == 78.0
        assert k.owner == "CTO"

    def test_invalid_trend(self) -> None:
        try:
            KPI(name="Bad", target=1, trend="sideways")
            assert False, "Should have raised"
        except ValidationError:
            pass


class TestRisk:
    def test_minimal(self) -> None:
        r = Risk(description="Data breach")
        assert r.description == "Data breach"
        assert r.impact == "medium"
        assert r.status == "open"

    def test_full(self) -> None:
        r = Risk(
            description="Cloud outage",
            impact="high",
            likelihood="low",
            mitigation="Multi-region HA",
            owner="Infra Team",
            status="mitigated",
        )
        assert r.impact == "high"
        assert r.status == "mitigated"


class TestDecision:
    def test_minimal(self) -> None:
        d = Decision(title="Use Python")
        assert d.title == "Use Python"
        assert d.stakeholders == []

    def test_full(self) -> None:
        d = Decision(
            title="Migrate to k8s",
            date="2026-07-01",
            author="CTO",
            rationale="Scalability and portability",
            outcome="Approved with conditions",
            stakeholders=["Eng", "Ops"],
        )
        assert d.rationale == "Scalability and portability"
        assert len(d.stakeholders) == 2


class TestPermission:
    def test_minimal(self) -> None:
        p = Permission(resource="db")
        assert p.resource == "db"
        assert p.actions == ["read"]

    def test_full(self) -> None:
        p = Permission(
            resource="admin-api",
            role="admin",
            actions=["read", "write", "delete"],
            constraints="Requires MFA",
        )
        assert "delete" in p.actions
        assert p.constraints == "Requires MFA"


class TestIntegration:
    def test_minimal(self) -> None:
        i = Integration(name="GitHub")
        assert i.name == "GitHub"
        assert i.status == "active"
        assert i.config == {}

    def test_full(self) -> None:
        i = Integration(
            name="Slack",
            type="webhook",
            version="2.0.0",
            config={"token": "xyz"},
            status="active",
        )
        assert i.config["token"] == "xyz"


class TestTool:
    def test_minimal(self) -> None:
        t = Tool(name="VS Code")
        assert t.name == "VS Code"
        assert t.access_roles == []

    def test_full(self) -> None:
        t = Tool(
            name="Docker",
            purpose="Containerization",
            category="infrastructure",
            config={"version": "24.0"},
            access_roles=["dev", "ops"],
        )
        assert t.category == "infrastructure"
        assert len(t.access_roles) == 2


class TestGovernance:
    def test_defaults(self) -> None:
        g = Governance()
        assert g.framework == "standard"
        assert g.policies == []
        assert g.review_cycle == "quarterly"

    def test_full(self) -> None:
        g = Governance(
            framework="MAGF v1",
            policies=["AI Safety", "Data Privacy"],
            controls=["Audit log", "Approval chain"],
            compliance_standards=["SOC 2", "GDPR"],
            review_cycle="monthly",
        )
        assert len(g.policies) == 2
        assert "SOC 2" in g.compliance_standards


class TestStrategy:
    def test_defaults(self) -> None:
        s = Strategy(name="Growth")
        assert s.name == "Growth"
        assert s.status == "draft"
        assert s.objectives == []

    def test_full(self) -> None:
        s = Strategy(
            name="Market Expansion",
            description="Expand to new markets",
            objectives=["Launch in EU", "Hire local team"],
            metrics=["Revenue", "Market share"],
            timeline="2026-2027",
            owner="CEO",
            status="active",
        )
        assert len(s.objectives) == 2
        assert s.status == "active"


class TestCulture:
    def test_defaults(self) -> None:
        c = Culture()
        assert c.values == []
        assert c.behaviors == []
        assert c.rituals == []

    def test_full(self) -> None:
        c = Culture(
            values=["Transparency", "Ownership"],
            behaviors=["Write things down", "Default to open"],
            norms=["Async-first", "Blameless post-mortems"],
            rituals=["Monday sync", "Friday demos"],
        )
        assert len(c.values) == 2
        assert "Monday sync" in c.rituals


class TestSerialization:
    def test_board_member_yaml_roundtrip(self, tmp_path: str) -> None:
        import yaml

        bm = BoardMember(name="Alice", role="Chair", committees=["Audit"])
        data = bm.model_dump()
        yaml_str = yaml.dump(data)
        loaded = yaml.safe_load(yaml_str)
        restored = BoardMember(**loaded)
        assert restored.name == "Alice"
        assert restored.committees == ["Audit"]

    def test_strategy_json_roundtrip(self) -> None:
        import json

        s = Strategy(
            name="Growth",
            objectives=["Obj1", "Obj2"],
            status="active",
        )
        data = s.model_dump()
        json_str = json.dumps(data)
        loaded = json.loads(json_str)
        restored = Strategy(**loaded)
        assert restored.name == "Growth"
        assert len(restored.objectives) == 2
        assert restored.status == "active"
