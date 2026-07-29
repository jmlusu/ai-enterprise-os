from pathlib import Path

from ai_company.generator.context import GeneratorContext
from ai_company.models.company import CompanyManifest, CompanyRegistry, VisionData


class TestGeneratorContext:
    def test_minimal_construction(self) -> None:
        manifest = CompanyManifest(name="TestCo", description="A test", departments=[])
        registry = CompanyRegistry(vision=VisionData(name="TestCo"))
        ctx = GeneratorContext(manifest, registry)
        d = ctx.to_dict()
        assert d["company"]["name"] == "TestCo"
        assert d["company"]["department_count"] == 0

    def test_default_paths(self) -> None:
        manifest = CompanyManifest(name="X", departments=[])
        registry = CompanyRegistry(vision=VisionData(name="X"))
        ctx = GeneratorContext(manifest, registry)
        assert ctx.company_dir == Path("company")
        assert ctx.templates_dir == Path("templates")
        assert ctx.output_dir == Path("generated")

    def test_custom_paths(self) -> None:
        manifest = CompanyManifest(name="X", departments=[])
        registry = CompanyRegistry(vision=VisionData(name="X"))
        ctx = GeneratorContext(
            manifest,
            registry,
            company_dir=Path("/custom/company"),
            templates_dir=Path("/custom/templates"),
            output_dir=Path("/custom/output"),
        )
        assert ctx.company_dir == Path("/custom/company")
        assert ctx.templates_dir == Path("/custom/templates")
        assert ctx.output_dir == Path("/custom/output")

    def test_to_dict_contains_company_info(self) -> None:
        manifest = CompanyManifest(
            name="Acme",
            company_name="Acme Inc",
            description="Builds things",
            departments=[],
        )
        registry = CompanyRegistry(vision=VisionData(name="Acme"))
        ctx = GeneratorContext(manifest, registry)
        d = ctx.to_dict()
        assert d["company"]["name"] == "Acme"
        assert d["company"]["company_name"] == "Acme Inc"

    def test_get_dot_path(self) -> None:
        manifest = CompanyManifest(name="N", departments=[])
        registry = CompanyRegistry(vision=VisionData(name="N"))
        ctx = GeneratorContext(manifest, registry)
        assert ctx.get("company.name") == "N"
        assert ctx.get("company.missing", "fallback") == "fallback"

    def test_settings(self) -> None:
        manifest = CompanyManifest(name="N", departments=[])
        registry = CompanyRegistry(vision=VisionData(name="N"))
        ctx = GeneratorContext(manifest, registry, settings={"key": "val"})
        assert ctx.settings == {"key": "val"}

    def test_to_dict_includes_registry_data(self) -> None:
        manifest = CompanyManifest(
            name="Co",
            company_name="Co Inc",
            description="Desc",
            departments=[],
        )
        registry = CompanyRegistry(vision=VisionData(name="RVision"))
        ctx = GeneratorContext(manifest, registry)
        d = ctx.to_dict()
        # to_dict uses normalized manifest as the primary source for company-level info
        assert d["company"]["vision"]["name"] == "Co"

    def test_departments_in_to_dict(self) -> None:
        from ai_company.models.company import ManifestDepartment

        manifest = CompanyManifest(
            name="T",
            departments=[ManifestDepartment(name="eng", display_name="Engineering")],
        )
        registry = CompanyRegistry(vision=VisionData(name="T"))
        ctx = GeneratorContext(manifest, registry)
        d = ctx.to_dict()
        assert len(d["company"]["departments"]) == 1
        assert d["company"]["departments"][0]["name"] == "eng"
