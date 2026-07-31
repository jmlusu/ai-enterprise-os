"""Shared data models for the Decision Engine.

Extracted into a separate module to break the circular import chain:

    engine.py → approval.py → engine.py   (was: engine imports approval,
                                                   approval imports Decision from engine)

All sub-modules (approval, routing, risk, policy, matrix, history) and the
engine itself now import model types from this file instead of from engine.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class DecisionStatus(Enum):
    """Status of a decision."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"
    IN_REVIEW = "in_review"
    AWAITING_INFO = "awaiting_info"


class DecisionPriority(Enum):
    """Priority levels for decisions."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4
    EMERGENCY = 5


class DecisionCategory(Enum):
    """Categories of decisions."""

    STRATEGIC = "strategic"
    OPERATIONAL = "operational"
    FINANCIAL = "financial"
    TECHNICAL = "technical"
    HR = "hr"
    COMPLIANCE = "compliance"
    GOVERNANCE = "governance"
    RISK = "risk"
    OTHER = "other"


@dataclass
class Decision:
    """Represents a single decision with full audit trail."""

    id: str
    title: str
    description: str
    category: DecisionCategory = DecisionCategory.OTHER
    priority: DecisionPriority = DecisionPriority.MEDIUM
    status: DecisionStatus = DecisionStatus.PENDING
    requester: str = ""
    owner: str = ""
    stakeholders: list[str] = field(default_factory=list)
    options: list[dict[str, Any]] = field(default_factory=list)
    selected_option: str | None = None
    rationale: str | None = None
    risk_score: float | None = None
    risk_factors: list[str] = field(default_factory=list)
    approval_required: bool = True
    approved_by: str | None = None
    escalation_path: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime | None = None
    resolved_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "requester": self.requester,
            "owner": self.owner,
            "stakeholders": self.stakeholders,
            "options": self.options,
            "selected_option": self.selected_option,
            "rationale": self.rationale,
            "risk_score": self.risk_score,
            "risk_factors": self.risk_factors,
            "approval_required": self.approval_required,
            "approved_by": self.approved_by,
            "escalation_path": self.escalation_path,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "metadata": self.metadata,
            "context": self.context,
            "constraints": self.constraints,
            "dependents": self.dependents,
        }
