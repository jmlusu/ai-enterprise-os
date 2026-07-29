from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateError, TemplateNotFound

from ai_company.generator.context import GeneratorContext
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
    ) -> None:
        self.company_dir = company_dir
        self.manifest_path = manifest_path
        self.templates_dir = templates_dir
        self.output_dir = output_dir

    def run(self) -> BootstrapResult:
        errors: list[str] = []
        warnings: list[str] = []
        created_files: list[str] = []

        manifest, manifest_error = self._load_manifest()
        if manifest_error:
            return BootstrapResult(False, [], [manifest_error], warnings)
        assert manifest is not None

        registry_result, registry_error = self._load_registry(manifest)
        if registry_error:
            return BootstrapResult(
                False, [], [registry_error], warnings, registry_result
            )

        dir_errors = self._create_directories()
        if dir_errors:
            return BootstrapResult(False, [], dir_errors, warnings, registry_result)

        env = self._build_jinja_env()
        if env is None:
            return BootstrapResult(
                False,
                [],
                [f"Template directory not found: {self.templates_dir}"],
                warnings,
                registry_result,
            )

        assert registry_result is not None and registry_result.registry is not None
        ctx = GeneratorContext(
            manifest=manifest.normalize(),
            registry=registry_result.registry,
            company_dir=self.company_dir,
            templates_dir=self.templates_dir,
            output_dir=self.output_dir,
        )
        context = ctx.to_dict()

        self._generate_main_readme(env, context, created_files, warnings)
        self._generate_department_readmes(
            env, context, manifest, created_files, warnings
        )
        self._generate_documentation_placeholders(
            env, context, manifest, created_files, warnings
        )
        self._generate_prompt_placeholders(
            env, context, manifest, created_files, warnings
        )

        return BootstrapResult(
            success=len(errors) == 0,
            created_files=created_files,
            errors=errors,
            warnings=warnings,
            registry_result=registry_result,
        )

    def _load_manifest(
        self,
    ) -> tuple[CompanyManifest | None, str | None]:
        try:
            return CompanyManifest.load(self.manifest_path), None
        except (FileNotFoundError, ValueError) as e:
            return None, str(e)

    def _load_registry(
        self, manifest: CompanyManifest
    ) -> tuple[RegistryLoadResult | None, str | None]:
        engine = RegistryEngine()
        result = engine.load(self.company_dir, manifest=manifest)
        if not result.success:
            return result, "; ".join(result.errors)
        return result, None

    def _create_directories(self) -> list[str]:
        dir_errors: list[str] = []
        dirs = [
            self.output_dir / "docs",
            self.output_dir / "prompts",
            self.output_dir / "README",
        ]
        for d in dirs:
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                dir_errors.append(f"Failed to create directory {d}: {e}")
        return dir_errors

    def _build_jinja_env(self) -> Environment | None:
        if not self.templates_dir.is_dir():
            return None
        return Environment(loader=FileSystemLoader(str(self.templates_dir)))

    @staticmethod
    def _render_template(
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

    @staticmethod
    def _generate_main_readme(
        env: Environment,
        context: dict[str, Any],
        created_files: list[str],
        warnings: list[str],
    ) -> None:
        BootstrapGenerator._render_template(
            env,
            "README.md.j2",
            context,
            Path("generated") / "README.md",
            created_files,
            warnings,
        )

    @staticmethod
    def _generate_department_readmes(
        env: Environment,
        context: dict[str, Any],
        manifest: CompanyManifest,
        created_files: list[str],
        warnings: list[str],
    ) -> None:
        for dept in manifest.departments:
            dept_context = {
                **context,
                "department": {
                    "name": dept.name,
                    "display_name": dept.display_name or dept.name.title(),
                    "description": dept.description or "",
                },
            }
            output = Path("generated") / "README" / dept.name / "README.md"
            BootstrapGenerator._render_template(
                env,
                "department_README.md.j2",
                dept_context,
                output,
                created_files,
                warnings,
            )

    @staticmethod
    def _generate_documentation_placeholders(
        env: Environment,
        context: dict[str, Any],
        manifest: CompanyManifest,
        created_files: list[str],
        warnings: list[str],
    ) -> None:
        for dept in manifest.departments:
            dept_context = {
                **context,
                "department": {
                    "name": dept.name,
                    "display_name": dept.display_name or dept.name.title(),
                    "description": dept.description or "",
                },
            }
            output = Path("generated") / "docs" / dept.name / "README.md"
            BootstrapGenerator._render_template(
                env,
                "doc_placeholder.md.j2",
                dept_context,
                output,
                created_files,
                warnings,
            )

    @staticmethod
    def _generate_prompt_placeholders(
        env: Environment,
        context: dict[str, Any],
        manifest: CompanyManifest,
        created_files: list[str],
        warnings: list[str],
    ) -> None:
        for dept in manifest.departments:
            dept_context = {
                **context,
                "department": {
                    "name": dept.name,
                    "display_name": dept.display_name or dept.name.title(),
                    "description": dept.description or "",
                },
            }
            output = Path("generated") / "prompts" / dept.name / "README.md"
            BootstrapGenerator._render_template(
                env,
                "prompt_placeholder.md.j2",
                dept_context,
                output,
                created_files,
                warnings,
            )
