"""Runtime lifecycle state machine.

The runtime moves through :class:`RuntimePhase` states:

    STOPPED -> STARTING -> RUNNING -> DEGRADED -> RECOVERING -> RUNNING
                            |                                  |
                            +------------------ STOPPING ----+
                            (and FAILED on unrecoverable errors)

Transitions are validated by :class:`RuntimeLifecycle`; illegal transitions
raise :class:`InvalidRuntimeTransitionError`.
"""

from __future__ import annotations

import logging
from typing import Any

from ai_company.runtime.models import (
    InvalidRuntimeTransitionError,
    RuntimePhase,
)

logger = logging.getLogger(__name__)

# Allowed phase transitions.
RUNTIME_TRANSITIONS: dict[RuntimePhase, set[RuntimePhase]] = {
    RuntimePhase.STOPPED: {RuntimePhase.STARTING},
    RuntimePhase.STARTING: {
        RuntimePhase.RUNNING,
        RuntimePhase.FAILED,
        RuntimePhase.STOPPING,
    },
    RuntimePhase.RUNNING: {
        RuntimePhase.DEGRADED,
        RuntimePhase.RECOVERING,
        RuntimePhase.STOPPING,
        RuntimePhase.FAILED,
    },
    RuntimePhase.DEGRADED: {
        RuntimePhase.RUNNING,
        RuntimePhase.RECOVERING,
        RuntimePhase.STOPPING,
        RuntimePhase.FAILED,
    },
    RuntimePhase.RECOVERING: {
        RuntimePhase.RUNNING,
        RuntimePhase.DEGRADED,
        RuntimePhase.STOPPING,
    },
    RuntimePhase.STOPPING: {RuntimePhase.STOPPED, RuntimePhase.FAILED},
    RuntimePhase.FAILED: {RuntimePhase.STARTING, RuntimePhase.STOPPED},
}


class RuntimeLifecycle:
    """State machine for the runtime phase.

    Args:
        initial: Initial phase (defaults to STOPPED).
    """

    def __init__(self, initial: RuntimePhase = RuntimePhase.STOPPED) -> None:
        self._phase = initial

    @property
    def phase(self) -> RuntimePhase:
        """Current runtime phase."""
        return self._phase

    def can_transition(self, new_phase: RuntimePhase) -> bool:
        """Return whether moving to ``new_phase`` is allowed."""
        return new_phase in RUNTIME_TRANSITIONS.get(self._phase, set())

    def transition(self, new_phase: RuntimePhase) -> RuntimePhase:
        """Transition to ``new_phase``, validating the move.

        Returns:
            The new phase.

        Raises:
            InvalidRuntimeTransitionError: If the transition is illegal.
        """
        if new_phase == self._phase:
            return self._phase
        if not self.can_transition(new_phase):
            raise InvalidRuntimeTransitionError(
                f"Invalid runtime transition: {self._phase.value} -> {new_phase.value}"
            )
        logger.info("Runtime phase: %s -> %s", self._phase.value, new_phase.value)
        self._phase = new_phase
        return self._phase

    def force(self, new_phase: RuntimePhase) -> RuntimePhase:
        """Set the phase without validation (used for persisted-state recovery)."""
        logger.warning(
            "Runtime phase forced: %s -> %s", self._phase.value, new_phase.value
        )
        self._phase = new_phase
        return self._phase

    def is_active(self) -> bool:
        """Return whether the runtime is in a live phase."""
        return self._phase in {
            RuntimePhase.STARTING,
            RuntimePhase.RUNNING,
            RuntimePhase.DEGRADED,
            RuntimePhase.RECOVERING,
            RuntimePhase.STOPPING,
        }

    def snapshot(self) -> dict[str, Any]:
        """Return a compact snapshot for diagnostics."""
        return {"phase": self._phase.value}
