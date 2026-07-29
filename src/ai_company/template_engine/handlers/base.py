from abc import ABC, abstractmethod


class BaseHandler(ABC):
    @abstractmethod
    def render(self, template: str, context: dict) -> str:
        ...
