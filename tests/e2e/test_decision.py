"""Decision engine e2e tests."""

from ai_company.decision.engine import DecisionCategory, DecisionEngine


class TestE2EDecision:
    def test_decision_engine_creates(self) -> None:
        engine = DecisionEngine()
        assert engine is not None

    def test_create_decision(self) -> None:
        engine = DecisionEngine()
        d = engine.create_decision(
            title="Test Decision",
            description="A test decision",
            category="strategic",
            priority="high",
        )
        assert d.id is not None
        assert d.title == "Test Decision"
        assert d.status.value == "pending"

    def test_decision_has_risk_score(self) -> None:
        engine = DecisionEngine()
        d = engine.create_decision(
            title="Risk Test", description="Testing risk scoring"
        )
        assert d.risk_score is not None

    def test_make_decision(self) -> None:
        engine = DecisionEngine()
        d = engine.create_decision(
            title="Approve Test",
            description="Testing approval",
            options=[{"id": "opt1", "name": "Option 1"}],
        )
        resolved = engine.make_decision(d, "opt1", "Best choice", approved_by="CEO")
        assert resolved.status.value == "approved"
        assert resolved.selected_option == "opt1"

    def test_escalate_decision(self) -> None:
        engine = DecisionEngine()
        d = engine.create_decision(title="Escalate Test", description="Test escalation")
        escalated = engine.escalate(d, "Needs higher authority")
        assert escalated.status.value == "escalated"

    def test_defer_decision(self) -> None:
        engine = DecisionEngine()
        d = engine.create_decision(title="Defer Test", description="Test deferral")
        deferred = engine.defer(d, "Need more info", "2026-08-01")
        assert deferred.status.value == "deferred"

    def test_cancel_decision(self) -> None:
        engine = DecisionEngine()
        d = engine.create_decision(title="Cancel Test", description="Test cancel")
        cancelled = engine.cancel(d, "No longer needed")
        assert cancelled.status.value == "cancelled"

    def test_decision_statistics(self) -> None:
        engine = DecisionEngine()
        stats = engine.get_statistics()
        assert "total_decisions" in stats
        assert "by_status" in stats

    def test_list_decisions(self) -> None:
        engine = DecisionEngine()
        engine.create_decision(title="List Test 1", description="Test listing")
        engine.create_decision(title="List Test 2", description="More listing")
        decisions = engine.list_decisions(limit=10)
        assert len(decisions) >= 2

    def test_decision_categories(self) -> None:
        cats = [c.value for c in DecisionCategory]
        for expected in ["strategic", "operational", "financial", "technical"]:
            assert expected in cats
