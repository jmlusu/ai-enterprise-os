"""Event type registry — the catalog of all standardized enterprise events."""

from __future__ import annotations

import logging
from typing import Any

from ai_company.events.models import EventType

logger = logging.getLogger(__name__)


class EventTypeRegistry:
    """Registry of all standardized enterprise event types.

    Provides event type registration, validation, categorization,
    and metadata lookup.
    """

    # Domain categorization of event types
    DOMAIN_MAP: dict[str, str] = {
        "company": "Company Lifecycle",
        "department": "Department Lifecycle",
        "executive": "Executive Lifecycle",
        "workflow": "Workflow Engine",
        "decision": "Decision Engine",
        "memory": "Memory Engine",
        "project": "Project Management",
        "meeting": "Meeting Management",
        "agent": "Agent Lifecycle",
        "bootstrap": "Bootstrap Engine",
        "generation": "Generator Engine",
        "registry": "Registry Engine",
        "system": "System Events",
        "audit": "Audit Engine",
        "event": "Event Bus",
        "integration": "Integration Events",
        "pipeline": "Pipeline Orchestration",
        "task": "Task Execution",
    }

    def __init__(self) -> None:
        self._registered: dict[str, EventType] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register all standard EventType enum values."""
        for et in EventType:
            domain = et.value.split(".")[0]
            self._registered[et.value] = et
            self._metadata[et.value] = {
                "event_type": et.value,
                "domain": domain,
                "domain_label": self.DOMAIN_MAP.get(domain, "Unknown"),
                "description": self._generate_description(et),
            }

    def _generate_description(self, event_type: EventType) -> str:
        """Generate a human-readable description for an event type."""
        parts = event_type.value.split(".")
        domain = parts[0]
        action = parts[1] if len(parts) > 1 else "unknown"
        domain_label = self.DOMAIN_MAP.get(domain, domain)
        return f"{domain_label}: {action.replace('_', ' ').title()}"

    def register(
        self, event_type: str, metadata: dict[str, Any] | None = None
    ) -> EventType:
        """Register a custom event type.

        Args:
            event_type: Dot-notation event type string (e.g. 'custom.event')
            metadata: Optional metadata describing the event type

        Returns:
            The registered EventType or a dynamically created one

        Raises:
            ValueError: If event_type is invalid
        """
        if not event_type or "." not in event_type:
            raise ValueError(f"Invalid event type: {event_type!r}")

        # Check if it's a known EventType
        for et in EventType:
            if et.value == event_type:
                if metadata:
                    self._metadata[event_type].update(metadata)
                return et

        # Register custom type
        self._registered[event_type] = EventType(event_type)
        domain = event_type.split(".")[0]
        self._metadata[event_type] = metadata or {
            "event_type": event_type,
            "domain": domain,
            "domain_label": self.DOMAIN_MAP.get(domain, "Custom"),
            "description": f"Custom: {event_type}",
        }
        return self._registered[event_type]

    def get_metadata(self, event_type: str) -> dict[str, Any] | None:
        """Get metadata for an event type."""
        return self._metadata.get(event_type)

    def get_all_types(self) -> list[str]:
        """Get all registered event type strings."""
        return list(self._registered.keys())

    def get_types_by_domain(self, domain: str) -> list[str]:
        """Get all event types in a domain."""
        return [et for et in self._registered if et.startswith(f"{domain}.")]

    def get_domains(self) -> dict[str, list[str]]:
        """Get all domains and their event types."""
        domains: dict[str, list[str]] = {}
        for et in self._registered:
            domain = et.split(".")[0]
            if domain not in domains:
                domains[domain] = []
            domains[domain].append(et)
        return domains

    def validate(self, event_type: str) -> bool:
        """Validate that an event type string is registered."""
        return event_type in self._registered

    def is_builtin(self, event_type: str) -> bool:
        """Check if event type is a built-in Enum value."""
        try:
            EventType(event_type)
            return True
        except ValueError:
            return False

    def count(self) -> int:
        """Return the number of registered event types."""
        return len(self._registered)
