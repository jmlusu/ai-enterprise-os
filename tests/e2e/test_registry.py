from pathlib import Path

from ai_company.models.company import CompanyManifest
from ai_company.registry.registry import RegistryEngine


class TestE2ERegistry:
    def test_registry_loads(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        assert result.success
        assert result.registry is not None

    def test_registry_vision_name(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        assert result.registry is not None
        assert result.registry.vision.name == "AI Enterprise OS Vision"

    def test_registry_company_name(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        assert result.registry is not None
        assert result.registry.vision.company_name == "Lightspeed Holdings Limited"

    def test_registry_departments_present(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        assert result.registry is not None
        assert len(result.registry.departments) > 0

    def test_registry_core_departments(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        assert result.registry is not None
        for dept in ["executive", "engineering", "finance", "operations", "ai"]:
            assert dept in result.registry.departments, f"Missing: {dept}"

    def test_registry_executives_present(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        assert result.registry is not None
        assert len(result.registry.executives) > 0

    def test_registry_no_errors(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        assert len(result.errors) == 0, f"Errors: {result.errors}"

    def test_registry_with_manifest(self) -> None:
        eng = RegistryEngine()
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        result = eng.load(Path("company"), manifest=manifest)
        assert result.success
        assert result.manifest is not None

    def test_registry_fails_on_bad_path(self, tmp_path) -> None:
        eng = RegistryEngine()
        result = eng.load(tmp_path / "void")
        assert result.registry is not None
