from ai_company.template_engine.handlers.base import BaseHandler
from ai_company.template_engine.handlers.jinja_handler import JinjaHandler
from ai_company.template_engine.handlers.json_handler import JsonHandler
from ai_company.template_engine.handlers.markdown_handler import MarkdownHandler
from ai_company.template_engine.handlers.python_handler import PythonHandler
from ai_company.template_engine.handlers.yaml_handler import YamlHandler

DEFAULT_HANDLERS: dict[str, type[BaseHandler]] = {
    "jinja": JinjaHandler,
    "python": PythonHandler,
    "markdown": MarkdownHandler,
    "json": JsonHandler,
    "yaml": YamlHandler,
}

__all__ = [
    "DEFAULT_HANDLERS",
    "BaseHandler",
    "JinjaHandler",
    "JsonHandler",
    "MarkdownHandler",
    "PythonHandler",
    "YamlHandler",
]
