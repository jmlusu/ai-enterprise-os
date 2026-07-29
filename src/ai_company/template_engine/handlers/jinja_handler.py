from jinja2 import Template as Jinja2Template
from jinja2 import TemplateError

from ai_company.template_engine.handlers.base import BaseHandler


class JinjaHandler(BaseHandler):
    def render(self, template: str, context: dict) -> str:
        try:
            return Jinja2Template(template).render(context)
        except TemplateError as e:
            raise ValueError(f"Jinja2 rendering failed: {e}") from e
