from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ai_company.models.company import (
    BoardEntry,
    CompanyManifest,
    CompanyRegistry,
    DepartmentData,
    ManifestDepartment,
    Role,
    VisionData,
)
from ai_company.registry.loader import load_registry_files, load_yaml
from ai_company.registry.parser import parse_registry
from ai_company.registry.registry import RegistryEngine, registry_engine
from ai_company.registry.resolver import resolve
from ai_company.registry.validator import validate_parsed_data

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestVisionData:
    def test_minimal(self) -> None:
        v = VisionData(name="Test Vision")
        assert v.name == "Test Vision"
        assert v.description is None
        assert v.company_name is None

    def test_full(self) -> None:
        v = VisionData(name="V", description="D", company_name="C")
        assert v.description == "D"
        assert v.company_name == "C"


class TestRole:
    def test_default_description(self) -> None:
        r = Role(title="CEO")
        assert r.title == "CEO"
        assert r.description == ""


class TestDepartmentData:
    def test_default_roles(self) -> None:
        d = DepartmentData(name="eng")
        assert d.name == "eng"
        assert d.roles == []

    def test_with_roles(self) -> None:
        d = DepartmentData(name="eng", roles=[Role(title="Dev")])
        assert len(d.roles) == 1
        assert d.roles[0].title == "Dev"


class TestBoardEntry:
    def test_defaults(self) -> None:
        b = BoardEntry()
        assert b.name is None
        assert b.role is None


class TestCompanyRegistry:
    def test_minimal(self) -> None:
        reg = CompanyRegistry(vision=VisionData(name="V"))
        assert reg.vision.name == "V"
        assert reg.departments == {}
        assert reg.board == []
        assert reg.unresolved_refs == []

    def test_prevents_attribute_reassignment(self) -> None:
        reg = CompanyRegistry(vision=VisionData(name="V"))
        with pytest.raises(ValidationError):
            reg.vision = VisionData(name="X")

    def test_prevents_dict_field_reassignment(self) -> None:
        reg = CompanyRegistry(vision=VisionData(name="V"))
        with pytest.raises(ValidationError):
            reg.departments = {}


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------


class TestLoader:
    def test_load_yaml_exists(self, temp_dir: Path) -> None:
        f = temp_dir / "test.yaml"
        f.write_text("key: value\nnested:\n  a: 1\n")
        result = load_yaml(f)
        assert result is not None
        assert result["key"] == "value"
        assert result["nested"]["a"] == 1

    def test_load_yaml_missing(self, temp_dir: Path) -> None:
        result = load_yaml(temp_dir / "nonexistent.yaml")
        assert result is None

    def test_load_yaml_empty(self, temp_dir: Path) -> None:
        f = temp_dir / "empty.yaml"
        f.write_text("")
        result = load_yaml(f)
        assert result == {}

    def test_load_yaml_invalid(self, temp_dir: Path) -> None:
        f = temp_dir / "bad.yaml"
        f.write_text(": broken yaml :\n  indentation:")
        with pytest.raises(ValueError, match="YAML syntax error"):
            load_yaml(f)

    def test_load_registry_files_success(self) -> None:
        result = load_registry_files(Path("company"))
        assert result.success
        assert "company" in result.data
        assert "departments" in result.data
        assert result.data["company"].get("name") == "AI Enterprise OS Vision"

    def test_load_registry_files_nonexistent_dir(self, temp_dir: Path) -> None:
        result = load_registry_files(temp_dir / "nope")
        assert result.success
        assert result.data == {}

    def test_load_registry_files_partial(self, temp_dir: Path) -> None:
        (temp_dir / "company.yaml").write_text("name: partial\n")
        result = load_registry_files(temp_dir)
        assert result.success
        assert result.data["company"]["name"] == "partial"
        assert "departments" not in result.data


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParser:
    def test_parse_company_full(self) -> None:
        parsed = parse_registry({
            "company": {
                "name": "V",
                "description": "D",
                "company_name": "C",
                "departments": ["eng", "sales"],
            }
        })
        assert parsed["vision"]["name"] == "V"
        assert parsed["vision"]["description"] == "D"
        assert parsed["vision"]["company_name"] == "C"
        assert parsed["department_names"] == ["eng", "sales"]

    def test_parse_company_minimal(self) -> None:
        parsed = parse_registry({"company": {"name": "V"}})
        assert parsed["vision"]["name"] == "V"
        assert parsed["department_names"] == []

    def test_parse_departments(self) -> None:
        parsed = parse_registry({
            "departments": {
                "eng": [{"Dev": "Developer"}, {"QA": "Tester"}],
                "sales": [{"Rep": "Sales Rep"}],
            }
        })
        depts = parsed["departments"]
        assert "eng" in depts
        assert len(depts["eng"]["roles"]) == 2
        assert depts["eng"]["roles"][0]["title"] == "Dev"
        assert depts["eng"]["roles"][0]["description"] == "Developer"

    def test_parse_empty(self) -> None:
        parsed = parse_registry({})
        assert parsed["vision"]["name"] == ""
        assert parsed["departments"] == {}
        assert parsed["board"] == []
        assert parsed["executives"] == []


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------


