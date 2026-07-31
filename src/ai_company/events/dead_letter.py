"""Dead Letter Queue for the Event Bus.

Captures events that failed delivery after exhausting all retries.
Provides storage, inspection, re-queuing, and automatic cleanup
of undeliverable messages.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ai_company.events.models import Event, EventEnvelope

logger = logging.getLogger(__name__)


@dataclass
class DeadLetterRecord:
    """Record of a failed event in the dead letter queue.

    Attributes:
        event: The original event that failed
        subscriber_name: The subscriber that failed
        error: Error message from the failure
        failed_at: When the failure occurred
        retry_count: Number of retry attempts made
        last_envelope: The last delivery envelope, if available
    """

    event: Event
    subscriber_name: str
    error: str
    failed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    retry_count: int = 3
    last_envelope: EventEnvelope | None = None


class DeadLetterQueue:
    """Stores and manages events that failed delivery.

    Features:
    - Persistent storage of dead letter records (JSONL)
    - Re-queuing dead letter events back to the event bus
    - Configurable TTL for automatic cleanup
    - Inspection and management of dead letter records
    """

    def __init__(
        self,
        storage_path: str | Path = "events/dead_letter.jsonl",
        max_records: int = 10000,
        ttl_days: int = 30,
    ) -> None:
        self.storage_path = Path(storage_path)
        self.max_records = max_records
        self.ttl_days = ttl_days
        self._records: list[DeadLetterRecord] = []
        self.logger = logging.getLogger(self.__class__.__name__)

        # Ensure directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing records
        self._load()

    def add(
        self,
        event: Event,
        subscriber_name: str,
        error: str,
        retry_count: int = 3,
        envelope: EventEnvelope | None = None,
    ) -> DeadLetterRecord:
        """Add a failed event to the dead letter queue.

        Args:
            event: The failed event
            subscriber_name: The subscriber that failed
            error: Error description
            retry_count: Number of retries attempted
            envelope: Last delivery envelope

        Returns:
            The dead letter record
        """
        record = DeadLetterRecord(
            event=event,
            subscriber_name=subscriber_name,
            error=error,
            retry_count=retry_count,
            last_envelope=envelope,
        )
        self._records.append(record)

        # Persist and manage size
        self._append_record(record)
        self._enforce_max()

        self.logger.warning(
            f"Dead letter: {event.metadata.event_type.value} "
            f"[{event.metadata.event_id}] -> {subscriber_name}: {error}"
        )
        return record

    def peek(self, limit: int = 10) -> list[DeadLetterRecord]:
        """View dead letter records without removing them.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of dead letter records
        """
        return self._records[:limit]

    def pop(self, count: int = 1) -> list[DeadLetterRecord]:
        """Remove and return dead letter records for re-queuing.

        Args:
            count: Number of records to pop (oldest first)

        Returns:
            List of removed dead letter records
        """
        records = self._records[:count]
        self._records = self._records[count:]
        self._save_all()
        return records

    def remove(self, event_id: str) -> bool:
        """Remove a specific dead letter record by event ID.

        Args:
            event_id: Event ID to remove

        Returns:
            True if record was found and removed
        """
        for i, record in enumerate(self._records):
            if record.event.metadata.event_id == event_id:
                self._records.pop(i)
                self._save_all()
                return True
        return False

    def count(self) -> int:
        """Return the number of dead letter records."""
        return len(self._records)

    def requeue_events(self, count: int = 1) -> list[Event]:
        """Get events ready for re-queuing onto the bus.

        Args:
            count: Number of events to requeue

        Returns:
            List of events to be republished
        """
        return [r.event for r in self.pop(count)]

    def cleanup(self) -> int:
        """Remove expired dead letter records.

        Returns:
            Number of records cleaned up
        """
        cutoff = datetime.now(UTC) - timedelta(days=self.ttl_days)
        before = len(self._records)
        self._records = [r for r in self._records if r.failed_at > cutoff]
        removed = before - len(self._records)
        if removed:
            self._save_all()
            self.logger.info(f"Cleaned up {removed} expired dead letter records")
        return removed

    def clear(self) -> None:
        """Clear all dead letter records."""
        self._records.clear()
        if self.storage_path.exists():
            os.remove(self.storage_path)
        self.logger.info("Cleared all dead letter records")

    def _load(self) -> None:
        """Load dead letter records from storage."""
        if not self.storage_path.exists():
            return
        with open(self.storage_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    event = Event(**data["event"])
                    record = DeadLetterRecord(
                        event=event,
                        subscriber_name=data["subscriber_name"],
                        error=data["error"],
                        failed_at=datetime.fromisoformat(data["failed_at"]),
                        retry_count=data["retry_count"],
                    )
                    self._records.append(record)
                except Exception as e:
                    self.logger.warning(f"Failed to load dead letter record: {e}")

    def _append_record(self, record: DeadLetterRecord) -> None:
        """Append a record to the persistent store."""
        data = {
            "event": record.event.model_dump(mode="json"),
            "subscriber_name": record.subscriber_name,
            "error": record.error,
            "failed_at": record.failed_at.isoformat(),
            "retry_count": record.retry_count,
        }
        with open(self.storage_path, "a") as f:
            f.write(json.dumps(data, default=str) + "\n")

    def _save_all(self) -> None:
        """Rewrite the entire dead letter store."""
        with open(self.storage_path, "w") as f:
            for record in self._records:
                data = {
                    "event": record.event.model_dump(mode="json"),
                    "subscriber_name": record.subscriber_name,
                    "error": record.error,
                    "failed_at": record.failed_at.isoformat(),
                    "retry_count": record.retry_count,
                }
                f.write(json.dumps(data, default=str) + "\n")

    def _enforce_max(self) -> None:
        """Enforce maximum records limit."""
        while len(self._records) > self.max_records:
            removed = self._records.pop(0)
            self.logger.warning(
                f"Dropped oldest dead letter record: "
                f"{removed.event.metadata.event_id} from {removed.failed_at}"
            )
