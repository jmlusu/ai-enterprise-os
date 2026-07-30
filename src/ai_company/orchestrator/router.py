"""Task router for AI Enterprise OS Orchestration Layer."""

from __future__ import annotations

import logging
from typing import Any, cast


class TaskRouter:
    """Routes tasks to appropriate engines based on task type and parameters."""

    def __init__(self) -> None:
        self._routes: dict[str, str] = {
            "load_registry": "registry",
            "validate": "registry",
            "generate": "generator",
            "create_decision": "decision",
            "evaluate_decision": "decision",
            "save_memory": "memory",
            "search_memory": "memory",
            "audit_record": "audit",
            "audit_query": "audit",
        }
        self._default_target: str = "unknown"
        self.logger = logging.getLogger(self.__class__.__name__)

    def route(self, task_type: str, params: dict[str, Any] | None = None) -> str:
        """Determine the target engine for a task."""
        target = self._routes.get(task_type)
        if target:
            return target

        # Fallback: use params override
        if params and "target" in params:
            return cast(str, params["target"])

        self.logger.warning(f"No route for task type: {task_type}")
        return self._default_target

    def add_route(self, task_type: str, target: str) -> None:
        """Add or override a route."""
        self._routes[task_type] = target

    def remove_route(self, task_type: str) -> bool:
        """Remove a route."""
        return self._routes.pop(task_type, None) is not None

    def list_routes(self) -> dict[str, str]:
        """List all registered routes."""
        return dict(self._routes)
