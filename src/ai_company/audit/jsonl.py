"""JSONL append-only audit store for AI Enterprise OS Audit Engine."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ai_company.audit.events import AuditEvent


class JsonlAuditStore:
    """Append-only JSONL store for audit events.

    Each event is written as a single JSON line, enabling efficient
    append operations and easy log rotation.
    """

    def __init__(self, log_path: str | Path | None = None) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self._events: list[AuditEvent] = []
        self._log_path = Path(log_path) if log_path else None

        if self._log_path:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: AuditEvent) -> None:
        """Append an event to the store."""
        self._events.append(event)

        if self._log_path:
            try:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event.to_dict()) + "\n")
            except Exception as e:
                self.logger.error(
                    f"Failed to write audit event to {self._log_path}: {e}"
                )

    def append_dict(self, event_dict: dict[str, Any]) -> None:
        """Append a dictionary as an event."""
        event = AuditEvent(
            event_type=event_dict.get("event_type", "unknown"),
            engine=event_dict.get("engine", ""),
            module=event_dict.get("module", ""),
            action=event_dict.get("action", ""),
            user=event_dict.get("user", ""),
            result=event_dict.get("result", "success"),
            duration=event_dict.get("duration"),
            decision=event_dict.get("decision"),
            files_created=event_dict.get("files_created", []),
            files_modified=event_dict.get("files_modified", []),
            error=event_dict.get("error"),
            metadata=event_dict.get("metadata", {}),
            session_id=event_dict.get("session_id"),
        )
        self.append(event)

    def read_all(self) -> list[dict[str, Any]]:
        """Read all events from the store."""
        return [e.to_dict() for e in self._events]

    def query(
        self,
        engine: str | None = None,
        event_type: str | None = None,
        result: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query events with filters."""
        results = self._events

        if engine:
            results = [e for e in results if e.engine == engine]
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if result:
            results = [e for e in results if e.result == result]

        return [e.to_dict() for e in results[-limit:]]

    def count(self) -> int:
        return len(self._events)

    def clear(self) -> None:
        self._events.clear()
        if self._log_path and self._log_path.exists():
            self._log_path.unlink()

    def rotate(self, archive_path: str | Path) -> int:
        """Rotate the audit log by archiving current events."""
        count = len(self._events)
        if count > 0:
            archive = Path(archive_path)
            archive.parent.mkdir(parents=True, exist_ok=True)
            with open(archive, "w", encoding="utf-8") as f:
                f.writelines(
                    json.dumps(event.to_dict()) + "\n" for event in self._events
                )
            self._events.clear()
            if self._log_path:
                self._log_path.unlink(missing_ok=True)
        return count
