"""End-to-end documentation generation pipeline tests."""

from pathlib import Path

from ai_company.company.doc_generator import DocGenerator
from ai_company.models.company import CompanyManifest
from ai_company.registry.registry import RegistryEngine


class TestE2EDocPipeline:
    def test_full_pipeline_generates_docs(self, tmp_path) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        gen = DocGenerator(result.registry, manifest)
        doc_result = gen.generate()
        assert len(doc_result.pages) > 0
        paths = gen.write_artifacts(doc_result, tmp_path)
        assert len(paths) > 0
        for p in paths:
            assert p.exists()
            assert p.stat().st_size > 0

    def test_doc_pipeline_all_page_types(self, tmp_path) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        gen = DocGenerator(result.registry, manifest)
        doc_result = gen.generate()
        types = {p["type"] for p in doc_result.pages}
        for required in ["executive", "department"]:
            assert required in types
        gen.write_artifacts(doc_result, tmp_path)
        index_file = tmp_path / "docs" / "INDEX.md"
        assert index_file.exists()
        assert "executive" in index_file.read_text().lower()

    def test_doc_pipeline_content_non_empty(self, tmp_path) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        gen = DocGenerator(result.registry, manifest)
        doc_result = gen.generate()
        gen.write_artifacts(doc_result, tmp_path)
        md_files = list(tmp_path.rglob("*.md"))
        assert len(md_files) > 0
        for f in md_files:
            content = f.read_text()
            assert len(content) > 50

    def test_doc_pipeline_regenerates(self, tmp_path) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        gen = DocGenerator(result.registry, manifest)
        r1 = gen.generate()
        r2 = gen.generate()
        assert len(r1.pages) == len(r2.pages)

    def test_doc_pipeline_output_structure(self, tmp_path) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        gen = DocGenerator(result.registry, manifest)
        doc_result = gen.generate()
        gen.write_artifacts(doc_result, tmp_path)
        docs_dir = tmp_path / "docs"
        assert docs_dir.is_dir()
        md_files = list(docs_dir.rglob("*.md"))
        assert len(md_files) > 0
        assert (docs_dir / "INDEX.md").exists()
