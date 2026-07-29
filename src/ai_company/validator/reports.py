from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    message: str
    severity: Literal["error", "warning", "info"] = "error"
    field: str = ""
    path: str | None = None


class ValidationReport(BaseModel):
    target: str
    passed: bool
    total_checks: int = 0
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    infos: list[ValidationIssue] = Field(default_factory=list)

    def add_error(self, message: str, field: str = "", path: str | None = None) -> None:
        self.errors.append(ValidationIssue(message=message, severity="error", field=field, path=path))
        self.passed = False
        self.total_checks += 1

    def add_warning(self, message: str, field: str = "", path: str | None = None) -> None:
        self.warnings.append(ValidationIssue(message=message, severity="warning", field=field, path=path))
        self.total_checks += 1

    def add_info(self, message: str, field: str = "", path: str | None = None) -> None:
        self.infos.append(ValidationIssue(message=message, severity="info", field=field, path=path))
        self.total_checks += 1


class ValidatorResult(BaseModel):
    engine_version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=datetime.now)
    reports: list[ValidationReport] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.reports)

    @property
    def total_errors(self) -> int:
        return sum(len(r.errors) for r in self.reports)

    @property
    def total_warnings(self) -> int:
        return sum(len(r.warnings) for r in self.reports)

    @property
    def total_checks(self) -> int:
        return sum(r.total_checks for r in self.reports)

    def summary(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        return (
            f"Validator Engine [{status}]  "
            f"{self.total_checks} checks, "
            f"{self.total_errors} errors, "
            f"{self.total_warnings} warnings "
            f"across {len(self.reports)} target(s)"
        )
