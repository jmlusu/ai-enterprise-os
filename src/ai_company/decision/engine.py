"""Decision engine for AI Enterprise OS.

Manages decision-making processes including approval routing, escalation,
risk scoring, explainability, and decision history persistence.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ai_company.decision.approval import ApprovalMatrix, ApprovalRouter
from ai_company.decision.history import DecisionHistory
from ai_company.decision.matrix import DecisionMatrix
from ai_company.decision.models import (
    Decision,
    DecisionCategory,
    DecisionPriority,
    DecisionStatus,
)
from ai_company.decision.policy import PolicyEngine
from ai_company.decision.risk import RiskScorer
from ai_company.decision.routing import RoutingTable


class DecisionEngine:
    """Core engine for making, tracking, and auditing decisions.

    This engine:
    1. Creates and manages decisions with full audit trails
    2. Routes decisions through approval workflows
    3. Calculates risk scores for decisions
    4. Explains reasoning behind decisions
    5. Persists decision history for accountability
    6. Supports escalation workflows
    7. Enforces policy constraints

    Args:
        decision_matrix: Matrix for evaluating decision options
        approval_matrix: Matrix for determining approval requirements
        approval_router: Router for directing approval requests
        risk_scorer: Scorer for calculating decision risk
        policy_engine: Engine for enforcing policies
        decision_history: History manager for persisting decisions
        routing_table: Table for routing decisions
    """

    def __init__(
        self,
        decision_matrix: DecisionMatrix | None = None,
        approval_matrix: ApprovalMatrix | None = None,
        approval_router: ApprovalRouter | None = None,
        risk_scorer: RiskScorer | None = None,
        policy_engine: PolicyEngine | None = None,
        decision_history: DecisionHistory | None = None,
        routing_table: RoutingTable | None = None,
    ) -> None:
        self.decision_matrix = decision_matrix or DecisionMatrix()
        self.approval_matrix = approval_matrix or ApprovalMatrix()
        self.approval_router = approval_router or ApprovalRouter()
        self.risk_scorer = risk_scorer or RiskScorer()
        self.policy_engine = policy_engine or PolicyEngine()
        self.decision_history = decision_history or DecisionHistory()
        self.routing_table = routing_table or RoutingTable()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._decision_counter = 0

    def create_decision(
        self,
        title: str,
        description: str,
        category: str | DecisionCategory = DecisionCategory.OTHER,
        priority: str | DecisionPriority = DecisionPriority.MEDIUM,
        requester: str = "",
        owner: str = "",
        stakeholders: list[str] | None = None,
        options: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Decision:
        """Create a new decision.

        Args:
            title: Decision title
            description: Decision description
            category: Decision category
            priority: Decision priority
            requester: Person/system requesting the decision
            owner: Person/system responsible for the decision
            stakeholders: List of stakeholders
            options: List of available options
            context: Decision context data
            tags: Tags for categorization
            metadata: Additional metadata

        Returns:
            Created Decision
        """
        self._decision_counter += 1
        decision_id = f"decision_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._decision_counter:04d}"

        if isinstance(category, str):
            category = DecisionCategory(category)
        if isinstance(priority, str):
            try:
                # Try by member name (e.g. "high" → DecisionPriority.HIGH)
                priority = DecisionPriority[priority.upper()]
            except KeyError:
                # Fall back to value lookup (e.g. "3" → DecisionPriority.HIGH)
                priority = DecisionPriority(int(priority))  # type: ignore[arg-type]

        decision = Decision(
            id=decision_id,
            title=title,
            description=description,
            category=category,
            priority=priority,
            requester=requester,
            owner=owner,
            stakeholders=stakeholders or [],
            options=options or [],
            context=context or {},
            tags=tags or [],
            metadata=metadata or {},
        )

        # Evaluate risk if possible
        decision.risk_score = self.risk_scorer.calculate(decision)
        decision.risk_factors = self.risk_scorer.identify_factors(decision)

        # Determine if approval is required
        decision.approval_required = self.approval_matrix.is_approval_required(decision)

        # Determine escalation path
        decision.escalation_path = self.approval_router.determine_path(decision)

        # Log creation
        self.logger.info(f"Decision created: {decision_id} - {title}")

        # Persist to history
        self.decision_history.record(decision)

        return decision

    def evaluate(
        self,
        decision: Decision,
        options: list[dict[str, Any]] | None = None,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Evaluate decision options using the decision matrix.

        Args:
            decision: Decision to evaluate
            options: Options to evaluate (uses decision's options if None)
            weights: Custom weights for evaluation criteria

        Returns:
            Evaluation results with scores for each option
        """
        eval_options = options or decision.options
        if not eval_options:
            raise ValueError("No options provided for evaluation")

        results = self.decision_matrix.evaluate(eval_options, weights)

        # Log evaluation
        self.logger.info(
            f"Decision evaluated: {decision.id} - {len(eval_options)} options scored"
        )

        return results

    def make_decision(
        self,
        decision: Decision,
        selected_option: str,
        rationale: str,
        approved_by: str | None = None,
    ) -> Decision:
        """Make a final decision by selecting an option.

        Args:
            decision: Decision to resolve
            selected_option: ID of the selected option
            rationale: Explanation for the decision
            approved_by: Person/system approving the decision

        Returns:
            Updated Decision
        """
        decision.selected_option = selected_option
        decision.rationale = rationale
        decision.approved_by = approved_by
        decision.updated_at = datetime.now()
        decision.resolved_at = datetime.now()

        # Determine if escalation is needed
        if decision.approval_required and not approved_by:
            decision.status = DecisionStatus.ESCALATED
        else:
            decision.status = DecisionStatus.APPROVED

        # Apply policy constraints
        self.policy_engine.enforce(decision)

        # Generate explanation
        self.explain(decision)

        # Store in history
        self.decision_history.record(decision)

        self.logger.info(
            f"Decision resolved: {decision.id} -> {selected_option} "
            f"(status: {decision.status.value})"
        )

        return decision

    def escalate(
        self,
        decision: Decision,
        escalation_note: str = "",
    ) -> Decision:
        """Escalate a decision to higher authority.

        Args:
            decision: Decision to escalate
            escalation_note: Reason for escalation

        Returns:
            Updated Decision
        """
        decision.status = DecisionStatus.ESCALATED
        decision.updated_at = datetime.now()

        if escalation_note:
            decision.metadata["escalation_note"] = escalation_note

        # Route to next level
        next_level = self.approval_router.escalate(decision)
        decision.escalation_path.append(next_level)

        # Store in history
        self.decision_history.record(decision)

        self.logger.warning(
            f"Decision escalated: {decision.id} to {next_level} - {escalation_note}"
        )

        return decision

    def defer(
        self,
        decision: Decision,
        defer_reason: str,
        defer_until: str | None = None,
    ) -> Decision:
        """Defer a decision to a later time.

        Args:
            decision: Decision to defer
            defer_reason: Reason for deferring
            defer_until: Date/time to revisit

        Returns:
            Updated Decision
        """
        decision.status = DecisionStatus.DEFERRED
        decision.updated_at = datetime.now()
        decision.metadata["defer_reason"] = defer_reason
        if defer_until:
            decision.metadata["defer_until"] = defer_until

        self.decision_history.record(decision)
        self.logger.info(f"Decision deferred: {decision.id} - {defer_reason}")

        return decision

    def cancel(self, decision: Decision, cancel_reason: str) -> Decision:
        """Cancel a pending decision.

        Args:
            decision: Decision to cancel
            cancel_reason: Reason for cancellation

        Returns:
            Updated Decision
        """
        decision.status = DecisionStatus.CANCELLED
        decision.updated_at = datetime.now()
        decision.metadata["cancel_reason"] = cancel_reason

        self.decision_history.record(decision)
        self.logger.info(f"Decision cancelled: {decision.id} - {cancel_reason}")

        return decision

    def explain(self, decision: Decision) -> dict[str, Any]:
        """Generate an explainable summary for a decision.

        Args:
            decision: Decision to explain

        Returns:
            Explanation dictionary with reasoning details
        """
        explanation: dict[str, Any] = {
            "decision_id": decision.id,
            "title": decision.title,
            "status": decision.status.value,
            "category": decision.category.value,
            "priority": decision.priority.value,
        }

        # Explain option selection
        if decision.selected_option:
            # Find the selected option details
            selected = None
            for opt in decision.options:
                if opt.get("id") == decision.selected_option:
                    selected = opt
                    break

            explanation["selected_option"] = selected or {
                "id": decision.selected_option
            }

        # Explain risk assessment
        if decision.risk_score is not None:
            explanation["risk_assessment"] = {
                "score": decision.risk_score,
                "level": self._risk_level(decision.risk_score),
                "factors": decision.risk_factors,
            }

        # Explain approval requirements
        explanation["approval"] = {
            "required": decision.approval_required,
            "approved_by": decision.approved_by,
            "escalation_path": decision.escalation_path,
        }

        # Add rationale if available
        if decision.rationale:
            explanation["rationale"] = decision.rationale

        # Add context summary
        explanation["context_summary"] = {
            "requester": decision.requester,
            "owner": decision.owner,
            "stakeholders": decision.stakeholders,
            "constraints": decision.constraints,
        }

        # Add timeline
        explanation["timeline"] = {
            "created": decision.created_at.isoformat(),
            "resolved": decision.resolved_at.isoformat()
            if decision.resolved_at
            else None,
            "duration": (
                (decision.resolved_at - decision.created_at).total_seconds()
                if decision.resolved_at
                else None
            ),
        }

        # Apply policy reasoning
        policy_reasoning = self.policy_engine.get_reasoning(decision)
        if policy_reasoning:
            explanation["policy_reasoning"] = policy_reasoning

        return explanation

    def get_decision(self, decision_id: str) -> Decision | None:
        """Get a decision by ID from history.

        Args:
            decision_id: Decision identifier

        Returns:
            Decision if found, None otherwise
        """
        return self.decision_history.get(decision_id)

    def list_decisions(
        self,
        status: str | None = None,
        category: str | None = None,
        owner: str | None = None,
        limit: int = 100,
    ) -> list[Decision]:
        """List decisions with optional filters.

        Args:
            status: Filter by status
            category: Filter by category
            owner: Filter by owner
            limit: Maximum number of decisions to return

        Returns:
            List of matching decisions
        """
        return self.decision_history.query(
            status=status,
            category=category,
            owner=owner,
            limit=limit,
        )

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about decisions.

        Returns:
            Dictionary with decision statistics
        """
        all_decisions = self.decision_history.get_all()
        total = len(all_decisions)

        status_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        priority_counts: dict[str, int] = {}

        for d in all_decisions:
            status_counts[d.status.value] = status_counts.get(d.status.value, 0) + 1
            category_counts[d.category.value] = (
                category_counts.get(d.category.value, 0) + 1
            )
            priority_counts[d.priority.name] = (
                priority_counts.get(d.priority.name, 0) + 1
            )

        return {
            "total_decisions": total,
            "by_status": status_counts,
            "by_category": category_counts,
            "by_priority": priority_counts,
            "average_risk_score": (
                sum(d.risk_score or 0 for d in all_decisions) / total
                if total > 0
                else 0
            ),
        }

    def _risk_level(self, score: float) -> str:
        """Determine risk level from a numeric score."""
        if score < 0.2:
            return "very_low"
        elif score < 0.4:
            return "low"
        elif score < 0.6:
            return "medium"
        elif score < 0.8:
            return "high"
        else:
            return "critical"


class DecisionError(Exception):
    """Exception raised for decision-related errors."""

    def __init__(self, message: str, decision_id: str | None = None) -> None:
        super().__init__(message)
        self.decision_id = decision_id
