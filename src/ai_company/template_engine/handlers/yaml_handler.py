from typing import Any

import yaml

from ai_company.template_engine.handlers._substitution import (
    protect_yaml_vars,
    resolve_yaml_placeholders,
)
from ai_company.template_engine.handlers.base import BaseHandler


class YamlHandler(BaseHandler):
    def render(self, template: str, context: dict[str, Any]) -> str:
        protected, keys = protect_yaml_vars(template)
        try:
            data = yaml.safe_load(protected)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML template: {e}") from e
        if data is None:
            return ""
        result = resolve_yaml_placeholders(data, keys, context)
        return yaml.safe_dump(result, default_flow_style=False, allow_unicode=True).strip()
