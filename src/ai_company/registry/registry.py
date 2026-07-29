from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from ai_company.models.company import (
    BoardEntry,
    CompanyRegistry,
    DepartmentData,
    ExecutiveEntry,
    PolicyEntry,
    Role,
    SpecialistEntry,
    VisionData,
    WorkflowEntry,
)
from ai_company.registry.loader import load_registry_files
from ai_company.registry.parser import parse_registry
from ai_company.registry.resolver import resolve
from ai_company.registry.validator import validate_parsed_data


class RegistryLoadResult:
    def __init__(
        self,
        registry: Optional[CompanyRegistry],
        errors: list[str],
        warnings: list[str],
    ) -> None:
        self.registry = registry
        self.errors = errors
        self.warnings = warnings

    @property
    def success(self) -> bool:
        return self.registry is not None and len(self.errors) == 0


class RegistryEngine:
    _instance: Optional["RegistryEngine"] = None
    _registry: Optional[CompanyRegistry] = None
    _last_result: Optional[RegistryLoadResult] = None

    def __new__(cls) -> "RegistryEngine":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, company_dir: Optional[Path] = None) -> RegistryLoadResult:
        if company_dir is None:
            company_dir = Path("company")

        errors: list[str] = []
        warnings: list[str] = []

        load_result = load_registry_files(company_dir)
        if not load_result.success:
            self._last_result = RegistryLoadResult(None, load_result.errors, [])
            return self._last_result

        parsed = parse_registry(load_result.data)

        validation = validate_parsed_data(parsed)
        if not validation.valid:
            self._last_result = RegistryLoadResult(None, validation.errors, validation.warnings)
            return self._last_result
        warnings.extend(validation.warnings)

        resolution = resolve(parsed)
        warnings.extend(resolution.warnings)
        if not resolution.success:
            warnings.append(f"unresolved department refs: {', '.join(resolution.unresolved_refs)}")

        merged = resolution.merge_into(parsed)

        try:
            self._registry = CompanyRegistry(
                vision=VisionData(**merged["vision"]),
                departments={
                    k: DepartmentData(**v) for k, v in merged["departments"].items()
                },
                board=[BoardEntry(**e) for e in merged.get("board", [])],
                executives=[ExecutiveEntry(**e) for e in merged.get("executives", [])],
                policies=[PolicyEntry(**e) for e in merged.get("policies", [])],
                specialists=[SpecialistEntry(**e) for e in merged.get("specialists", [])],
                workflows=[WorkflowEntry(**e) for e in merged.get("workflows", [])],
                unresolved_refs=resolution.unresolved_refs,
            )
        except ValidationError as e:
            errors.append(str(e))
            self._last_result = RegistryLoadResult(None, errors, warnings)
            return self._last_result

        self._last_result = RegistryLoadResult(self._registry, errors, warnings)
        return self._last_result

    def reload(self) -> None:
        self._registry = None
        self._last_result = None

    @property
    def registry(self) -> CompanyRegistry:
        if self._registry is None:
            raise RuntimeError("Registry not loaded. Call load() first.")
        return self._registry

    @property
    def last_result(self) -> Optional[RegistryLoadResult]:
        return self._last_result


registry_engine = RegistryEngine()
