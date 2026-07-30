"""Generate role definitions across the organization.

The :class:`RoleGenerator` enriches raw role entries from the registry
with standardized metadata, seniority classifications, and skill mappings.
"""

from __future__ import annotations

import logging
from typing import Any

from ai_company.company.models import OrgGraph
from ai_company.models.company import CompanyRegistry

logger = logging.getLogger(__name__)


class RoleError(Exception):
    """Raised when role generation encounters an inconsistency."""


# Seniority heuristics based on title keywords
SENIORITY_KEYWORDS: dict[str, str] = {
    "chief": "c-suite",
    "vp": "vp",
    "vice president": "vp",
    "director": "director",
    "senior": "senior",
    "staff": "staff",
    "lead": "senior",
    "principal": "staff",
    "manager": "manager",
    "junior": "junior",
    "associate": "junior",
    "intern": "intern",
}

# Category heuristics
CATEGORY_KEYWORDS: dict[str, str] = {
    "engineer": "engineering",
    "developer": "engineering",
    "architect": "engineering",
    "devops": "engineering",
    "sre": "engineering",
    "data": "data",
    "scientist": "data",
    "analyst": "data",
    "designer": "design",
    "ux": "design",
    "product": "product",
    "manager": "management",
    "marketing": "marketing",
    "sales": "sales",
    "support": "support",
    "security": "security",
    "legal": "legal",
    "finance": "finance",
    "hr": "hr",
    "recruiter": "hr",
    "researcher": "research",
    "writer": "communication",
    "counsel": "legal",
}


def classify_seniority(title: str) -> str:
    """Determine seniority level from a job title."""
    lower = title.lower()
    for keyword, level in SENIORITY_KEYWORDS.items():
        if keyword in lower:
            return level
    return "mid"


def classify_category(title: str) -> str:
    """Determine functional category from a job title."""
    lower = title.lower()
    for keyword, cat in CATEGORY_KEYWORDS.items():
        if keyword in lower:
            return cat
    return "general"


class RoleGenerator:
    """Generates and enriches role definitions across the organization.

    Args:
        registry: The loaded company registry.
        graph: The organization graph (optional — used to cross-reference).
    """

    def __init__(
        self,
        registry: CompanyRegistry,
        graph: OrgGraph | None = None,
    ) -> None:
        self._registry = registry
        self._graph = graph

    def generate_all(self) -> list[dict[str, Any]]:
        """Generate enriched role definitions for every role in the registry.

        Returns:
            A list of role dictionaries with enriched metadata.
        """
        roles: list[dict[str, Any]] = []

        for dept_name, dept_data in self._registry.departments.items():
            for role in dept_data.roles:
                enriched = self._enrich_role(role.title, role.description, dept_name)
                roles.append(enriched)

        # Add roles inferred from executives
        for ex in self._registry.executives:
            if ex.name and ex.title:
                enriched = self._enrich_role(
                    ex.title,
                    ex.bio or "",
                    ex.department or "executive",
                    is_executive=True,
                    executive_name=ex.name,
                )
                roles.append(enriched)

        logger.info("Generated %d role definitions", len(roles))
        return roles

    def generate_for_department(self, department_name: str) -> list[dict[str, Any]]:
        """Generate roles for a single department."""
        dept_data = self._registry.departments.get(department_name)
        if dept_data is None:
            return []

        roles: list[dict[str, Any]] = []
        for role in dept_data.roles:
            enriched = self._enrich_role(role.title, role.description, department_name)
            roles.append(enriched)
        return roles

    def _enrich_role(
        self,
        title: str,
        description: str,
        department: str,
        is_executive: bool = False,
        executive_name: str = "",
    ) -> dict[str, Any]:
        """Add computed metadata to a raw role entry."""
        return {
            "title": title,
            "description": description,
            "department": department,
            "seniority": classify_seniority(title),
            "category": classify_category(title),
            "is_executive": is_executive,
            "executive_name": executive_name,
            "requires_approval": title.lower().startswith("chief"),
            "max_decision_authority": self._estimate_authority(title),
        }

    @staticmethod
    def _estimate_authority(title: str) -> str:
        """Estimate decision authority level from title."""
        lower = title.lower()
        if "chief" in lower:
            return "company-wide"
        if "vp" in lower or "vice president" in lower:
            return "department-wide"
        if "director" in lower:
            return "team-wide"
        if "manager" in lower:
            return "project-level"
        if "senior" in lower or "staff" in lower or "lead" in lower:
            return "domain-level"
        return "task-level"
