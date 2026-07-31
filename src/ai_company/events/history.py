"""Event History for the Event Bus.

Provides an audit trail of all event activity including publishing,
delivery, failures, and replay operations. In-memory ring buffer
with optional persistence.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ai_company.events.models import DeliveryResult, Event, EventStatus

logger = logging.getLogger(__name__)


@dataclass
class HistoryEntry:
    """A single entry in the event history/audit log.

    Attributes:
        event_id: The event ID
        event_type: Type of event
        source: Source component
        action: Action taken (published, delivered, failed, replayed, dead_lettered)
        timestamp: When the action occurred
        details: Additional details (subscriber, error, etc.)
    """

    event_id: str
    event_type: str
    source: str
    action: str  # published, delivered, failed, replayed, dead_lettered
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: Dict[str, Any] = field(default_factory=dict)


class EventHistory:
    """Maintains an event audit trail.

    Uses an in-memory ring buffer to limit memory usage while
    retaining the most recent history. Supports filtering and
    export.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self.max_entries = max_entries
        self._entries: deque[HistoryEntry] = deque(maxlen=max_entries)
        self.logger = logging.getLogger(self.__class__.__name__)

    def record_publish(self, event: Event) -> None:
        """Record an event publication."""
        self._entries.append(
            HistoryEntry(
                event_id=event.metadata.event_id,
                event_type=event.metadata.event_type.value,
                source=event.metadata.source,
                action="published",
                details={
                    "priority": event.metadata.priority.value,
                    "correlation_id": event.metadata.correlation_id,
                },
            )
        )

    def record_delivery(self, event: Event, result: DeliveryResult) -> None:
        """Record an event delivery result."""
        action = "delivered" if result.status == EventStatus.DELIVERED else "failed"
        details: Dict[str, Any] = {
            "subscriber": result.subscriber_name,
        }
        if result.processing_time_ms is not None:
            details["processing_time_ms"] = result.processing_time_ms
        if result.error:
            details["error"] = result.error

        self._entries.append(
            HistoryEntry(
                event_id=event.metadata.event_id,
                event_type=event.metadata.event_type.value,
                source=event.metadata.source,
                action=action,
                details=details,
            )
        )

    def record_dead_letter(
        self, event: Event, subscriber_name: str, error: str
    ) -> None:
        """Record a dead letter event."""
        self._entries.append(
            HistoryEntry(
                event_id=event.metadata.event_id,
                event_type=event.metadata.event_type.value,
                source=event.metadata.source,
                action="dead_lettered",
                details={
                    "subscriber": subscriber_name,
                    "error": error,
                },
            )
        )

    def record_replay(self, event_type: str, replay_count: int) -> None:
        """Record a replay operation."""
        self._entries.append(
            HistoryEntry(
                event_id="replay_batch",
                event_type=event_type,
                source="replay_engine",
                action="replayed",
                details={"count": replay_count},
            )
        )

    def get_history(
        self,
        limit: int = 100,
        event_type: Optional[str] = None,
        action: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[HistoryEntry]:
        """Get filtered event history.

        Args:
            limit: Maximum entries to return
            event_type: Filter by event type
            action: Filter by action
            source: Filter by source

        Returns:
            List of matching history entries
        """
        entries = list(self._entries)

        if event_type:
            entries = [e for e in entries if e.event_type == event_type]
        if action:
            entries = [e for e in entries if e.action == action]
        if source:
            entries = [e for e in entries if e.source == source]

        return entries[-limit:]

    def get_recent(self, limit: int = 20) -> List[HistoryEntry]:
        """Get the most recent history entries."""
        return list(self._entries)[-limit:]

    def count(self) -> int:
        """Return total number of history entries."""
        return len(self._entries)

    def clear(self) -> None:
        """Clear all history entries."""
        self._entries.clear()

    def export(self) -> List[Dict[str, Any]]:
        """Export all history as serializable dicts."""
        return [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "source": e.source,
                "action": e.action,
                "timestamp": e.timestamp.isoformat(),
                "details": e.details,
            }
            for e in self._entries
        ]
