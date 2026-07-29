import json
from typing import Any

from ai_company.template_engine.handlers._substitution import walk_and_substitute
from ai_company.template_engine.handlers.base import BaseHandler


class JsonHandler(BaseHandler):
    def __init__(self, indent: int = 2) -> None:
        self.indent = indent

    def render(self, template: str, context: dict[str, Any]) -> str:
        try:
            data = json.loads(template)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON template: {e}") from e
        result = walk_and_substitute(data, context)
        return json.dumps(result, indent=self.indent)
