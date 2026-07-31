"""Event Replay Engine for the Event Bus.

Allows replaying historical events for recovery, testing, and
reprocessing. Supports time-range filtering, event-type filtering,
speed control, and progress tracking.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Set

from ai_company.events.models import Event, ReplayRequest
from ai_company.events.persistence import EventPersistence

logger = logging.getLogger(__name__)

# Type alias for replay event handler
ReplayHandler = Callable[[Event], None]

# Type alias for progress callback
ProgressCallback = Callable[[int, int], None]  # current, total


@dataclass
class ReplaySession:
    """Tracks a single replay operation.

    Attributes:
        request: The original replay request
        state: Current replay state
        total_events: Total events to replay
        processed: Number of events processed
        succeeded: Number of successfully replayed events
        failed: Number of failed replayed events
        started_at: When replay started
        completed_at: When replay completed (None if still running)
    """

    request: ReplayRequest
    state: str = "pending"  # pending, running, completed, failed
    total_events: int = 0
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ReplayEngine:
    """Replays historical events from the event store.

    Supports:
    - Full replay of all events
    - Time-range filtered replay
    - Event-type filtered replay
    - Source-filtered replay
    - Rate-limited replay (events per second)
    - Progress tracking and cancellation
    - Multiple concurrent replay sessions
    """

    def __init__(
        self,
        persistence: EventPersistence,
        handler: Optional[ReplayHandler] = None,
    ) -> None:
        self.persistence = persistence
        self.handler = handler
        self._sessions: Dict[str, ReplaySession] = {}
        self._cancel_flags: Set[str] = set()
        self.logger = logging.getLogger(self.__class__.__name__)

    def replay(
        self,
        request: ReplayRequest,
        handler: Optional[ReplayHandler] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ReplaySession:
        """Execute a replay operation.

        Args:
            request: Replay configuration
            handler: Handler to invoke for each event (overrides default)
            progress_callback: Called with (processed, total) after each event

        Returns:
            ReplaySession tracking progress and results
        """
        session_id = request.session_id or f"replay_{int(time.time())}"
        session = ReplaySession(request=request, state="running")
        session.started_at = datetime.now(timezone.utc)
        self._sessions[session_id] = session

        handler_fn = handler or self.handler
        if not handler_fn:
            raise ValueError(
                "No replay handler provided. Provide a handler or set one "
                "on the ReplayEngine."
            )

        try:
            # Load events with filters
            events = self.persistence.load_events(
                since=request.since,
                until=request.until,
                event_types=request.event_types,
                source_filter=request.source_filter,
                limit=request.limit or 10000,
            )

            session.total_events = len(events)

            # Apply rate limiting if specified
            delay = 0.0
            if request.max_events_per_second and request.max_events_per_second > 0:
                delay = 1.0 / request.max_events_per_second

            # Process events
            for i, event in enumerate(events):
                # Check cancellation
                if session_id in self._cancel_flags:
                    session.state = "cancelled"
                    self._cancel_flags.discard(session_id)
                    break

                try:
                    handler_fn(event)
                    session.succeeded += 1
                except Exception as e:
                    session.failed += 1
                    self.logger.error(
                        f"Replay failed for event {event.metadata.event_id}: {e}"
                    )

                session.processed += 1
                if progress_callback:
                    progress_callback(session.processed, session.total_events)

                if delay > 0:
                    time.sleep(delay)

            session.state = "completed"
        except Exception as e:
            session.state = "failed"
            self.logger.error(f"Replay session {session_id} failed: {e}")
        finally:
            session.completed_at = datetime.now(timezone.utc)

        return session

    async def replay_async(
        self,
        request: ReplayRequest,
        handler: Optional[ReplayHandler] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ReplaySession:
        """Execute a replay operation asynchronously.

        Args:
            Same as replay()

        Returns:
            ReplaySession tracking progress
        """
        return await asyncio.get_event_loop().run_in_executor(
            None, self.replay, request, handler, progress_callback
        )

    def cancel(self, session_id: str) -> bool:
        """Cancel a running replay session.

        Args:
            session_id: Session to cancel

        Returns:
            True if cancellation was requested
        """
        if session_id in self._sessions:
            self._cancel_flags.add(session_id)
            return True
        return False

    def get_session(self, session_id: str) -> Optional[ReplaySession]:
        """Get replay session status."""
        return self._sessions.get(session_id)

    def get_sessions(self) -> Dict[str, ReplaySession]:
        """Get all replay sessions."""
        return dict(self._sessions)

    def get_stats(self) -> Dict[str, Any]:
        """Get replay engine statistics."""
        total = len(self._sessions)
        completed = sum(1 for s in self._sessions.values() if s.state == "completed")
        running = sum(1 for s in self._sessions.values() if s.state == "running")
        failed = sum(1 for s in self._sessions.values() if s.state == "failed")
        total_events = sum(s.total_events for s in self._sessions.values())
        total_succeeded = sum(s.succeeded for s in self._sessions.values())
        total_failed = sum(s.failed for s in self._sessions.values())

        return {
            "total_sessions": total,
            "completed": completed,
            "running": running,
            "failed": failed,
            "total_events": total_events,
            "total_succeeded": total_succeeded,
            "total_failed": total_failed,
        }
