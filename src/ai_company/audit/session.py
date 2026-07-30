"""Session tracking for AI Enterprise OS Audit Engine."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any


class SessionTracker:
    """Tracks audit sessions for grouping related events."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._current_session_id: str | None = None
        self.logger = logging.getLogger(self.__class__.__name__)

    def start_session(
        self, session_name: str = "", metadata: dict[str, Any] | None = None
    ) -> str:
        """Start a new session and return session ID."""
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            "id": session_id,
            "name": session_name or f"session_{session_id[:8]}",
            "started_at": datetime.now().isoformat(),
            "ended_at": None,
            "event_count": 0,
            "status": "active",
            "metadata": metadata or {},
        }
        self._current_session_id = session_id
        self.logger.info(f"Session started: {session_id}")
        return session_id

    def end_session(self, session_id: str | None = None) -> bool:
        """End a session."""
        sid = session_id or self._current_session_id
        if sid and sid in self._sessions:
            self._sessions[sid]["ended_at"] = datetime.now().isoformat()
            self._sessions[sid]["status"] = "completed"
            if self._current_session_id == sid:
                self._current_session_id = None
            self.logger.info(f"Session ended: {sid}")
            return True
        return False

    def record_event(self, session_id: str) -> None:
        """Record an event in a session."""
        if session_id in self._sessions:
            self._sessions[session_id]["event_count"] += 1

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session information."""
        return self._sessions.get(session_id)

    def get_current_session(self) -> dict[str, Any] | None:
        """Get current active session."""
        if self._current_session_id:
            return self._sessions.get(self._current_session_id)
        return None

    def list_sessions(self, status: str | None = None) -> list[dict[str, Any]]:
        """List all sessions."""
        sessions = list(self._sessions.values())
        if status:
            sessions = [s for s in sessions if s["status"] == status]
        return sorted(sessions, key=lambda s: s["started_at"], reverse=True)

    def get_current_session_id(self) -> str | None:
        return self._current_session_id
