from ai_company.template_engine.handlers._substitution import substitute
from ai_company.template_engine.handlers.base import BaseHandler


class PythonHandler(BaseHandler):
    def render(self, template: str, context: dict) -> str:
        return substitute(template, context)
