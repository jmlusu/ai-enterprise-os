from pathlib import Path

from ai_company.generator.context import GeneratorContext
from ai_company.generator.prompt_generator import PromptGenerator
from ai_company.models.company import (
    CompanyManifest,
    CompanyRegistry,
    ExecutiveEntry,
    SpecialistEntry,
    VisionData,
)


class TestPromptGenerator:
    def test_init(self) -> None:
        manifest = CompanyManifest(name="P", departments=[])
        registry = CompanyRegistry(vision=VisionData(name="P"))
        ctx = GeneratorContext(manifest, registry)
        gen = PromptGenerator(ctx)
        assert gen.context is ctx

    def test_generate_executive_prompt(self) -> None:
        manifest = CompanyManifest(
            name="TestCo",
            company_name="TestCo Inc",
            description="A test company",
            departments=[],
        )
        registry = CompanyRegistry(
            vision=VisionData(name="TVision"),
            executives=[ExecutiveEntry(name="Alice", title="CEO")],
        )
        ctx = GeneratorContext(manifest, registry)
        gen = PromptGenerator(ctx)
        prompt = gen.generate_executive_prompt("Alice")
        assert "Alice" in prompt
        assert "CEO" in prompt
        assert "TestCo Inc" in prompt

    def test_generate_executive_prompt_not_found(self) -> None:
        manifest = CompanyManifest(name="T", departments=[])
        registry = CompanyRegistry(vision=VisionData(name="T"))
        ctx = GeneratorContext(manifest, registry)
        gen = PromptGenerator(ctx)
        prompt = gen.generate_executive_prompt("Nobody")
        assert "not found" in prompt

    def test_generate_specialist_prompt(self) -> None:
        manifest = CompanyManifest(
            name="TestCo",
            company_name="TestCo Inc",
            description="A test",
            departments=[],
        )
        registry = CompanyRegistry(
            vision=VisionData(name="TVision"),
            specialists=[SpecialistEntry(name="Bob", expertise="Security")],
        )
        ctx = GeneratorContext(manifest, registry)
        gen = PromptGenerator(ctx)
        prompt = gen.generate_specialist_prompt("Bob")
        assert "Bob" in prompt
        assert "Security" in prompt

    def test_generate_specialist_prompt_not_found(self) -> None:
        manifest = CompanyManifest(name="T", departments=[])
        registry = CompanyRegistry(vision=VisionData(name="T"))
        ctx = GeneratorContext(manifest, registry)
        gen = PromptGenerator(ctx)
        prompt = gen.generate_specialist_prompt("Nobody")
        assert "not found" in prompt

    def test_generate_department_prompt(self) -> None:
        manifest = CompanyManifest(
            name="T",
            company_name="TC",
            departments=[],
        )
        registry = CompanyRegistry(vision=VisionData(name="T"))
        ctx = GeneratorContext(manifest, registry)
        gen = PromptGenerator(ctx)
        prompt = gen.generate_department_prompt("eng")
        assert "not found" in prompt or "eng" in prompt

    def test_generate_all_creates_files(self, tmp_path: Path) -> None:
        manifest = CompanyManifest(
            name="TestCo",
            company_name="TestCo Inc",
            description="A test",
            departments=[],
        )
        registry = CompanyRegistry(
            vision=VisionData(name="TVision"),
            executives=[ExecutiveEntry(name="Alice", title="CEO")],
            specialists=[SpecialistEntry(name="Bob", expertise="Security")],
        )
        ctx = GeneratorContext(manifest, registry)
        gen = PromptGenerator(ctx)
        out = tmp_path / "prompts"
        created = gen.generate_all(output_dir=out)
        assert len(created) > 0
        assert all(p.exists() for p in created)
