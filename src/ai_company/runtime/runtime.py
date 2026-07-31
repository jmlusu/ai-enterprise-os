"""Runtime entry points — engine factory and main loop.

``create_runtime`` builds a :class:`RuntimeEngine` wired to the real
subsystems; ``main_loop`` runs the runtime loop until the stop event
fires (used by ``ai-company runtime start``).
"""

from __future__ import annotations

import logging
from typing import Any

from ai_company.runtime.engine import RuntimeEngine

logger = logging.getLogger(__name__)

__all__ = ["RuntimeEngine", "create_runtime", "main_loop"]


def create_runtime(
    config_dir: str = "config",
    event_bus: Any | None = None,
    memory_engine: Any | None = None,
    **kwargs: Any,
) -> RuntimeEngine:
    """Create a RuntimeEngine wired to the configured subsystems.

    Args:
        config_dir: Directory containing ``config/runtime/*.yaml``.
        event_bus: Pre-built EventBus (a new one is created from the
            startup sequence when omitted).
        memory_engine: Pre-built MemoryEngine (created from the startup
            sequence when omitted).
        **kwargs: Forwarded to RuntimeEngine (``name``, ``version``).

    Returns:
        An unstarted RuntimeEngine (call ``.start()`` to boot it).
    """
    return RuntimeEngine(
        config_dir=config_dir,
        event_bus=event_bus,
        memory_engine=memory_engine,
        **kwargs,
    )


def main_loop(
    runtime: RuntimeEngine,
    stop_event: Any,
    interval_seconds: float | None = None,
) -> None:
    """Run the runtime main loop until ``stop_event`` is set.

    The loop keeps the runtime alive, periodically refreshes metrics,
    and checks for termination (Ctrl-C sets the stop event).

    Args:
        runtime: The running RuntimeEngine.
        stop_event: A ``threading.Event`` signalling shutdown.
        interval_seconds: Loop cadence (defaults to the configured
            ``loop_interval_seconds``).
    """
    interval = (
        interval_seconds
        if interval_seconds is not None
        else float(runtime.config.loop_interval_seconds)
    )
    logger.info("Runtime main loop started (interval=%ss)", interval)
    while not stop_event.is_set():
        try:
            runtime.metrics()
        except Exception as exc:
            logger.error("Metrics refresh failed in main loop: %s", exc)
        stop_event.wait(interval)
    logger.info("Runtime main loop stopped")
