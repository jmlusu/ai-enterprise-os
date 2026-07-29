import json
from collections.abc import ItemsView
from pathlib import Path
from typing import Any

import yaml


class TemplateContext:
    def __init__(self, variables: dict[str, Any] | None = None) -> None:
        self._variables: dict[str, Any] = dict(variables or {})

    @classmethod
    def from_dict(cls, variables: dict[str, Any]) -> "TemplateContext":
        return cls(variables)

    @classmethod
    def from_file(cls, path: Path) -> "TemplateContext":
        content = path.read_text(encoding="utf-8")
        if path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(content)
        elif path.suffix == ".json":
            data = json.loads(content)
        else:
            raise ValueError(f"Unsupported context file format: {path.suffix}")
        if not isinstance(data, dict):
            raise TypeError(f"Context file must contain a mapping, got {type(data).__name__}")
        return cls(data)

    def get(self, key: str, default: Any = None) -> Any:
        parts = key.split(".")
        val: Any = self._variables
        for part in parts:
            if isinstance(val, dict):
                val = val.get(part, default)
            else:
                return default
        return val

    def merge(self, other: "TemplateContext | dict[str, Any]") -> "TemplateContext":
        if isinstance(other, TemplateContext):
            other = other._variables
        merged = {**self._variables}
        for k, v in other.items():
            if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v
        return TemplateContext(merged)

    def validate(self, required_keys: list[str]) -> list[str]:
        missing: list[str] = []
        for key in required_keys:
            if self.get(key) is None:
                missing.append(key)
        return missing

    def to_dict(self) -> dict[str, Any]:
        return dict(self._variables)

    def keys(self) -> set[str]:
        return set(self._variables.keys())

    def items(self) -> ItemsView[str, Any]:
        return self._variables.items()