class TestValidator:
    def test_valid_full(self) -> None:
        parsed = {
            "vision": {"name": "V", "description": "D", "company_name": "C"},
            "department_names": ["eng"],
            "departments": {
                "eng": {"name": "eng", "roles": [{"title": "Dev", "description": "Dev work"}]}
            },
            "board": [],
            "executives": [],
            "policies": [],
            "specialists": [],
            "workflows": [],
        }
        report = validate_parsed_data(parsed)
        assert report.passed
        assert report.errors == []

    def test_invalid_vision(self) -> None:
        parsed = {
            "vision": {},
            "department_names": [],
            "departments": {},
            "board": [],
            "executives": [],
            "policies": [],
            "specialists": [],
            "workflows": [],
        }
        report = validate_parsed_data(parsed)
        assert not report.passed

    def test_invalid_department(self) -> None:
        parsed = {
            "vision": {"name": "V"},
            "department_names": [],
            "departments": {"bad": "not_a_dict"},
            "board": [],
            "executives": [],
            "policies": [],
            "specialists": [],
            "workflows": [],
        }
        report = validate_parsed_data(parsed)
        assert not report.passed

    def test_warning_no_departments(self) -> None:
        parsed = {
            "vision": {"name": "V"},
            "department_names": [],
            "departments": {},
            "board": [],
            "executives": [],
            "policies": [],
            "specialists": [],
            "workflows": [],
        }
        report = validate_parsed_data(parsed)
        assert report.passed
        assert any("no departments" in w.message for w in report.warnings)


# ---------------------------------------------------------------------------
# Resolver tests
# ---------------------------------------------------------------------------


class TestResolver:
    def test_all_matched(self) -> None:
        parsed = {
            "department_names": ["eng", "sales"],
            "departments": {
                "eng": {"name": "eng", "roles": []},
                "sales": {"name": "sales", "roles": []},
            },
        }
        report = resolve(parsed)
        assert report.success
        assert report.unresolved_refs == []

    def test_unresolved_refs(self) -> None:
        parsed = {
            "department_names": ["eng", "missing_dept"],
            "departments": {
                "eng": {"name": "eng", "roles": []},
            },
        }
        report = resolve(parsed)
        assert not report.success
        assert "missing_dept" in report.unresolved_refs

    def test_extra_definition_warning(self) -> None:
        parsed = {
            "department_names": ["eng"],
            "departments": {
                "eng": {"name": "eng", "roles": []},
                "extra": {"name": "extra", "roles": []},
            },
        }
        report = resolve(parsed)
        assert report.success
        assert any("extra" in w for w in report.warnings)

    def test_stub_created_for_unresolved(self) -> None:
        parsed = {
            "department_names": ["orphan"],
            "departments": {},
        }
        report = resolve(parsed)
        assert not report.success
        assert "orphan" in report.resolved["departments"]
        assert report.resolved["departments"]["orphan"]["name"] == "orphan"


# ---------------------------------------------------------------------------
# Registry integration tests
# ---------------------------------------------------------------------------


