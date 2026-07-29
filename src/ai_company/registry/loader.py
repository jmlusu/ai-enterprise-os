from pathlib import Path
from typing import Any

import yaml

REGISTRY_FILES: list[str] = [
    "company.yaml",
    "departments.yaml",
    "board.yaml",
    "executives.yaml",
    "policies.yaml",
    "specialists.yaml",
    "workflows.yaml",
]

CONFIG_REGISTRY_FILES: list[str] = [
    "vision.yaml",
    "strategy.yaml",
    "culture.yaml",
    "governance.yaml",
    "policies.yaml",
    "kpis.yaml",
    "budget.yaml",
]


class LoadResult:
    def __init__(self, data: dict[str, dict[str, Any]], errors: list[str]) -> None:
        self.data = data
        self.errors = errors

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


def load_yaml(filepath: Path) -> dict[str, Any] | None:
    if not filepath.exists():
        return None
    if filepath.stat().st_size == 0:
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            result = yaml.safe_load(f)
            return result if isinstance(result, dict) else {}
    except yaml.YAMLError as e:
        raise ValueError(f"YAML syntax error in '{filepath.name}': {e}")


def load_registry_files(company_dir: Path) -> LoadResult:
    data: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for filename in REGISTRY_FILES:
        filepath = company_dir / filename
        try:
            content = load_yaml(filepath)
            if content is not None:
                key = filename.replace(".yaml", "")
                data[key] = content
        except ValueError as e:
            errors.append(str(e))

    return LoadResult(data, errors)


def load_config_registry(config_dir: Path) -> LoadResult:
    """Load extended configuration files from config/company/ directory.

    Returns a LoadResult with keys matching the config filenames.
    """
    data: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for filename in CONFIG_REGISTRY_FILES:
        filepath = config_dir / filename
        try:
            content = load_yaml(filepath)
            if content is not None:
                key = filename.replace(".yaml", "")
                data[key] = content
        except ValueError as e:
            errors.append(str(e))

    return LoadResult(data, errors)
