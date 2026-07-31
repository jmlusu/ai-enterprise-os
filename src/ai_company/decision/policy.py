"""Policy engine for AI Enterprise OS Decision Engine.

Enforces policies and constraints on decisions, provides reasoning
for policy-based decisions.
"""

from __future__ import annotations

import logging
from typing import Any

from ai_company.decision.models import Decision


class Policy:
    """A single policy rule."""

    def __init__(
        self,
        policy_id: str,
        name: str,
        description: str = "",
        scope: str = "global",
        enabled: bool = True,
        priority: int = 0,
        conditions: dict[str, Any] | None = None,
        actions: dict[str, Any] | None = None,
    ) -> None:
        self.policy_id = policy_id
        self.name = name
        self.description = description
        self.scope = scope
        self.enabled = enabled
        self.priority = priority
        self.conditions = conditions or {}
        self.actions = actions or {}

    def applies_to(self, decision: Decision) -> bool:
        """Check if this policy applies to a decision."""
        if not self.enabled:
            return False

        if self.scope != "global":
            scope_value = decision.context.get("scope", decision.category.value)
            if scope_value != self.scope:
                return False

        for key, value in self.conditions.items():
            if key == "min_priority" and decision.priority.value < value:
                return False
            if key == "max_priority" and decision.priority.value > value:
                return False
            if key == "category" and decision.category.value != value:
                return False
            if key == "risk_max" and (decision.risk_score or 0) > value:
                return False

        return True

    def enforce(self, decision: Decision) -> list[str]:
        """Enforce this policy on a decision. Returns list of actions taken."""
        results: list[str] = []
        if not self.applies_to(decision):
            return results

        action_type = self.actions.get("type")
        if action_type == "require_approval":
            decision.approval_required = True
            results.append(f"Approval required by policy {self.name}")
        elif action_type == "auto_approve":
            decision.approval_required = False
            results.append(f"Auto-approved by policy {self.name}")
        elif action_type == "add_constraint":
            constraint = self.actions.get("constraint", "")
            if constraint:
                decision.constraints.append(constraint)
                results.append(f"Constraint added: {constraint}")
        elif action_type == "set_owner":
            owner = self.actions.get("owner", "")
            if owner:
                decision.owner = owner
                results.append(f"Owner set to {owner}")
        elif action_type == "escalate":
            results.append(f"Escalation triggered by policy {self.name}")

        return results


class PolicyEngine:
    """Engine for managing and enforcing policies on decisions."""

    def __init__(self) -> None:
        self.policies: dict[str, Policy] = {}
        self.logger = logging.getLogger(self.__class__.__name__)

    def add_policy(self, policy: Policy) -> None:
        self.policies[policy.policy_id] = policy

    def remove_policy(self, policy_id: str) -> bool:
        if policy_id in self.policies:
            del self.policies[policy_id]
            return True
        return False

    def enforce(self, decision: Decision) -> list[str]:
        """Enforce all applicable policies on a decision."""
        all_results: list[str] = []
        sorted_policies = sorted(
            self.policies.values(), key=lambda p: p.priority, reverse=True
        )

        for policy in sorted_policies:
            results = policy.enforce(decision)
            all_results.extend(results)

        return all_results

    def get_reasoning(self, decision: Decision) -> dict[str, Any]:
        """Get policy reasoning for a decision."""
        reasoning: dict[str, Any] = {
            "policies_applied": [],
            "policies_not_applied": [],
            "total_policies": len(self.policies),
        }

        for policy in self.policies.values():
            entry = {
                "id": policy.policy_id,
                "name": policy.name,
                "description": policy.description,
                "scope": policy.scope,
            }

            if policy.applies_to(decision):
                reasoning["policies_applied"].append(entry)
            else:
                reasoning["policies_not_applied"].append(entry)

        reasoning["applicable_count"] = len(reasoning["policies_applied"])

        return reasoning

    def get_policy(self, policy_id: str) -> Policy | None:
        return self.policies.get(policy_id)

    def list_policies(self, scope: str | None = None) -> list[Policy]:
        if scope:
            return [p for p in self.policies.values() if p.scope == scope]
        return list(self.policies.values())
