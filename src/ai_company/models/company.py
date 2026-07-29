from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError
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


class ManifestDepartment(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None


class CompanyManifest(BaseModel):
    name: str
    description: Optional[str] = None
    company_name: Optional[str] = None
    version: Optional[str] = None
    departments: list[ManifestDepartment] = []

    @classmethod
    def load(cls, path: Path) -> "CompanyManifest":
        if not path.exists():
            raise FileNotFoundError(f"Company manifest not found: {path}")
        if path.stat().st_size == 0:
            raise ValueError(f"Company manifest is empty: {path}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ValueError("Company manifest must be a mapping")
            return cls(**data)
        except yaml.YAMLError as e:
            raise ValueError(f"YAML syntax error in manifest: {e}")
        except ValidationError as e:
            raise ValueError(f"Manifest validation failed: {e}")

    def validate_manifest(self) -> list[str]:
        errors: list[str] = []
        if not self.name:
            errors.append("manifest name is required")
        seen = set()
        for dept in self.departments:
            if not dept.name:
                errors.append("department name is required")
            elif dept.name in seen:
                errors.append(f"duplicate department name: {dept.name}")
            seen.add(dept.name)
        if not self.departments:
            errors.append("at least one department must be defined")
        return errors

    def normalize(self) -> "CompanyManifest":
        depts = [
            ManifestDepartment(
                name=d.name.strip().lower().replace(" ", "_"),
                display_name=d.display_name or d.name.strip().title(),
                description=d.description.strip() if d.description else "",
            )
            for d in self.departments
        ]
        return CompanyManifest(
            name=self.name.strip(),
            description=self.description.strip() if self.description else None,
            company_name=self.company_name.strip() if self.company_name else None,
            version=self.version.strip() if self.version else None,
            departments=depts,
        )
