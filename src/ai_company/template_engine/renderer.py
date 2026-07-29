from ai_company.template_engine.handlers import DEFAULT_HANDLERS, BaseHandler


class Renderer:
    def __init__(self, handlers: dict[str, type[BaseHandler]] | None = None) -> None:
        self._handlers: dict[str, BaseHandler] = {}
        handler_classes = handlers if handlers is not None else DEFAULT_HANDLERS
        for fmt, cls in handler_classes.items():
            self._handlers[fmt] = cls()

    def render(self, template: str, context: dict, fmt: str = "jinja") -> str:
        handler = self._handlers.get(fmt)
        if handler is None:
            available = ", ".join(sorted(self._handlers))
            raise ValueError(f"Unknown format '{fmt}'. Available formats: {available}")
        return handler.render(template, context)

    def register_handler(self, fmt: str, handler: BaseHandler) -> None:
        self._handlers[fmt] = handler