class TestRegistryEngine:
    def engine(self) -> RegistryEngine:
        return RegistryEngine()

    def test_load_success(self) -> None:
        eng = self.engine()
        result = eng.load(Path("company"))
        assert result.success
        assert result.registry is not None
        assert result.registry.vision.name == "AI Enterprise OS Vision"
        assert result.registry.vision.company_name == "Lightspeed Holdings Limited"

    def test_load_departments_resolved(self) -> None:
        eng = self.engine()
        result = eng.load(Path("company"))
        assert result.success
        reg = result.registry
        assert reg is not None
        assert "executive" in reg.departments
        assert "technical" in reg.departments
        exec_dept = reg.departments["executive"]
        assert len(exec_dept.roles) >= 2
        assert exec_dept.roles[0].title == "CEO"

    def test_singleton(self) -> None:
        e1 = RegistryEngine()
        e2 = RegistryEngine()
        assert e1 is not e2

    def test_reload_clears_cache(self) -> None:
        eng = self.engine()
        eng.load(Path("company"))
        assert eng.registry is not None
        eng.reload()
        with pytest.raises(RuntimeError, match="not loaded"):
            _ = eng.registry

    def test_immutable_registry(self) -> None:
        eng = self.engine()
        result = eng.load(Path("company"))
        assert result.registry is not None
        with pytest.raises(ValidationError):
            result.registry.vision = VisionData(name="X")

    def test_load_from_missing_dir(self, temp_dir: Path) -> None:
        eng = self.engine()
        result = eng.load(temp_dir / "void")
        assert result.success
        assert result.registry is not None
        assert result.registry.vision.name == ""

    def test_last_result_property(self) -> None:
        eng = self.engine()
        assert eng.last_result is None
        eng.load(Path("company"))
        assert eng.last_result is not None
        assert eng.last_result.success


