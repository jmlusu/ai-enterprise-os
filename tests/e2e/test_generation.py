from pathlib import Path

from ai_company.company.generator import CompanyGenerator
from ai_company.generator.context import GeneratorContext
from ai_company.generator.engine import GenerationConfig
from ai_company.generator.planner import GenerationPlanner
from ai_company.models.company import CompanyManifest
from ai_company.registry.registry import RegistryEngine


class TestE2EGeneratorEngine:
    def test_generator_engine_creates_config(self) -> None:
        config = GenerationConfig()
        assert config.output_dir == Path("generated")

    def test_generator_engine_defaults(self) -> None:
        config = GenerationConfig(dry_run=True)
        assert config.dry_run

    def test_company_generator_creates(self) -> None:
        gen = CompanyGenerator()
        assert gen is not None

    def test_company_generator_validate_registry(self) -> None:
        gen = CompanyGenerator()
        errors = gen.validate()
        assert len(errors) == 0, f"Validation errors: {errors}"

    def test_company_generator_validate_executives(self) -> None:
        gen = CompanyGenerator()
        errors = gen.validate_executives()
        assert len(errors) == 0

    def test_company_generator_validate_departments(self) -> None:
        gen = CompanyGenerator()
        errors = gen.validate_departments()
        assert len(errors) == 0

    def test_company_generator_validate_workflows(self) -> None:
        gen = CompanyGenerator()
        errors = gen.validate_workflows()
        assert len(errors) == 0

    def test_company_generator_validate_specialists(self) -> None:
        gen = CompanyGenerator()
        errors = gen.validate_specialists()
        assert len(errors) == 0

    def test_company_generator_validate_docs(self) -> None:
        gen = CompanyGenerator()
        errors = gen.validate_docs()
        assert len(errors) == 0

    def test_company_generator_validate_prompts(self) -> None:
        gen = CompanyGenerator()
        errors = gen.validate_prompts()
        assert len(errors) == 0

    def test_generator_context_creation(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        assert result.registry is not None
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        ctx = GeneratorContext(
            manifest=manifest,
            registry=result.registry,
            company_dir=Path("company"),
            templates_dir=Path("templates"),
            output_dir=Path("generated"),
        )
        d = ctx.to_dict()
        assert "company" in d
        assert d["company"]["name"] == "AI Enterprise OS Vision"

    def test_planner_creates(self) -> None:
        from ai_company.generator.context import GeneratorContext
        from ai_company.template_engine.context import TemplateContext

        eng = RegistryEngine()
        result = eng.load(Path("company"))
        assert result.registry is not None
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        ctx = GeneratorContext(
            manifest=manifest,
            registry=result.registry,
            company_dir=Path("company"),
            templates_dir=Path("templates"),
            output_dir=Path("generated"),
        )
        planner = GenerationPlanner(ctx, TemplateContext({}))
        plan = planner.create_plan()
        assert plan is not None
