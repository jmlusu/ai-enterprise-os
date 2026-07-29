from ai_company.template_engine.handlers.base import BaseHandler
from ai_company.template_engine.handlers._substitution import substitute


class MarkdownHandler(BaseHandler):
    def render(self, template: str, context: dict) -> str:
        return substitute(template, context)
