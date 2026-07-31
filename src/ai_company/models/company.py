from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class VisionData(BaseModel):
    name: str
    description: str | None = None
    company_name: str | None = None


class Role(BaseModel):
    title: str
    description: str = ""


class DepartmentData(BaseModel):
    name: str
    roles: list[Role] = []


class BoardEntry(BaseModel):
    name: str | None = None
    role: str | None = None


class ExecutiveAgentConfig(BaseModel):
    """Agent runtime configuration tied to an executive."""

    model: str = "gpt-4o"
    instructions: str = ""
    tools: list[str] = Field(
        default_factory=lambda: ["registry-read", "kpi-dashboard", "budget-view"]
    )
    temperature: float = 0.0
    department_scope: list[str] = Field(default_factory=list)


class ExecutiveEntry(BaseModel):
    name: str | None = None
    title: str | None = None
    bio: str = ""
    department: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    kpis: list[str] = Field(default_factory=list)
    budget_authority: float = 0.0
    direct_reports: list[str] = Field(default_factory=list)
    reports_to: str = ""
    status: str = "active"
    start_date: str = ""
    email: str = ""
    agent_config: ExecutiveAgentConfig = Field(default_factory=ExecutiveAgentConfig)


class PolicyEntry(BaseModel):
    name: str | None = None
    description: str | None = None


class SpecialistEntry(BaseModel):
    name: str | None = None
    expertise: str | None = None
    department: str | None = None
    bio: str | None = None
    tools: list[str] = []


class WorkflowEntry(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[str] = []


class DepartmentRef(BaseModel):
    name: str
    defined: bool = False


class BoardMember(BaseModel):
    name: str
    role: str = ""
    term_start: str | None = None
    term_end: str | None = None
    committees: list[str] = []
    independent: bool = False


class Committee(BaseModel):
    name: str
    purpose: str = ""
    chair: str = ""
    members: list[str] = []
    meeting_frequency: str = "monthly"


class Meeting(BaseModel):
    title: str
    meeting_date: str = ""
    meeting_type: str = "standup"
    attendees: list[str] = []
    minutes: str = ""
    action_items: list[str] = []


class Voting(BaseModel):
    motion: str
    proposed_by: str = ""
    seconds_by: str = ""
    votes_for: int = 0
    votes_against: int = 0
    votes_abstain: int = 0
    passed: bool = False
    vote_date: str = ""


class Agent(BaseModel):
    name: str
    role: str = ""
    model: str = ""
    instructions: str = ""
    tools: list[str] = []
    department: str = ""


class Policy(BaseModel):
    name: str
    description: str = ""
    scope: str = ""
    version: str = "1.0.0"
    effective_date: str = ""
    owner: str = ""
    rules: list[str] = []


class Budget(BaseModel):
    department: str
    fiscal_year: str = ""
    total: float = 0.0
    spent: float = 0.0
    currency: str = "USD"
    categories: dict[str, float] = Field(default_factory=dict)


class KPI(BaseModel):
    name: str
    target: float
    current: float = 0.0
    unit: str = ""
    owner: str = ""
    frequency: str = "quarterly"
    trend: Literal["up", "down", "flat"] = "flat"


class Risk(BaseModel):
    description: str
    impact: Literal["low", "medium", "high", "critical"] = "medium"
    likelihood: Literal["low", "medium", "high"] = "medium"
    mitigation: str = ""
    owner: str = ""
    status: Literal["open", "mitigated", "accepted", "closed"] = "open"


class Decision(BaseModel):
    title: str
    decision_date: str = ""
    author: str = ""
    rationale: str = ""
    outcome: str = ""
    stakeholders: list[str] = []


class Permission(BaseModel):
    resource: str
    role: str = ""
    actions: list[str] = Field(default_factory=lambda: ["read"])
    constraints: str = ""


class Integration(BaseModel):
    name: str
    type: str = "api"
    version: str = "1.0.0"
    config: dict[str, Any] = Field(default_factory=dict)
    status: Literal["active", "inactive", "deprecated"] = "active"


class Tool(BaseModel):
    name: str
    purpose: str = ""
    category: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    access_roles: list[str] = []


class Governance(BaseModel):
    framework: str = "standard"
    policies: list[str] = []
    controls: list[str] = []
    compliance_standards: list[str] = []
    review_cycle: str = "quarterly"


class Strategy(BaseModel):
    name: str = ""
    description: str = ""
    objectives: list[str] = []
    metrics: list[str] = []
    timeline: str = ""
    owner: str = ""
    status: Literal["draft", "active", "completed", "cancelled"] = "draft"


class Culture(BaseModel):
    values: list[str] = []
    behaviors: list[str] = []
    norms: list[str] = []
    rituals: list[str] = []


CompanyRegistry_update_warning = "CompanyRegistry updated with new model fields"


class CompanyRegistry(BaseModel):
    model_config = ConfigDict(frozen=True)

    vision: VisionData
    departments: dict[str, DepartmentData] = {}
    board: list[BoardEntry] = []
    executives: list[ExecutiveEntry] = []
    executive_agents: list[Agent] = []
    specialists: list[SpecialistEntry] = []
    policies: list[PolicyEntry] = []
    workflows: list[WorkflowEntry] = []
    unresolved_refs: list[str] = []

    board_members: list[BoardMember] = []
    committees: list[Committee] = []
    meetings: list[Meeting] = []
    voting_records: list[Voting] = []
    agents: list[Agent] = []
    policy_documents: list[Policy] = []
    budgets: list[Budget] = []
    kpis: list[KPI] = []
    risks: list[Risk] = []
    decisions: list[Decision] = []
    permissions: list[Permission] = []
    integrations: list[Integration] = []
    tools: list[Tool] = []
    governance: Governance = Field(default_factory=Governance)
    strategy: Strategy = Field(default_factory=Strategy)
    culture: Culture = Field(default_factory=Culture)


class ManifestDepartment(BaseModel):
    name: str
    display_name: str | None = None
    description: str | None = None


class CompanyManifest(BaseModel):
    name: str
    description: str | None = None
    company_name: str | None = None
    version: str | None = None
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
                raise TypeError("Company manifest must be a mapping")
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
