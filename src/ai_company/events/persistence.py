"""Event persistence for the Event Bus.

Persists events to JSONL files for durability, replay, and audit.
Supports append-only writes with configurable rotation and retention.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_company.events.models import Event, EventEnvelope, EventType

logger = logging.getLogger(__name__)


class EventPersistence:
    """Persists events to JSONL storage.

    Events are stored as newline-delimited JSON records for
    append-only, replayable, and auditable history.

    Attributes:
        storage_path: Path to the JSONL event store file
        max_file_size_bytes: Rotate file when it exceeds this size
    """

    def __init__(
        self,
        storage_path: str | Path = "events/store.jsonl",
        max_file_size_bytes: int = 100 * 1024 * 1024,  # 100 MB
        auto_flush: bool = True,
    ) -> None:
        self.storage_path = Path(storage_path)
        self.max_file_size_bytes = max_file_size_bytes
        self.auto_flush = auto_flush
        self._file: Any | None = None
        self._current_size: int = 0
        self.logger = logging.getLogger(self.__class__.__name__)

        # Ensure directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing size
        if self.storage_path.exists():
            self._current_size = self.storage_path.stat().st_size

    def persist(self, event: Event) -> None:
        """Persist an event to the store.

        Args:
            event: The event to persist

        Raises:
            IOError: If writing fails
        """
        record = self._event_to_record(event)
        self._write_record(record)
        self.logger.debug(
            f"Persisted event: {event.metadata.event_type.value} "
            f"[{event.metadata.event_id}]"
        )

    def persist_envelope(self, envelope: EventEnvelope) -> None:
        """Persist an event envelope (with delivery tracking)."""
        record = envelope.model_dump(mode="json")
        record["_type"] = "envelope"
        self._write_record(record)

    def load_events(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        event_types: list[EventType] | None = None,
        source_filter: str | None = None,
        limit: int = 1000,
    ) -> list[Event]:
        """Load events from the store with optional filters.

        Args:
            since: Only events after this timestamp
            until: Only events before this timestamp
            event_types: Only events of these types
            source_filter: Only events from this source
            limit: Maximum number of events to return

        Returns:
            List of matching events
        """
        if not self.storage_path.exists():
            return []

        events: list[Event] = []
        type_strs = {et.value for et in (event_types or [])}

        with open(self.storage_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Skip envelopes
                if data.get("_type") == "envelope":
                    continue

                event = self._record_to_event(data)
                if not event:
                    continue

                # Apply filters
                if since and event.metadata.timestamp < since:
                    continue
                if until and event.metadata.timestamp > until:
                    continue
                if type_strs and event.metadata.event_type.value not in type_strs:
                    continue
                if source_filter and event.metadata.source != source_filter:
                    continue

                events.append(event)
                if len(events) >= limit:
                    break

        return events

    def count_events(self) -> int:
        """Count the total number of events in the store."""
        if not self.storage_path.exists():
            return 0

        count = 0
        with open(self.storage_path, "r") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count

    def rotate(self) -> Path:
        """Rotate the event store file.

        Creates a timestamped archive of the current file and starts a new one.

        Returns:
            Path to the archived file
        """
        if not self.storage_path.exists():
            raise FileNotFoundError(f"No event store to rotate: {self.storage_path}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = self.storage_path.with_name(
            f"{self.storage_path.stem}_{timestamp}{self.storage_path.suffix}"
        )

        self.close()
        os.rename(self.storage_path, archive_path)
        self._current_size = 0
        self.logger.info(f"Rotated event store to: {archive_path}")
        return archive_path

    def close(self) -> None:
        """Close the persistence file handle."""
        if self._file:
            self._file.close()
            self._file = None

    def _event_to_record(self, event: Event) -> dict[str, Any]:
        """Convert event to storage record dict."""
        record = event.model_dump(mode="json")
        record["_type"] = "event"
        return record

    def _record_to_event(self, data: dict[str, Any]) -> Event | None:
        """Convert storage record dict to Event."""
        try:
            # Records carry a "_type" discriminator; Event (pydantic strict)
            # rejects unknown fields, so strip it before deserialization.
            record = dict(data)
            record.pop("_type", None)
            return Event(**record)
        except Exception as e:
            self.logger.warning(f"Failed to deserialize event record: {e}")
            return None

    def _write_record(self, record: dict[str, Any]) -> None:
        """Write a single JSON record to the store."""
        line = json.dumps(record, default=str) + "\n"

        # Rotate if needed
        if self._current_size + len(line.encode("utf-8")) > self.max_file_size_bytes:
            self.rotate()

        # Append to file
        with open(self.storage_path, "a") as f:
            f.write(line)
            if self.auto_flush:
                f.flush()

        self._current_size += len(line.encode("utf-8"))