class TestRegistryIntegrationWithRealData:
    def engine(self) -> RegistryEngine:
        return RegistryEngine()

    def test_company_yaml_roundtrip(self) -> None:
        with open("company/company.yaml", "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        assert raw["name"] == "AI Enterprise OS Vision"
        assert raw["company_name"] == "Lightspeed Holdings Limited"

    def test_departments_yaml_structure(self) -> None:
        with open("company/departments.yaml", "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        assert "executive" in raw
        assert isinstance(raw["executive"], list)
        assert len(raw["executive"]) >= 1

    def test_full_load_matches_yaml(self) -> None:
        eng = self.engine()
        result = eng.load(Path("company"))
        assert result.success
        reg = result.registry
        assert reg is not None
        assert reg.vision.name == "AI Enterprise OS Vision"
        assert "executive" in reg.departments
        assert "strategic" in reg.departments
        assert "technical" in reg.departments
        assert "marketing" in reg.departments
        assert "sales" in reg.departments
        assert "research" in reg.departments
        assert "product" in reg.departments


# ---------------------------------------------------------------------------
# Manifest tests
# ---------------------------------------------------------------------------


class TestManifestDepartment:
    def test_minimal(self) -> None:
        d = ManifestDepartment(name="eng")
        assert d.name == "eng"
        assert d.display_name is None
        assert d.description is None

    def test_full(self) -> None:
        d = ManifestDepartment(name="eng", display_name="Engineering", description="Eng team")
        assert d.display_name == "Engineering"
        assert d.description == "Eng team"


class TestCompanyManifest:
    def test_minimal(self) -> None:
        m = CompanyManifest(name="Test Co", departments=[ManifestDepartment(name="eng")])
        assert m.name == "Test Co"
        assert m.description is None
        assert m.version is None
        assert len(m.departments) == 1

    def test_full(self) -> None:
        m = CompanyManifest(
            name="Test Co",
            description="Desc",
            company_name="C",
            version="1.0",
            departments=[ManifestDepartment(name="eng", display_name="Engineering")],
        )
        assert m.company_name == "C"
        assert m.version == "1.0"

    def test_load_from_real_file(self) -> None:
        m = CompanyManifest.load(Path("config/company/company.yaml"))
        assert m.name == "AI Enterprise OS Vision"
        assert m.company_name == "Lightspeed Holdings Limited"
        assert m.version == "1.0.0"
        assert len(m.departments) == 7

    def test_load_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            CompanyManifest.load(Path("nonexistent.yaml"))

    def test_load_empty_file(self, temp_dir: Path) -> None:
        f = temp_dir / "empty.yaml"
        f.write_text("")
        with pytest.raises(ValueError, match="empty"):
            CompanyManifest.load(f)

    def test_load_invalid_yaml(self, temp_dir: Path) -> None:
        f = temp_dir / "bad.yaml"
        f.write_text(": broken :\n  indentation:")
        with pytest.raises(ValueError, match="YAML syntax error"):
            CompanyManifest.load(f)

    def test_load_invalid_schema(self, temp_dir: Path) -> None:
        f = temp_dir / "bad.yaml"
        f.write_text("name: 42")
        with pytest.raises(ValueError, match="Manifest validation failed"):
            CompanyManifest.load(f)

    def test_validate_manifest_success(self) -> None:
        m = CompanyManifest(
            name="Test",
            departments=[ManifestDepartment(name="eng"), ManifestDepartment(name="sales")],
        )
        assert m.validate_manifest() == []

    def test_validate_manifest_missing_name(self) -> None:
        m = CompanyManifest(name="", departments=[ManifestDepartment(name="eng")])
        errors = m.validate_manifest()
        assert any("name" in e for e in errors)

    def test_validate_manifest_no_departments(self) -> None:
        m = CompanyManifest(name="Test")
        errors = m.validate_manifest()
        assert any("department" in e for e in errors)

    def test_validate_manifest_duplicate_departments(self) -> None:
        m = CompanyManifest(
            name="Test",
            departments=[ManifestDepartment(name="eng"), ManifestDepartment(name="eng")],
        )
        errors = m.validate_manifest()
        assert any("duplicate" in e for e in errors)

    def test_normalize_trims_whitespace(self) -> None:
        m = CompanyManifest(
            name="  Test Co  ",
            description="  Desc  ",
            departments=[ManifestDepartment(name="  Eng  ")],
        )
        n = m.normalize()
        assert n.name == "Test Co"
        assert n.description == "Desc"
        assert n.departments[0].name == "eng"

    def test_normalize_lowercases_name(self) -> None:
        m = CompanyManifest(
            name="Test",
            departments=[ManifestDepartment(name="Engineering Dept")],
        )
        n = m.normalize()
        assert n.departments[0].name == "engineering_dept"

    def test_normalize_fills_display_name(self) -> None:
        m = CompanyManifest(
            name="Test",
            departments=[ManifestDepartment(name="eng")],
        )
        n = m.normalize()
        assert n.departments[0].display_name == "Eng"

    def test_real_manifest_normalize(self) -> None:
        m = CompanyManifest.load(Path("config/company/company.yaml"))
        n = m.normalize()
        assert n.name == "AI Enterprise OS Vision"
        assert n.version == "1.0.0"
        assert len(n.departments) == 7
        for d in n.departments:
            assert d.name == d.name.lower()
            assert "_" not in d.name
            assert d.display_name is not None
            assert d.description is not None


class TestManifestWithRegistryEngine:
    def engine(self) -> RegistryEngine:
        return RegistryEngine()

    def test_load_with_manifest(self) -> None:
        eng = self.engine()
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        result = eng.load(Path("company"), manifest=manifest)
        assert result.success
        assert result.manifest is not None
        assert result.manifest.name == "AI Enterprise OS Vision"
        assert result.registry is not None

    def test_load_with_manifest_department_warning(self, temp_dir: Path) -> None:
        eng = self.engine()
        manifest = CompanyManifest(
            name="Test",
            departments=[ManifestDepartment(name="ghost")],
        )
        result = eng.load(Path("company"), manifest=manifest)
        assert result.success
        assert any("ghost" in w for w in result.warnings)

    def test_load_with_manifest_extra_department_warning(self, temp_dir: Path) -> None:
        eng = self.engine()
        manifest = CompanyManifest(
            name="Test",
            departments=[ManifestDepartment(name="executive")],
        )
        result = eng.load(Path("company"), manifest=manifest)
        assert result.success
        assert any("technical" in w for w in result.warnings)

    def test_load_with_invalid_manifest_fails(self, temp_dir: Path) -> None:
        eng = self.engine()
        manifest = CompanyManifest(name="")
        result = eng.load(Path("company"), manifest=manifest)
        assert not result.success
        assert any("manifest" in e for e in result.errors)

    def test_last_result_includes_manifest(self) -> None:
        eng = self.engine()
        manifest = CompanyManifest.load(Path("config/company/company.yaml"))
        result = eng.load(Path("company"), manifest=manifest)
        assert result.manifest is not None
        assert result.manifest.name == "AI Enterprise OS Vision"

    def test_load_without_manifest_still_works(self) -> None:
        eng = self.engine()
        result = eng.load(Path("company"))
        assert result.success
        assert result.manifest is None


class TestFrozenImmutability:
    def engine(self) -> RegistryEngine:
        return RegistryEngine()

    def test_cannot_reassign_root_attr(self) -> None:
        eng = self.engine()
        result = eng.load(Path("company"))
        assert result.registry is not None
        with pytest.raises(ValidationError):
            result.registry.departments = {}

    def test_cannot_reassign_nested_attr(self) -> None:
        result = registry_engine.load(Path("company"))
        assert result.registry is not None
        with pytest.raises(ValidationError):
            result.registry.vision = VisionData(name="X")
