"""Risk scoring module for AI Enterprise OS Decision Engine."""

from __future__ import annotations

import logging
from typing import Any

from ai_company.decision.models import Decision, DecisionCategory


class RiskFactor:
    """A single risk factor evaluated during risk assessment."""

    def __init__(
        self,
        name: str,
        weight: float = 1.0,
        description: str = "",
        category: str = "general",
    ) -> None:
        self.name = name
        self.weight = weight
        self.description = description
        self.category = category


class RiskScorer:
    """Scores risk for decisions based on multiple factors."""

    def __init__(self) -> None:
        self.factors: list[RiskFactor] = []
        self.logger = logging.getLogger(self.__class__.__name__)
        self._register_default_factors()

    def _register_default_factors(self) -> None:
        """Register default risk factors."""
        self.factors = [
            RiskFactor(
                "financial_impact", 3.0, "Financial impact of decision", "financial"
            ),
            RiskFactor(
                "compliance_risk", 4.0, "Regulatory and compliance risk", "compliance"
            ),
            RiskFactor("reputation_risk", 2.5, "Reputation impact", "strategic"),
            RiskFactor(
                "operational_impact", 2.0, "Impact on operations", "operational"
            ),
            RiskFactor(
                "technical_complexity",
                1.5,
                "Technical implementation risk",
                "technical",
            ),
            RiskFactor("stakeholder_impact", 2.0, "Impact on stakeholders", "social"),
            RiskFactor("time_pressure", 1.0, "Time constraints", "operational"),
            RiskFactor(
                "data_security", 4.5, "Data security implications", "compliance"
            ),
        ]

    def add_factor(self, factor: RiskFactor) -> None:
        """Add a custom risk factor."""
        self.factors.append(factor)

    def calculate(self, decision: Decision) -> float:
        """Calculate risk score for a decision (0.0 to 1.0).

        Args:
            decision: Decision to evaluate

        Returns:
            Risk score between 0.0 (low risk) and 1.0 (high risk)
        """
        if not self.factors:
            return 0.0

        total_weight = sum(f.weight for f in self.factors)
        if total_weight == 0:
            return 0.0

        weighted_score = 0.0

        for factor in self.factors:
            score = self._evaluate_factor(factor, decision)
            weighted_score += score * factor.weight

        return min(1.0, weighted_score / total_weight)

    def identify_factors(self, decision: Decision) -> list[str]:
        """Identify top risk factors for a decision."""
        factor_scores: list[tuple[str, float]] = []

        for factor in self.factors:
            score = self._evaluate_factor(factor, decision)
            if score > 0.5:
                factor_scores.append((factor.name, score))

        factor_scores.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in factor_scores[:5]]

    def get_factor_details(self, decision: Decision) -> dict[str, dict[str, Any]]:
        """Get detailed scoring for each factor."""
        details = {}

        for factor in self.factors:
            score = self._evaluate_factor(factor, decision)
            details[factor.name] = {
                "score": score,
                "weight": factor.weight,
                "description": factor.description,
                "category": factor.category,
                "contribution": score * factor.weight,
            }

        return details

    def _evaluate_factor(self, factor: RiskFactor, decision: Decision) -> float:
        """Evaluate a single risk factor for a decision."""
        context = decision.context or {}

        # Base risk on decision priority
        base_risk = decision.priority.value / 5.0

        # Adjust based on category-specific factors
        if factor.category == "financial":
            budget = context.get("budget", 0)
            if budget > 100000:
                base_risk += 0.3
            elif budget > 50000:
                base_risk += 0.2
            elif budget > 10000:
                base_risk += 0.1

        elif factor.category == "compliance":
            if decision.category == DecisionCategory.COMPLIANCE:
                base_risk += 0.4
            if decision.category == DecisionCategory.GOVERNANCE:
                base_risk += 0.3

        elif factor.category == "strategic":
            if decision.category == DecisionCategory.STRATEGIC:
                base_risk += 0.3

        # Check for risk-related context
        risk_context = context.get("risk_factors", [])
        if isinstance(risk_context, list):
            if factor.name in risk_context:
                base_risk += 0.2

        return min(1.0, base_risk)
