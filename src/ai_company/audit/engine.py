"""Audit engine for AI Enterprise OS.

Coordinates audit logging, session tracking, metrics collection,
and file change tracking for the entire platform.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ai_company.audit.events import AuditEvent, EventBuilder
from ai_company.audit.jsonl import JsonlAuditStore
from ai_company.audit.logger import AuditLogger
from ai_company.audit.metrics import MetricsCollector
from ai_company.audit.session import SessionTracker


class AuditEngine:
    """Core audit engine for tracking all platform operations.

    Coordinates:
    1. JSONL append-only audit logging
    2. Structured event creation and storage
    3. Session tracking
    4. Timing and performance metrics
    5. File change tracking
    6. Query and analysis of audit data

    Args:
        store: JSONL audit store for persistence
        logger: Audit logger for recording events
        metrics: Metrics collector for performance data
        session_tracker: Session tracker for grouping events
        log_path: Optional path for JSONL log file
    """

    def __init__(
        self,
        store: JsonlAuditStore | None = None,
        logger: AuditLogger | None = None,
        metrics: MetricsCollector | None = None,
        session_tracker: SessionTracker | None = None,
        log_path: str | Path | None = None,
    ) -> None:
        self.store = store or JsonlAuditStore(log_path=log_path)
        self.logger = logger or AuditLogger(self.store)
        self.metrics = metrics or MetricsCollector()
        self.session_tracker = session_tracker or SessionTracker()
        self._log = logging.getLogger(self.__class__.__name__)

    def record(
        self,
        event_type: str,
        engine: str = "",
        module: str = "",
        action: str = "",
        user: str = "system",
        result: str = "success",
        duration: float | None = None,
        decision: str | None = None,
        files_created: list[str] | None = None,
        files_modified: list[str] | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Record an audit event.

        Args:
            event_type: Type of event
            engine: Source engine name
            module: Source module name
            action: Action performed
            user: User who performed the action
            result: Result status (success/error/warning)
            duration: Operation duration in seconds
            decision: Decision ID if applicable
            files_created: List of created file paths
            files_modified: List of modified file paths
            error: Error message if failed
            metadata: Additional event metadata

        Returns:
            Created AuditEvent
        """
        session_id = self.session_tracker.get_current_session_id()

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
        self.metrics.record_event(event_type, result)

        if session_id:
            self.session_tracker.record_event(session_id)

        if duration is not None:
            self.metrics.set_gauge(f"last_{action}_duration", duration)

        return event

    def create_builder(self) -> EventBuilder:
        """Create an event builder for constructing complex events."""
        return EventBuilder()

    def start_session(
        self, name: str = "", metadata: dict[str, Any] | None = None
    ) -> str:
        """Start a new audit session."""
        session_id = self.session_tracker.start_session(name, metadata)
        self.record(
            "session_start",
            engine="audit",
            action="start_session",
            metadata={"session_id": session_id},
        )
        return session_id

    def end_session(self, session_id: str | None = None) -> bool:
        """End an audit session."""
        result = self.session_tracker.end_session(session_id)
        if result:
            self.record(
                "session_end",
                engine="audit",
                action="end_session",
                metadata={"session_id": session_id},
            )
        return result

    def query(
        self,
        engine: str | None = None,
        event_type: str | None = None,
        result: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query audit events."""
        return self.store.query(
            engine=engine, event_type=event_type, result=result, limit=limit
        )

    def get_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent audit events."""
        return self.store.query(limit=limit)

    def get_metrics(self) -> dict[str, Any]:
        """Get collected metrics."""
        return self.metrics.get_all_metrics()

    def get_sessions(self, status: str | None = None) -> list[dict[str, Any]]:
        """Get audit sessions."""
        return self.session_tracker.list_sessions(status)

    def clear(self) -> None:
        """Clear all audit data."""
        self.store.clear()
        self.metrics.reset()
