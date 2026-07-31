"""Approval matrix and routing for AI Enterprise OS Decision Engine."""

from __future__ import annotations

import logging
from typing import Any

from ai_company.decision.models import Decision


class ApprovalRule:
    """Represents a rule in the approval matrix."""

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: str | None = None,
        min_priority: int = 1,
        max_risk_score: float = 1.0,
        requires_approval: bool = True,
        approver_role: str = "",
        escalation_role: str = "",
        auto_approve: bool = False,
        conditions: dict[str, Any] | None = None,
    ) -> None:
        self.rule_id = rule_id
        self.name = name
        self.category = category
        self.min_priority = min_priority
        self.max_risk_score = max_risk_score
        self.requires_approval = requires_approval
        self.approver_role = approver_role
        self.escalation_role = escalation_role
        self.auto_approve = auto_approve
        self.conditions = conditions or {}

    def matches(self, decision: Decision) -> bool:
        """Check if this rule applies to the given decision."""
        if self.category and decision.category.value != self.category:
            return False
        if decision.priority.value < self.min_priority:
            return False
        if (
            decision.risk_score is not None
            and decision.risk_score > self.max_risk_score
        ):
            return False
        for key, value in self.conditions.items():
            if decision.context.get(key) != value:
                return False
        return True


class ApprovalMatrix:
    """Matrix for determining approval requirements for decisions."""

    def __init__(self) -> None:
        self.rules: list[ApprovalRule] = []
        self.default_approver: str = "board"
        self.logger = logging.getLogger(self.__class__.__name__)

    def add_rule(self, rule: ApprovalRule) -> None:
        self.rules.append(rule)

    def is_approval_required(self, decision: Decision) -> bool:
        """Determine if approval is required for a decision."""
        for rule in self.rules:
            if rule.matches(decision):
                return rule.requires_approval
        return True

    def get_approver(self, decision: Decision) -> str:
        """Get the approver role for a decision."""
        for rule in self.rules:
            if rule.matches(decision):
                return rule.approver_role or self.default_approver
        return self.default_approver

    def can_auto_approve(self, decision: Decision) -> bool:
        """Check if a decision can be auto-approved."""
        for rule in self.rules:
            if rule.matches(decision):
                return rule.auto_approve
        return False

    def get_matching_rules(self, decision: Decision) -> list[ApprovalRule]:
        """Get all rules matching a decision."""
        return [r for r in self.rules if r.matches(decision)]


class ApprovalRouter:
    """Routes approval requests through the approval hierarchy."""

    def __init__(self) -> None:
        self.approval_hierarchy: dict[str, str] = {}
        self.logger = logging.getLogger(self.__class__.__name__)

    def determine_path(self, decision: Decision) -> list[str]:
        """Determine the escalation path for a decision."""
        path: list[str] = []
        current_role = decision.owner or "requester"

        while current_role in self.approval_hierarchy:
            path.append(current_role)
            current_role = self.approval_hierarchy[current_role]

        if current_role:
            path.append(current_role)

        return path

    def escalate(self, decision: Decision) -> str:
        """Escalate a decision to the next level."""
        path = decision.escalation_path
        if not path:
            return "board"
        current_index = path.index(decision.owner) if decision.owner in path else -1
        if current_index < len(path) - 1:
            return path[current_index + 1]
        return path[-1]

    def set_hierarchy(self, hierarchy: dict[str, str]) -> None:
        """Set the approval hierarchy."""
        self.approval_hierarchy = hierarchy
