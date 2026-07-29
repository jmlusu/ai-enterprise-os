from pathlib import Path

from pydantic import ValidationError

from ai_company.models.company import (
    BoardEntry,
    CompanyManifest,
    CompanyRegistry,
    DepartmentData,
    ExecutiveEntry,
    PolicyEntry,
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
        registry: CompanyRegistry | None,
        errors: list[str],
        warnings: list[str],
        manifest: CompanyManifest | None = None,
    ) -> None:
        self.registry = registry
        self.errors = errors
        self.warnings = warnings
        self.manifest = manifest

    @property
    def success(self) -> bool:
        return self.registry is not None and len(self.errors) == 0


class RegistryEngine:
    def __init__(self) -> None:
        self._registry: CompanyRegistry | None = None
        self._last_result: RegistryLoadResult | None = None

    def load(
        self,
        company_dir: Path | None = None,
        manifest: CompanyManifest | None = None,
    ) -> RegistryLoadResult:
        if company_dir is None:
            company_dir = Path("company")

        errors: list[str] = []
        warnings: list[str] = []

        if manifest is not None:
            manifest_errors = manifest.validate_manifest()
            if manifest_errors:
                errors.extend(f"manifest: {e}" for e in manifest_errors)
                self._last_result = RegistryLoadResult(None, errors, [], manifest=manifest)
                return self._last_result

        load_result = load_registry_files(company_dir)
        if not load_result.success:
            self._last_result = RegistryLoadResult(None, load_result.errors, [], manifest=manifest)
            return self._last_result

        parsed = parse_registry(load_result.data)

        if manifest is not None:
            manifest_dept_names = {d.name for d in manifest.normalize().departments}
            yaml_dept_names = set(parsed.get("department_names", []))
            for dept in sorted(manifest_dept_names - yaml_dept_names):
                warnings.append(f"manifest department '{dept}' not found in company YAML files")
            for dept in sorted(yaml_dept_names - manifest_dept_names):
                warnings.append(
                    f"company YAML references department '{dept}' not declared in manifest"
                )

        validation = validate_parsed_data(parsed)
        if not validation.passed:
            self._last_result = RegistryLoadResult(
                None, [e.message for e in validation.errors], [w.message for w in validation.warnings], manifest=manifest
            )
            return self._last_result
        warnings.extend(w.message for w in validation.warnings)

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
            self._last_result = RegistryLoadResult(None, errors, warnings, manifest=manifest)
            return self._last_result

        self._last_result = RegistryLoadResult(self._registry, errors, warnings, manifest=manifest)
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
    def last_result(self) -> RegistryLoadResult | None:
        return self._last_result


registry_engine = RegistryEngine()
