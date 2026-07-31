"""Subscriber management for the Event Bus."""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

from ai_company.events.models import Event, EventType, SubscriberInfo

logger = logging.getLogger(__name__)

# Type alias for event handler callables
EventHandler = Callable[[Event], Any]


class Subscriber:
    """Represents a registered event subscriber.

    Subscribers register interest in specific event types and provide
    handler callables that are invoked when matching events are published.
    """

    def __init__(
        self,
        subscriber_id: str,
        name: str,
        handler: EventHandler,
        event_types: Optional[List[EventType]] = None,
        description: str = "",
        is_active: bool = True,
        max_retries: int = 3,
        timeout_seconds: int = 30,
    ) -> None:
        self.subscriber_id = subscriber_id
        self.name = name
        self.handler = handler
        self.event_types = event_types or []
        self.description = description
        self.is_active = is_active
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger(f"{self.__class__.__name__}[{name}]")

    def handle(self, event: Event) -> Any:
        """Invoke the subscriber's handler for an event.

        Args:
            event: The event to handle

        Returns:
            Result from the handler

        Raises:
            Exception: Any exception from the handler
        """
        if not self.is_active:
            self.logger.warning(f"Subscriber {self.name} is inactive, skipping")
            return None

        self.logger.debug(f"Handling event: {event.metadata.event_type.value}")
        return self.handler(event)

    def matches(self, event_type: EventType) -> bool:
        """Check if this subscriber handles the given event type.

        Args:
            event_type: The event type to check

        Returns:
            True if the subscriber handles this event type
        """
        return event_type in self.event_types or len(self.event_types) == 0

    def to_info(self) -> SubscriberInfo:
        """Convert to SubscriberInfo model."""
        return SubscriberInfo(
            subscriber_id=self.subscriber_id,
            name=self.name,
            event_types=self.event_types,
            description=self.description,
            is_active=self.is_active,
            max_retries=self.max_retries,
            timeout_seconds=self.timeout_seconds,
        )

    def __repr__(self) -> str:
        return (
            f"Subscriber(id={self.subscriber_id}, name={self.name}, "
            f"types={[e.value for e in self.event_types]})"
        )
