from typing import Any

from ._substitution import substitute
from .base import BaseHandler


class PythonHandler(BaseHandler):
    def render(self, template: str, context: dict[str, Any]) -> str:
        result = substitute(template, context)
        return str(result)
