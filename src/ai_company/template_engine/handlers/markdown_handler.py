from typing import Any

from ._substitution import substitute
from .base import BaseHandler


class MarkdownHandler(BaseHandler):
    def render(self, template: str, context: dict[str, Any]) -> str:
        return substitute(template, context)
