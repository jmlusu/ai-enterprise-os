"""Pydantic models for the Event Bus & Messaging Platform.

All models use Pydantic BaseModel for validation, serialization, and
schema generation. Supports YAML, JSON, and dict formats.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Return current UTC timestamp (timezone-aware)."""
    return datetime.now(UTC)


def _new_id(prefix: str = "evt") -> str:
    """Generate a unique event ID."""
    return f"{prefix}_{uuid4().hex[:16]}"


class EventPriority(str, Enum):
    """Event priority levels for processing order."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"

    def __lt__(self, other: str) -> bool:
        if not isinstance(other, EventPriority):
            return NotImplemented
        order = list(EventPriority)
        return order.index(self) < order.index(other)


class EventStatus(str, Enum):
    """Lifecycle status of an event."""

    PENDING = "pending"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"
    EXPIRED = "expired"
    REPLAYED = "replayed"


class EventType(str, Enum):
    """Standardized enterprise event type registry.

    Convention: <domain>.<action> where action is past-tense verb.
    """

    # Company lifecycle
    COMPANY_CREATED = "company.created"
    COMPANY_UPDATED = "company.updated"

    # Department lifecycle
    DEPARTMENT_CREATED = "department.created"
    DEPARTMENT_UPDATED = "department.updated"

    # Executive lifecycle
    EXECUTIVE_HIRED = "executive.hired"
    EXECUTIVE_UPDATED = "executive.updated"

    # Workflow lifecycle
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_CANCELLED = "workflow.cancelled"

    # Decision lifecycle
    DECISION_REQUESTED = "decision.requested"
    DECISION_APPROVED = "decision.approved"
    DECISION_REJECTED = "decision.rejected"
    DECISION_ESCALATED = "decision.escalated"
    DECISION_DEFERRED = "decision.deferred"

    # Memory lifecycle
    MEMORY_SAVED = "memory.saved"
    MEMORY_UPDATED = "memory.updated"
    MEMORY_ARCHIVED = "memory.archived"
    MEMORY_RESTORED = "memory.restored"

    # Project lifecycle
    PROJECT_STARTED = "project.started"
    PROJECT_COMPLETED = "project.completed"
    PROJECT_MILESTONE = "project.milestone"

    # Meeting lifecycle
    MEETING_SCHEDULED = "meeting.scheduled"
    MEETING_COMPLETED = "meeting.completed"

    # Agent lifecycle
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"

    # Bootstrap lifecycle
    BOOTSTRAP_STARTED = "bootstrap.started"
    BOOTSTRAP_FINISHED = "bootstrap.finished"

    # Generator lifecycle
    GENERATION_STARTED = "generation.started"
    GENERATION_FINISHED = "generation.finished"
    GENERATION_FAILED = "generation.failed"

    # Registry lifecycle
    REGISTRY_LOADED = "registry.loaded"
    REGISTRY_RELOADED = "registry.reloaded"

    # System lifecycle
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
    SYSTEM_HEALTH_CHECK = "system.health_check"

    # Audit lifecycle
    AUDIT_RECORDED = "audit.recorded"
    AUDIT_WRITE = "audit.write"
    AUDIT_WRITE_REJECTED = "audit.write_rejected"

    # Event bus lifecycle
    EVENT_PUBLISHED = "event.published"
    EVENT_REPLAYED = "event.replayed"
    EVENT_DLQ = "event.dead_letter"

    # Integration
    INTEGRATION_TRIGGERED = "integration.triggered"
    INTEGRATION_COMPLETED = "integration.completed"
    INTEGRATION_FAILED = "integration.failed"

    # Pipeline lifecycle (Enterprise Orchestration Engine)
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"
    PIPELINE_CANCELLED = "pipeline.cancelled"
    PIPELINE_RECOVERED = "pipeline.recovered"

    # Task lifecycle (Enterprise Orchestration Engine)
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_SKIPPED = "task.skipped"


class EventMetadata(BaseModel):
    """Metadata attached to every event."""

    event_id: str = Field(default_factory=lambda: _new_id("evt"))
    timestamp: datetime = Field(default_factory=_utcnow)
    event_type: EventType
    source: str = Field(default="", description="Component that emitted the event")
    version: str = Field(default="1.0")
    correlation_id: str | None = Field(default=None, description="Links related events")
    causation_id: str | None = Field(
        default=None, description="ID of event that caused this one"
    )
    tenant_id: str | None = Field(default=None, description="Multi-tenant support")
    user_id: str | None = Field(
        default=None, description="User who triggered the event"
    )
    priority: EventPriority = Field(default=EventPriority.NORMAL)
    status: EventStatus = Field(default=EventStatus.PENDING)
    ttl_seconds: int | None = Field(default=None, description="Time-to-live in seconds")
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=3, ge=0)
    tags: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class Event(BaseModel):
    """An event with metadata and payload."""

    metadata: EventMetadata
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Event data payload"
    )

    model_config = {"extra": "forbid"}


class EventEnvelope(BaseModel):
    """Full event envelope including delivery tracking."""

    event: Event
    routing_key: str = Field(default="", description="Routing key for the event")
    delivered_to: list[str] = Field(default_factory=list)
    failed_at: datetime | None = Field(None)
    error_message: str | None = Field(None)
    delivered_at: datetime | None = Field(None)
    processing_time_ms: float | None = Field(None)

    model_config = {"extra": "forbid"}


class DeliveryResult(BaseModel):
    """Result of delivering an event to a single subscriber."""

    event_id: str
    subscriber_name: str
    status: EventStatus = EventStatus.DELIVERED
    error: str = ""
    processing_time_ms: float = 0.0
    note: str = ""

    model_config = {"extra": "forbid"}


class SubscriberInfo(BaseModel):
    """Information about a registered subscriber."""

    subscriber_id: str = Field(default_factory=lambda: _new_id("sub"))
    name: str
    event_types: list[EventType]
    description: str = ""
    is_active: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
    max_retries: int = 3
    timeout_seconds: int = 30

    model_config = {"extra": "forbid"}


class ReplayRequest(BaseModel):
    """Request to replay historical events."""

    replay_id: str = Field(default_factory=lambda: _new_id("rpl"))
    session_id: str | None = Field(
        default=None, description="Session identifier for tracking"
    )
    since: datetime | None = Field(
        default=None, description="Replay events after this timestamp"
    )
    until: datetime | None = Field(
        default=None, description="Replay events before this timestamp"
    )
    event_types: list[EventType] = Field(
        default_factory=list, description="Filter by event types"
    )
    source_filter: str | None = Field(
        default=None, description="Filter by source component"
    )
    max_events: int = Field(default=1000, ge=1, le=100000)
    limit: int | None = Field(
        default=None, description="Max events to replay (overrides max_events)"
    )
    max_events_per_second: int | None = Field(
        default=None, description="Rate-limit for replay (events/second)"
    )
    target_subscribers: list[str] = Field(
        default_factory=list, description="Only deliver to these subscribers"
    )

    model_config = {"extra": "forbid"}
