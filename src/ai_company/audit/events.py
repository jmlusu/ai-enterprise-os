"""Audit events for AI Enterprise OS Audit Engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any


class AuditEvent:
    """A single structured audit event.

    Every action records:
    {
      "timestamp": "...",
      "user": "...",
      "engine": "...",
      "module": "...",
      "action": "...",
      "duration": "...",
      "result": "...",
      "decision": "...",
      "files_created": [],
      "files_modified": []
    }
    """

    def __init__(
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
        self.timestamp = datetime.now().isoformat()
        self.event_type = event_type
        self.engine = engine
        self.module = module
        self.action = action
        self.user = user
        self.result = result
        self.duration = duration
        self.decision = decision
        self.files_created = files_created or []
        self.files_modified = files_modified or []
        self.error = error
        self.metadata = metadata or {}
        self.session_id = session_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "engine": self.engine,
            "module": self.module,
            "action": self.action,
            "user": self.user,
            "result": self.result,
            "duration": self.duration,
            "decision": self.decision,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "error": self.error,
            "metadata": self.metadata,
            "session_id": self.session_id,
        }


class EventBuilder:
    """Builder for constructing audit events."""

    def __init__(self) -> None:
        self._event_type: str = ""
        self._engine: str = ""
        self._module: str = ""
        self._action: str = ""
        self._user: str = ""
        self._result: str = "success"
        self._duration: float | None = None
        self._decision: str | None = None
        self._files_created: list[str] = []
        self._files_modified: list[str] = []
        self._error: str | None = None
        self._metadata: dict[str, Any] = {}
        self._session_id: str | None = None

    def event_type(self, event_type: str) -> EventBuilder:
        self._event_type = event_type
        return self

    def engine(self, engine: str) -> EventBuilder:
        self._engine = engine
        return self

    def module(self, module: str) -> EventBuilder:
        self._module = module
        return self

    def action(self, action: str) -> EventBuilder:
        self._action = action
        return self

    def user(self, user: str) -> EventBuilder:
        self._user = user
        return self

    def result(self, result: str) -> EventBuilder:
        self._result = result
        return self

    def duration(self, duration: float) -> EventBuilder:
        self._duration = duration
        return self

    def decision(self, decision: str) -> EventBuilder:
        self._decision = decision
        return self

    def file_created(self, path: str) -> EventBuilder:
        self._files_created.append(path)
        return self

    def file_modified(self, path: str) -> EventBuilder:
        self._files_modified.append(path)
        return self

    def error(self, error: str) -> EventBuilder:
        self._error = error
        return self

    def metadata(self, key: str, value: Any) -> EventBuilder:
        self._metadata[key] = value
        return self

    def session_id(self, session_id: str) -> EventBuilder:
        self._session_id = session_id
        return self

    def build(self) -> AuditEvent:
        return AuditEvent(
            event_type=self._event_type,
            engine=self._engine,
            module=self._module,
            action=self._action,
            user=self._user,
            result=self._result,
            duration=self._duration,
            decision=self._decision,
            files_created=self._files_created,
            files_modified=self._files_modified,
            error=self._error,
            metadata=self._metadata,
            session_id=self._session_id,
        )
