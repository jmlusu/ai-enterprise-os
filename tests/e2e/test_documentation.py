from pathlib import Path

from ai_company.company.doc_generator import DocGenerator
from ai_company.company.generator import CompanyGenerator
from ai_company.models.company import CompanyManifest
from ai_company.registry.registry import RegistryEngine


class TestE2EDocumentation:
    def test_doc_generator_creates(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        gen = DocGenerator(result.registry, manifest)
        assert gen is not None

    def test_doc_generator_generates_pages(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        gen = DocGenerator(result.registry, manifest)
        doc_result = gen.generate()
        assert len(doc_result.pages) > 0

    def test_doc_generator_executive_pages(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        gen = DocGenerator(result.registry, manifest)
        doc_result = gen.generate()
        types = {p["type"] for p in doc_result.pages}
        assert "executive" in types

    def test_doc_generator_department_pages(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        gen = DocGenerator(result.registry, manifest)
        doc_result = gen.generate()
        types = {p["type"] for p in doc_result.pages}
        assert "department" in types

    def test_doc_generator_writes_artifacts(self, tmp_path) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        gen = DocGenerator(result.registry, manifest)
        doc_result = gen.generate()
        paths = gen.write_artifacts(doc_result, tmp_path)
        assert len(paths) > 0
        for p in paths:
            assert p.exists()

    def test_doc_generator_validate(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        gen = DocGenerator(result.registry)
        errors = gen.validate()
        assert len(errors) == 0

    def test_company_gen_docs(self) -> None:
        gen = CompanyGenerator()
        errors = gen.validate_docs()
        assert len(errors) == 0

    def test_doc_pages_have_markdown(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        gen = DocGenerator(result.registry, manifest)
        doc_result = gen.generate()
        for page in doc_result.pages:
            assert "markdown" in page
            assert len(page["markdown"]) > 0

    def test_doc_index_written(self, tmp_path) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        gen = DocGenerator(result.registry, manifest)
        doc_result = gen.generate()
        gen.write_artifacts(doc_result, tmp_path)
        assert (tmp_path / "docs" / "INDEX.md").exists()
