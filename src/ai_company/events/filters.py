"""Event filtering for the Event Bus."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from ai_company.events.models import Event, EventPriority, EventType

logger = logging.getLogger(__name__)

# Type alias for filter predicates
FilterPredicate = Callable[[Event], bool]


class EventFilter(ABC):
    """Base class for event filters.

    Filters determine whether an event should be processed by
    a subscriber or should pass through a routing rule.
    """

    @abstractmethod
    def matches(self, event: Event) -> bool:
        """Check if an event passes this filter.

        Args:
            event: The event to check

        Returns:
            True if the event passes the filter
        """
        ...

    def __and__(self, other: EventFilter) -> EventFilter:
        return AndFilter(self, other)

    def __or__(self, other: EventFilter) -> EventFilter:
        return OrFilter(self, other)

    def __invert__(self) -> EventFilter:
        return NotFilter(self)


class TypeFilter(EventFilter):
    """Filter events by their type."""

    def __init__(self, event_types: List[EventType]) -> None:
        self.event_types = event_types

    def matches(self, event: Event) -> bool:
        return event.metadata.event_type in self.event_types


class PriorityFilter(EventFilter):
    """Filter events by priority level."""

    def __init__(self, min_priority: EventPriority) -> None:
        self.min_priority = min_priority

    def matches(self, event: Event) -> bool:
        return event.metadata.priority <= self.min_priority


class SourceFilter(EventFilter):
    """Filter events by source component."""

    def __init__(self, sources: List[str]) -> None:
        self.sources = sources

    def matches(self, event: Event) -> bool:
        return event.metadata.source in self.sources


class TagFilter(EventFilter):
    """Filter events by tags."""

    def __init__(self, required_tags: List[str]) -> None:
        self.required_tags = required_tags

    def matches(self, event: Event) -> bool:
        return all(tag in event.metadata.tags for tag in self.required_tags)


class PayloadFilter(EventFilter):
    """Filter events by payload field values."""

    def __init__(self, conditions: Dict[str, Any]) -> None:
        self.conditions = conditions

    def matches(self, event: Event) -> bool:
        for key, value in self.conditions.items():
            if key not in event.payload:
                return False
            if event.payload[key] != value:
                return False
        return True


class AndFilter(EventFilter):
    """Combine filters with AND logic."""

    def __init__(self, *filters: EventFilter) -> None:
        self.filters = filters

    def matches(self, event: Event) -> bool:
        return all(f.matches(event) for f in self.filters)


class OrFilter(EventFilter):
    """Combine filters with OR logic."""

    def __init__(self, *filters: EventFilter) -> None:
        self.filters = filters

    def matches(self, event: Event) -> bool:
        return any(f.matches(event) for f in self.filters)


class NotFilter(EventFilter):
    """Negate a filter."""

    def __init__(self, filter_: EventFilter) -> None:
        self.filter = filter_

    def matches(self, event: Event) -> bool:
        return not self.filter.matches(event)


class FilterChain:
    """Chain of filters applied in sequence.

    All filters must pass for the event to proceed.
    """

    def __init__(self, filters: Optional[List[EventFilter]] = None) -> None:
        self.filters = filters or []

    def add_filter(self, filter_: EventFilter) -> None:
        """Add a filter to the chain."""
        self.filters.append(filter_)

    def passes(self, event: Event) -> bool:
        """Check if event passes all filters in the chain."""
        if not self.filters:
            return True
        return all(f.matches(event) for f in self.filters)
