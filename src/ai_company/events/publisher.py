"""Publisher management for the Event Bus."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ai_company.events.models import Event, EventMetadata, EventPriority, EventType

logger = logging.getLogger(__name__)


class Publisher:
    """Represents a component that publishes events to the bus.

    Publishers are identified by source name and can create properly
    formatted Event objects with consistent metadata.
    """

    def __init__(
        self,
        source: str,
        description: str = "",
        default_priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        self.source = source
        self.description = description
        self.default_priority = default_priority
        self.logger = logging.getLogger(f"{self.__class__.__name__}[{source}]")

    def create_event(
        self,
        event_type: EventType,
        payload: Optional[Dict[str, Any]] = None,
        priority: Optional[EventPriority] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        max_retries: int = 3,
        ttl_seconds: Optional[int] = None,
    ) -> Event:
        """Create a properly formatted event for publishing.

        Args:
            event_type: Type of event
            payload: Event data payload
            priority: Override default priority
            correlation_id: Links related events
            causation_id: ID of event that caused this one
            tags: Event tags
            max_retries: Maximum delivery retries
            ttl_seconds: Time-to-live in seconds

        Returns:
            A ready-to-publish Event instance
        """
        metadata = EventMetadata(
            event_type=event_type,
            source=self.source,
            priority=priority or self.default_priority,
            correlation_id=correlation_id,
            causation_id=causation_id,
            tenant_id=None,
            user_id=None,
            tags=tags or [],
            max_retries=max_retries,
            ttl_seconds=ttl_seconds,
        )
        return Event(metadata=metadata, payload=payload or {})

    def __repr__(self) -> str:
        return f"Publisher(source={self.source})"
