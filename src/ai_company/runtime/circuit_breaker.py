"""Circuit breaker implementation for isolating engine dependencies.

Provides circuit breaker pattern for protecting runtime engines from cascading
failures. Circuit breakers open after successive failures and attempt to
reconnect after a timeout period.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ai_company.runtime.models import CircuitBreakerOpenError

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker for isolating engine dependencies."""

    def __init__(self, component_name: str, timeout_seconds: int = 60):
        self.component_name = component_name
        self.timeout_seconds = timeout_seconds
        self.failure_count = 0
        self.last_failure_time: datetime | None = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.success_threshold = 3

    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        if self.state == "OPEN":
            if self.can_reconnect():
                self.state = "HALF_OPEN"
            else:
                raise CircuitBreakerOpenError(f"Circuit {self.component_name} is open")

        try:
            result = func(*args, **kwargs)
            self.on_success()
            return result
        except Exception:
            self.on_failure()
            raise

    def on_success(self):
        if self.state == "HALF_OPEN":
            self.failure_count = 0
            self.state = "CLOSED"
        elif self.state == "CLOSED":
            self.failure_count = 0

    def on_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now(UTC)
        if self.failure_count >= self.success_threshold:
            self.state = "OPEN"

    def can_reconnect(self) -> bool:
        if self.state != "OPEN":
            return True
        if self.last_failure_time is None:
            return False
        return (
            datetime.now(UTC) - self.last_failure_time
        ).total_seconds() > self.timeout_seconds

    def get_state(self) -> dict[str, Any]:
        """Return circuit breaker state for monitoring."""
        return {
            "component_name": self.component_name,
            "state": self.state,
            "failure_count": self.failure_count,
            "timeout_seconds": self.timeout_seconds,
            "last_failure_time": self.last_failure_time,
            "success_threshold": self.success_threshold,
        }
