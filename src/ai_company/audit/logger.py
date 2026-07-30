"""Audit logger for AI Enterprise OS Audit Engine."""

from __future__ import annotations

import logging
from typing import Any

from ai_company.audit.events import AuditEvent
from ai_company.audit.jsonl import JsonlAuditStore


class AuditLogger:
    """Logger that records audit events to the audit store."""

    def __init__(self, store: JsonlAuditStore) -> None:
        self.store = store
        self.logger = logging.getLogger(self.__class__.__name__)

    def info(self, event: AuditEvent) -> None:
        """Log an informational audit event."""
        self.store.append(event)

    def warn(self, event: AuditEvent) -> None:
        """Log a warning audit event."""
        event.result = "warning"
        self.store.append(event)

    def error(self, event: AuditEvent) -> None:
        """Log an error audit event."""
        event.result = "error"
        self.store.append(event)

    def log(
        self,
        event_type: str,
        engine: str = "",
        module: str = "",
        action: str = "",
        user: str = "",
        result: str = "success",
        duration: float | None = None,
        decision: str | None = None,
        files_created: list[str] | None = None,
        files_modified: list[str] | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> None:
        """Create and log an audit event."""
        event = AuditEvent(
            event_type=event_type,
            engine=engine,
            module=module,
            action=action,
            user=user,
            result=result,
            duration=duration,
            decision=decision,
            files_created=files_created or [],
            files_modified=files_modified or [],
            error=error,
            metadata=metadata or {},
            session_id=session_id,
        )
        self.store.append(event)
