"""Event bus exception hierarchy."""


class EventBusError(Exception):
    """Base exception for all event bus errors."""


class EventPublishError(EventBusError):
    """Raised when event publishing fails."""


class EventSubscribeError(EventBusError):
    """Raised when subscription registration fails."""


class EventReplayError(EventBusError):
    """Raised when event replay fails."""


class DeadLetterError(EventBusError):
    """Raised when dead letter operations fail."""


class EventPersistenceError(EventBusError):
    """Raised when event persistence fails."""


class EventTimeoutError(EventBusError):
    """Raised when event delivery times out."""


class EventValidationError(EventBusError):
    """Raised when event validation fails."""
