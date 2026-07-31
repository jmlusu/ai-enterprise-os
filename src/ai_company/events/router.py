"""Event routing engine for the Event Bus.

Routes events to subscribers based on routing rules that combine
filters with target subscribers. Supports conditional routing,
fallback routes, and route priority.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ai_company.events.filters import FilterChain
from ai_company.events.models import Event, EventType
from ai_company.events.subscriber import Subscriber

logger = logging.getLogger(__name__)


@dataclass
class Route:
    """A single routing rule mapping filters to a subscriber.

    Attributes:
        name: Unique route name
        subscriber: The target subscriber
        filter_chain: Filters that events must pass to use this route
        priority: Route evaluation priority (lower = evaluated first)
        description: Human-readable description
    """

    name: str
    subscriber: Subscriber
    filter_chain: FilterChain = field(default_factory=FilterChain)
    priority: int = 100
    description: str = ""


class Router:
    """Routes events to subscribers based on configurable rules.

    Routes are evaluated in priority order. The first matching route
    determines the subscriber that receives the event.
    """

    def __init__(self) -> None:
        self._routes: List[Route] = []
        self.logger = logging.getLogger(self.__class__.__name__)

    def add_route(self, route: Route) -> None:
        """Register a route.

        Args:
            route: The route to add
        """
        self._routes.append(route)
        self._routes.sort(key=lambda r: r.priority)
        self.logger.debug(f"Registered route: {route.name} -> {route.subscriber.name}")

    def add_subscriber_route(
        self,
        name: str,
        subscriber: Subscriber,
        event_types: Optional[List[EventType]] = None,
        priority: int = 100,
        description: str = "",
    ) -> Route:
        """Create and register a route that matches by event types.

        This is a convenience method for the common case of routing
        specific event types to a subscriber.

        Args:
            name: Route name
            subscriber: Target subscriber
            event_types: Event types to match (None = all types)
            priority: Route priority
            description: Route description

        Returns:
            The created Route
        """
        from ai_company.events.filters import TypeFilter

        chain = FilterChain()
        if event_types:
            chain.add_filter(TypeFilter(event_types))

        route = Route(
            name=name,
            subscriber=subscriber,
            filter_chain=chain,
            priority=priority,
            description=description,
        )
        self.add_route(route)
        return route

    def remove_route(self, name: str) -> bool:
        """Remove a route by name.

        Args:
            name: Route name to remove

        Returns:
            True if route was found and removed
        """
        for i, route in enumerate(self._routes):
            if route.name == name:
                self._routes.pop(i)
                self.logger.debug(f"Removed route: {name}")
                return True
        return False

    def route_event(self, event: Event) -> List[Subscriber]:
        """Find all subscribers that should receive an event.

        Evaluates all routes in priority order and returns the
        subscribers for matching routes.

        Args:
            event: The event to route

        Returns:
            List of subscribers that match the event
        """
        subscribers: List[Subscriber] = []
        for route in self._routes:
            if route.subscriber in subscribers:
                continue
            if route.filter_chain.passes(event):
                subscribers.append(route.subscriber)
        return subscribers

    def has_route(self, name: str) -> bool:
        """Check if a route exists."""
        return any(r.name == name for r in self._routes)

    def get_route(self, name: str) -> Optional[Route]:
        """Get a route by name."""
        for r in self._routes:
            if r.name == name:
                return r
        return None

    def list_routes(self) -> List[Dict[str, Any]]:
        """List all registered routes."""
        return [
            {
                "name": r.name,
                "subscriber": r.subscriber.name,
                "priority": r.priority,
                "description": r.description,
            }
            for r in self._routes
        ]

    def clear(self) -> None:
        """Remove all routes."""
        self._routes.clear()

    @property
    def route_count(self) -> int:
        """Number of registered routes."""
        return len(self._routes)
