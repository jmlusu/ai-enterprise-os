from pathlib import Path

from ai_company.validator.manifest_validator import validate_manifest_file
from ai_company.validator.output_validator import validate_generated_directory
from ai_company.validator.registry_validator import validate_registry_integrity
from ai_company.validator.reports import ValidationReport, ValidatorResult
from ai_company.validator.template_validator import validate_templates_directory
from ai_company.validator.yaml_validator import validate_yaml_directory


class ValidatorEngine:
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

    def validate_all(self) -> ValidatorResult:
        reports: list[ValidationReport] = [
            self.validate_yaml(),
            self.validate_registry(),
            self.validate_templates(),
            self.validate_manifest(),
            self.validate_output(),
        ]
        return ValidatorResult(reports=reports)

    def validate_yaml(self) -> ValidationReport:
        return validate_yaml_directory(self.company_dir)

    def validate_registry(self) -> ValidationReport:
        return validate_registry_integrity(self.company_dir)

    def validate_templates(self) -> ValidationReport:
        return validate_templates_directory(self.templates_dir)

    def validate_manifest(self) -> ValidationReport:
        return validate_manifest_file(self.manifest_path)

    def validate_output(self) -> ValidationReport:
        return validate_generated_directory(self.output_dir)
