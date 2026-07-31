"""Decision routing table for AI Enterprise OS Decision Engine."""

from __future__ import annotations

import logging
from typing import Any

from ai_company.decision.models import Decision


class RouteEntry:
    """A single route in the routing table."""

    def __init__(
        self,
        route_id: str,
        name: str,
        category: str | None = None,
        min_priority: int = 0,
        max_priority: int = 5,
        destination: str = "",
        conditions: dict[str, Any] | None = None,
        fallback: str = "",
        timeout: int = 3600,
        retry_count: int = 0,
    ) -> None:
        self.route_id = route_id
        self.name = name
        self.category = category
        self.min_priority = min_priority
        self.max_priority = max_priority
        self.destination = destination
        self.conditions = conditions or {}
        self.fallback = fallback
        self.timeout = timeout
        self.retry_count = retry_count

    def matches(self, decision: Decision) -> bool:
        """Check if this route applies to the given decision."""
        if self.category and decision.category.value != self.category:
            return False
        priority = decision.priority.value
        if priority < self.min_priority or priority > self.max_priority:
            return False
        for key, value in self.conditions.items():
            if decision.context.get(key) != value:
                return False
        return True


class RoutingTable:
    """Routing table for directing decisions to appropriate handlers."""

    def __init__(self) -> None:
        self.routes: list[RouteEntry] = []
        self.default_route: str = "default_handler"
        self.logger = logging.getLogger(self.__class__.__name__)

    def add_route(self, route: RouteEntry) -> None:
        self.routes.append(route)

    def route_decision(self, decision: Decision) -> str:
        """Find the appropriate route for a decision."""
        for route in self.routes:
            if route.matches(decision):
                self.logger.debug(
                    f"Routing decision {decision.id} to {route.destination}"
                )
                return route.destination
        self.logger.debug(
            f"Routing decision {decision.id} to default: {self.default_route}"
        )
        return self.default_route

    def find_route(self, route_id: str) -> RouteEntry | None:
        """Find a route by ID."""
        for route in self.routes:
            if route.route_id == route_id:
                return route
        return None

    def remove_route(self, route_id: str) -> bool:
        """Remove a route by ID."""
        for i, route in enumerate(self.routes):
            if route.route_id == route_id:
                del self.routes[i]
                return True
        return False

    def clear(self) -> None:
        self.routes.clear()
