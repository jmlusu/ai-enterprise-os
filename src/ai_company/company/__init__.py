"""Organization Generator — the heart of Sprint 3.

This package produces the complete organizational model of an AI-native
company from the :class:`~ai_company.registry.registry.CompanyRegistry`.
It is consumed by the board, executive, department, specialist, workflow,
prompt, documentation, and graph generators.
"""

from ai_company.company.board_generator import BoardGenerator, BoardResult
from ai_company.company.department_generator import DepartmentGenerator
from ai_company.company.executive_generator import ExecutiveGenerator
from ai_company.company.specialist_generator import SpecialistGenerator
from ai_company.company.generator import CompanyGenerator
from ai_company.company.hierarchy import HierarchyBuilder, HierarchyError
from ai_company.company.models import OrgEdge, OrgGraph, OrgMetadata, OrgNode
from ai_company.company.organization import OrganizationGenerator
from ai_company.company.relationships import RelationshipError, RelationshipResolver
from ai_company.company.reporting import ReportingError, ReportingStructure
from ai_company.company.roles import RoleError, RoleGenerator

__all__ = [
    "OrgNode",
    "OrgEdge",
    "OrgGraph",
    "OrgMetadata",
    "HierarchyBuilder",
    "HierarchyError",
    "RoleGenerator",
    "RoleError",
    "RelationshipResolver",
    "RelationshipError",
    "ReportingStructure",
    "ReportingError",
    "OrganizationGenerator",
    "CompanyGenerator",
    "BoardGenerator",
    "BoardResult",
    "ExecutiveGenerator",
    "DepartmentGenerator",
    "SpecialistGenerator",
]
