from pathlib import Path

from ai_company.company.board_generator import BoardGenerator
from ai_company.company.department_generator import DepartmentGenerator
from ai_company.company.executive_generator import ExecutiveGenerator
from ai_company.company.generator import CompanyGenerator
from ai_company.company.organization import OrganizationGenerator
from ai_company.company.specialist_generator import SpecialistGenerator
from ai_company.company.workflow_generator import WorkflowGenerator
from ai_company.models.company import CompanyManifest
from ai_company.registry.registry import RegistryEngine


class TestE2ECompanyGeneration:
    def test_company_generator_creates(self) -> None:
        gen = CompanyGenerator()
        assert gen is not None

    def test_company_generator_loads_registry(self) -> None:
        gen = CompanyGenerator()
        result = gen._load_registry()
        assert result is not None
        assert result.vision.name == "AI Enterprise OS Vision"

    def test_company_generator_validate(self) -> None:
        gen = CompanyGenerator()
        errors = gen.validate()
        assert len(errors) == 0

    def test_organization_generator(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        org_gen = OrganizationGenerator(result.registry)
        org_result = org_gen.generate()
        assert org_result.graph is not None
        assert len(org_result.graph.nodes) > 0
        assert len(org_result.graph.edges) >= 0

    def test_organization_summary(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        org_gen = OrganizationGenerator(result.registry)
        org_result = org_gen.generate()
        summary = org_result.summary()
        assert summary["nodes"] > 0
        assert "edges" in summary
        assert "roles" in summary

    def test_board_generator(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        board_gen = BoardGenerator(result.registry, config_dir=Path("config/board"))
        board_result = board_gen.generate()
        assert board_result is not None

    def test_board_validate(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        board_gen = BoardGenerator(result.registry, config_dir=Path("config/board"))
        errors = board_gen.validate()
        assert len(errors) == 0

    def test_executive_generator(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        exec_gen = ExecutiveGenerator(result.registry, manifest)
        exec_result = exec_gen.generate()
        assert exec_result is not None

    def test_department_generator(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        dept_gen = DepartmentGenerator(result.registry, manifest)
        dept_result = dept_gen.generate()
        assert dept_result is not None

    def test_specialist_generator(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        spec_gen = SpecialistGenerator(result.registry, manifest)
        spec_result = spec_gen.generate()
        assert spec_result is not None

    def test_workflow_generator(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        wf_gen = WorkflowGenerator(result.registry)
        wf_result = wf_gen.generate()
        assert wf_result is not None

    def test_organization_roles(self) -> None:
        eng = RegistryEngine()
        result = eng.load(Path("company"))
        org_gen = OrganizationGenerator(result.registry)
        org_result = org_gen.generate()
        assert len(org_result.roles) > 0
