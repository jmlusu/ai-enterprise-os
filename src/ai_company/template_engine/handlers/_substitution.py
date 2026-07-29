import re
from typing import Any

_VAR_PATTERN = re.compile(r"\{(\w+(?:\.\w+)*)\}")


def substitute(template: str, context: dict[str, Any]) -> str:
    def _replace(m: re.Match[str]) -> str:
        key = m.group(1)
        parts = key.split(".")
        val: Any = context
        for part in parts:
            if isinstance(val, dict):
                val = val.get(part, m.group(0))
            else:
                return m.group(0)
        if val is None:
            return m.group(0)
        return str(val)

    return _VAR_PATTERN.sub(_replace, template)


def walk_and_substitute(obj: Any, context: dict[str, Any]) -> Any:
    if isinstance(obj, str):
        return substitute(obj, context)
    if isinstance(obj, dict):
        return {k: walk_and_substitute(v, context) for k, v in obj.items()}
    if isinstance(obj, list):
        return [walk_and_substitute(v, context) for v in obj]
    return obj


_YAML_PLACEHOLDER = "__YTPL_{}__"


def protect_yaml_vars(template: str) -> tuple[str, list[str]]:
    keys: list[str] = []

    def _replace(m: re.Match[str]) -> str:
        keys.append(m.group(1))
        return _YAML_PLACEHOLDER.format(len(keys) - 1)

    protected = _VAR_PATTERN.sub(_replace, template)
    return protected, keys


def resolve_yaml_placeholders(
    obj: Any, keys: list[str], context: dict[str, Any]
) -> Any:
    if isinstance(obj, str):
        result = obj
        for i, key in enumerate(keys):
            placeholder = _YAML_PLACEHOLDER.format(i)
            if placeholder in result:
                val = _resolve_key(key, context)
                if result == placeholder:
                    return val if val is not None else result
                result = result.replace(
                    placeholder, str(val) if val is not None else ""
                )
        return result
    if isinstance(obj, dict):
        return {k: resolve_yaml_placeholders(v, keys, context) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_yaml_placeholders(v, keys, context) for v in obj]
    return obj


def _resolve_key(key: str, context: dict[str, Any]) -> Any:
    parts = key.split(".")
    val: Any = context
    for part in parts:
        if isinstance(val, dict):
            val = val.get(part, None)
        else:
            return None
    return val
