from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateError, TemplateNotFound

from ai_company.models.company import CompanyManifest
from ai_company.registry.registry import RegistryEngine, RegistryLoadResult


class BootstrapResult:
    def __init__(
        self,
        success: bool,
        created_files: list[str],
        errors: list[str],
        warnings: list[str],
        registry_result: RegistryLoadResult | None = None,
    ) -> None:
        self.success = success
        self.created_files = created_files
        self.errors = errors
        self.warnings = warnings
        self.registry_result = registry_result


class BootstrapGenerator:
    def __init__(
        self,
        company_dir: Path = Path("company"),
        manifest_path: Path = Path("config/company/company.yaml"),
        templates_dir: Path = Path("templates"),
        output_dir: Path = Path("generated"),
        tests_dir: Path = Path("tests"),
    ) -> None:
        self.company_dir = company_dir
        self.manifest_path = manifest_path
        self.templates_dir = templates_dir
        self.output_dir = output_dir
        self.tests_dir = tests_dir

    def run(self) -> BootstrapResult:
        errors: list[str] = []
        warnings: list[str] = []
        created_files: list[str] = []

        manifest = self._load_manifest(errors)
        if errors or manifest is None:
            return BootstrapResult(False, [], errors, warnings)

        registry_result = self._load_registry(errors, manifest)
        if errors:
            return BootstrapResult(False, [], errors, warnings, registry_result)

        normalized = manifest.normalize()
        self._create_directories(errors)

        env = self._build_jinja_env()
        if env is None:
            errors.append(f"Template directory not found: {self.templates_dir}")
            return BootstrapResult(False, [], errors, warnings, registry_result)

        context = self._build_context(normalized, registry_result)

        self._generate_main_readme(env, context, created_files, warnings)
        self._generate_department_readmes(env, context, normalized, created_files, warnings)
        self._generate_documentation_placeholders(env, context, normalized, created_files, warnings)
        self._generate_prompt_placeholders(env, context, normalized, created_files, warnings)
        self._generate_test_placeholders(env, context, normalized, created_files, warnings)

        return BootstrapResult(
            success=len(errors) == 0,
            created_files=created_files,
            errors=errors,
            warnings=warnings,
            registry_result=registry_result,
        )

    def _load_manifest(self, errors: list[str]) -> CompanyManifest | None:
        try:
            return CompanyManifest.load(self.manifest_path)
        except (FileNotFoundError, ValueError) as e:
            errors.append(str(e))
            return None

    def _load_registry(
        self, errors: list[str], manifest: CompanyManifest
    ) -> RegistryLoadResult | None:
        engine = RegistryEngine()
        result = engine.load(self.company_dir, manifest=manifest)
        if not result.success:
            for e in result.errors:
                errors.append(str(e))
        return result

    def _create_directories(self, errors: list[str]) -> None:
        dirs = [
            self.output_dir / "docs",
            self.output_dir / "prompts",
            self.output_dir / "README",
        ]
        for d in dirs:
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                errors.append(f"Failed to create directory {d}: {e}")

    def _build_jinja_env(self) -> Environment | None:
        if not self.templates_dir.is_dir():
            return None
        return Environment(loader=FileSystemLoader(str(self.templates_dir)))

    def _build_context(self, manifest: CompanyManifest, registry_result: RegistryLoadResult | None) -> dict[str, Any]:
        return {
            "company": {
                "name": manifest.name,
                "company_name": manifest.company_name or "",
                "description": manifest.description or "",
                "version": manifest.version or "",
                "departments": [
                    {
                        "name": d.name,
                        "display_name": d.display_name or d.name.title(),
                        "description": d.description or "",
                    }
                    for d in manifest.departments
                ],
                "department_count": len(manifest.departments),
                "vision": {
                    "name": manifest.name,
                    "company_name": manifest.company_name or "",
                    "description": manifest.description or "",
                },
            }
        }

    def _render_template(
        self,
        env: Environment,
        template_name: str,
        context: dict[str, Any],
        output_path: Path,
        created_files: list[str],
        warnings: list[str],
    ) -> None:
        try:
            template = env.get_template(template_name)
        except TemplateNotFound:
            warnings.append(f"Template not found, skipping: {template_name}")
            return
        try:
            rendered = template.render(context)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
            created_files.append(str(output_path))
        except (TemplateError, OSError) as e:
            warnings.append(f"Failed to render {template_name} to {output_path}: {e}")

    def _generate_main_readme(
        self,
        env: Environment,
        context: dict[str, Any],
        created_files: list[str],
        warnings: list[str],
    ) -> None:
        self._render_template(
            env, "README.md.j2", context, self.output_dir / "README.md", created_files, warnings
        )

    def _generate_department_readmes(
        self,
        env: Environment,
        context: dict[str, Any],
        manifest: CompanyManifest,
        created_files: list[str],
        warnings: list[str],
    ) -> None:
        for dept in manifest.departments:
            dept_context = {**context, "department": {"name": dept.name, "display_name": dept.display_name or dept.name.title(), "description": dept.description or ""}}
            output = self.output_dir / "README" / dept.name / "README.md"
            self._render_template(env, "department_README.md.j2", dept_context, output, created_files, warnings)

    def _generate_documentation_placeholders(
        self,
        env: Environment,
        context: dict[str, Any],
        manifest: CompanyManifest,
        created_files: list[str],
        warnings: list[str],
    ) -> None:
        for dept in manifest.departments:
            dept_context = {**context, "department": {"name": dept.name, "display_name": dept.display_name or dept.name.title(), "description": dept.description or ""}}
            output = self.output_dir / "docs" / dept.name / "README.md"
            self._render_template(env, "doc_placeholder.md.j2", dept_context, output, created_files, warnings)

    def _generate_prompt_placeholders(
        self,
        env: Environment,
        context: dict[str, Any],
        manifest: CompanyManifest,
        created_files: list[str],
        warnings: list[str],
    ) -> None:
        for dept in manifest.departments:
            dept_context = {**context, "department": {"name": dept.name, "display_name": dept.display_name or dept.name.title(), "description": dept.description or ""}}
            output = self.output_dir / "prompts" / dept.name / "README.md"
            self._render_template(env, "prompt_placeholder.md.j2", dept_context, output, created_files, warnings)

    def _generate_test_placeholders(
        self,
        env: Environment,
        context: dict[str, Any],
        manifest: CompanyManifest,
        created_files: list[str],
        warnings: list[str],
    ) -> None:
        for dept in manifest.departments:
            dept_context = {**context, "department": {"name": dept.name, "display_name": dept.display_name or dept.name.title(), "description": dept.description or ""}}
            test_filename = f"test_{dept.name}.py"
            output = self.tests_dir / test_filename
            self._render_template(env, "test_placeholder.py.j2", dept_context, output, created_files, warnings)
