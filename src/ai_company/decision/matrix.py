"""Decision matrix for evaluating options in the AI Enterprise OS Decision Engine."""

from __future__ import annotations

import logging
from typing import Any, cast

from ai_company.decision.models import Decision


class DecisionMatrix:
    """Matrix for evaluating decision options against criteria."""

    def __init__(self) -> None:
        self.criteria: dict[str, dict[str, Any]] = {}
        self.logger = logging.getLogger(self.__class__.__name__)

    def add_criterion(
        self,
        name: str,
        weight: float = 1.0,
        description: str = "",
        is_beneficial: bool = True,
    ) -> None:
        """Add a criterion to the matrix."""
        self.criteria[name] = {
            "weight": weight,
            "description": description,
            "is_beneficial": is_beneficial,
        }

    def evaluate(
        self,
        options: list[dict[str, Any]],
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Evaluate options against the decision matrix.

        Args:
            options: List of option dicts with criteria scores
            weights: Optional weight overrides

        Returns:
            Evaluation results with scores and ranking
        """
        if not self.criteria:
            return {"scores": {}, "ranking": [], "method": "no_criteria"}

        effective_weights = weights or {
            name: c["weight"] for name, c in self.criteria.items()
        }

        scores: dict[str, float] = {}
        details: dict[str, dict[str, Any]] = {}

        for option in options:
            option_id = option.get("id", str(hash(str(option))))
            total_score = 0.0
            criterion_scores: dict[str, float] = {}

            for criterion_name, criterion_config in self.criteria.items():
                raw_score = option.get(criterion_name, 0)
                weight = effective_weights.get(
                    criterion_name, criterion_config["weight"]
                )

                if not criterion_config["is_beneficial"]:
                    raw_score = 1.0 - raw_score

                weighted_score = raw_score * weight
                criterion_scores[criterion_name] = weighted_score
                total_score += weighted_score

            scores[option_id] = total_score
            details[option_id] = {
                "criterion_scores": criterion_scores,
                "total_score": total_score,
                "option_data": option,
            }

        ranking = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)

        return {
            "scores": scores,
            "ranking": ranking,
            "details": details,
            "method": "weighted_sum",
            "criteria_used": list(self.criteria.keys()),
        }

    def evaluate_decision(
        self,
        decision: Decision,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Evaluate options in a decision object."""
        return self.evaluate(decision.options, weights)

    def get_top_option(
        self,
        options: list[dict[str, Any]],
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any] | None:
        """Get the top-ranked option."""
        results = self.evaluate(options, weights)
        if results["ranking"]:
            top_id = results["ranking"][0]
            for opt in options:
                if opt.get("id") == top_id:
                    return opt
        return None

    def get_option_score(
        self,
        option: dict[str, Any],
        weights: dict[str, float] | None = None,
    ) -> float:
        """Get the score for a single option."""
        results = self.evaluate([option], weights)
        option_id = option.get("id", str(hash(str(option))))
        return cast(float, results["scores"].get(option_id, 0.0))
