"""Priority processing for the Event Bus."""

from __future__ import annotations

import heapq
import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ai_company.events.models import Event, EventPriority

logger = logging.getLogger(__name__)


@dataclass(order=True)
class PrioritizedEvent:
    """Wrapper for events with priority ordering.

    Uses negative priority index so CRITICAL (index 0) is processed first.
    """

    priority_index: int
    created_at: float = field(compare=False)
    sequence: int = field(compare=False)
    event: Event = field(compare=False)


class PriorityProcessor:
    """Processes events in priority order using a priority queue.

    CRITICAL events are always processed before HIGH, HIGH before NORMAL,
    NORMAL before LOW, LOW before BACKGROUND.
    Within the same priority level, events are processed FIFO.
    """

    PRIORITY_ORDER: Dict[EventPriority, int] = {
        EventPriority.CRITICAL: 0,
        EventPriority.HIGH: 1,
        EventPriority.NORMAL: 2,
        EventPriority.LOW: 3,
        EventPriority.BACKGROUND: 4,
    }

    def __init__(self) -> None:
        self._queue: List[PrioritizedEvent] = []
        self._sequence: int = 0
        self._lock = threading.Lock()
        self.logger = logging.getLogger(self.__class__.__name__)

    def enqueue(self, event: Event) -> None:
        """Add an event to the priority queue.

        Args:
            event: The event to enqueue
        """
        priority_idx = self.PRIORITY_ORDER.get(
            event.metadata.priority, self.PRIORITY_ORDER[EventPriority.NORMAL]
        )
        with self._lock:
            self._sequence += 1
            pe = PrioritizedEvent(
                priority_index=priority_idx,
                created_at=event.metadata.timestamp.timestamp(),
                sequence=self._sequence,
                event=event,
            )
            heapq.heappush(self._queue, pe)
            self.logger.debug(
                f"Enqueued {event.metadata.event_type.value} "
                f"at priority {event.metadata.priority.value} "
                f"(idx={priority_idx})"
            )

    def dequeue(self) -> Optional[Event]:
        """Get the highest-priority event from the queue.

        Returns:
            The next event to process, or None if queue is empty
        """
        with self._lock:
            if not self._queue:
                return None
            pe = heapq.heappop(self._queue)
            return pe.event

    def peek(self) -> Optional[Event]:
        """Look at the highest-priority event without removing it.

        Returns:
            The next event to process, or None if queue is empty
        """
        with self._lock:
            if not self._queue:
                return None
            return self._queue[0].event

    def size(self) -> int:
        """Return the number of events in the queue."""
        with self._lock:
            return len(self._queue)

    def clear(self) -> None:
        """Clear all events from the queue."""
        with self._lock:
            self._queue.clear()
            self._sequence = 0

    def is_empty(self) -> bool:
        """Check if the queue is empty."""
        return self.size() == 0
