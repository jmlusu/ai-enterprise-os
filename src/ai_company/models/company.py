from pydantic import BaseModel, ConfigDict
from typing import Optional


class VisionData(BaseModel):
    name: str
    description: Optional[str] = None
    company_name: Optional[str] = None


class Role(BaseModel):
    title: str
    description: str = ""


class DepartmentData(BaseModel):
    name: str
    roles: list[Role] = []


class BoardEntry(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None


class ExecutiveEntry(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None


class PolicyEntry(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class SpecialistEntry(BaseModel):
    name: Optional[str] = None
    expertise: Optional[str] = None


class WorkflowEntry(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    steps: list[str] = []


class DepartmentRef(BaseModel):
    name: str
    defined: bool = False


class CompanyRegistry(BaseModel):
    model_config = ConfigDict(frozen=True)

    vision: VisionData
    departments: dict[str, DepartmentData] = {}
    board: list[BoardEntry] = []
    executives: list[ExecutiveEntry] = []
    specialists: list[SpecialistEntry] = []
    policies: list[PolicyEntry] = []
    workflows: list[WorkflowEntry] = []
    unresolved_refs: list[str] = []
