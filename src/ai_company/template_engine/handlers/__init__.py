from .base import BaseHandler
from .jinja_handler import JinjaHandler
from .json_handler import JsonHandler
from .markdown_handler import MarkdownHandler
from .python_handler import PythonHandler
from .yaml_handler import YamlHandler

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
