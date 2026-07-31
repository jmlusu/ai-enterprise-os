"""Event Bus & Messaging Platform for AI Enterprise OS.

Provides enterprise-grade event-driven communication between all subsystems:
Registry, Bootstrap, Generator, Decision, Workflow, and Memory engines.

Supports publish/subscribe, broadcast, request/reply, event persistence,
replay, dead letter queues, priority processing, filtering, routing, and
middleware pipelines.
"""

from __future__ import annotations

from .bus import EventBus
from .config import EventRegistryConfig, load_event_pipeline_config, load_event_registry
from .dead_letter import DeadLetterQueue, DeadLetterRecord
from .dispatcher import Dispatcher
from .exceptions import (
    DeadLetterError,
    EventBusError,
    EventPersistenceError,
    EventPublishError,
    EventReplayError,
    EventSubscribeError,
    EventTimeoutError,
    EventValidationError,
)
from .filters import (
    AndFilter,
    EventFilter,
    FilterChain,
    NotFilter,
    OrFilter,
    PayloadFilter,
    PriorityFilter,
    SourceFilter,
    TagFilter,
    TypeFilter,
)
from .history import EventHistory, HistoryEntry
from .metrics import EventMetrics
from .middleware import (
    LoggingMiddleware,
    MetricsMiddleware,
    Middleware,
    MiddlewarePipeline,
    RetryMiddleware,
    ValidationMiddleware,
)
from .models import (
    DeliveryResult,
    Event,
    EventEnvelope,
    EventMetadata,
    EventPriority,
    EventStatus,
    EventType,
    ReplayRequest,
    SubscriberInfo,
)
from .persistence import EventPersistence
from .priorities import PrioritizedEvent, PriorityProcessor
from .publisher import Publisher
from .registry import EventTypeRegistry
from .replay import ReplayEngine, ReplaySession
from .router import Route, Router
from .subscriber import Subscriber

__all__ = [
    "AndFilter",
    "EventRegistryConfig",
    "DeadLetterError",
    "DeadLetterQueue",
    "DeadLetterRecord",
    "DeliveryResult",
    "Dispatcher",
    "Event",
    "EventBus",
    "EventBusError",
    "EventEnvelope",
    "EventFilter",
    "EventHistory",
    "EventMetadata",
    "EventMetrics",
    "EventPersistence",
    "EventPersistenceError",
    "EventPriority",
    "EventPublishError",
    "EventReplayError",
    "EventStatus",
    "EventSubscribeError",
    "EventTimeoutError",
    "EventType",
    "EventTypeRegistry",
    "EventValidationError",
    "FilterChain",
    "HistoryEntry",
    "load_event_pipeline_config",
    "load_event_registry",
    "LoggingMiddleware",
    "MetricsMiddleware",
    "Middleware",
    "MiddlewarePipeline",
    "NotFilter",
    "OrFilter",
    "PayloadFilter",
    "PriorityFilter",
    "PriorityProcessor",
    "PrioritizedEvent",
    "Publisher",
    "ReplayEngine",
    "ReplayRequest",
    "ReplaySession",
    "RetryMiddleware",
    "Route",
    "Router",
    "SourceFilter",
    "Subscriber",
    "SubscriberInfo",
    "TagFilter",
    "TypeFilter",
    "ValidationMiddleware",
]
