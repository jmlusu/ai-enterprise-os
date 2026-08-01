"""Runtime facade — the shared, stable surface over the runtime engine.

ADR 0003: the CLI, the dashboard API, and OpenCode prompt execution are thin
adapters; business logic lives exactly once. This facade stabilizes the
:class:`RuntimeEngine` public API so every surface asks the same questions
("is the system healthy?", "what is the status?") through one well-tested
object instead of duplicating runtime wiring per surface.
"""

from __future__ import annotations

import logging
from typing import Any, Self

from ai_company.runtime import RuntimeEngine, create_runtime

logger = logging.getLogger(__name__)

__all__ = ["RuntimeFacade"]


class RuntimeFacade:
    """Thin, shared adapter over the enterprise runtime engine.

    The facade never owns business logic; it only normalizes the runtime's
    public surface and returns JSON-ready dictionaries. All methods are
    synchronous — the async API layer bridges them through a thread executor
    (ADR 0002) so runtime locks are never held on the event loop.
    """

    def __init__(
        self,
        config_dir: str = "config",
        runtime: RuntimeEngine | None = None,
    ) -> None:
        self._config_dir = config_dir
        self._runtime = (
            runtime if runtime is not None else create_runtime(config_dir=config_dir)
        )

    @property
    def runtime(self) -> RuntimeEngine:
        """The underlying runtime engine."""
        return self._runtime

    @property
    def config_dir(self) -> str:
        """Directory containing ``config/runtime/*.yaml``."""
        return self._config_dir

    @property
    def event_bus(self) -> Any | None:
        """The runtime's event bus (None until the runtime provides one)."""
        return getattr(self._runtime, "event_bus", None)

    @property
    def phase(self) -> str:
        """Current lifecycle phase (``running``, ``stopped``, ...)."""
        try:
            return self._runtime.status().phase.value
        except Exception:
            return "unknown"

    @property
    def is_running(self) -> bool:
        """Whether the runtime lifecycle phase is ``running``."""
        return self.phase == "running"

    def ensure_running(self) -> None:
        """Boot the runtime if it is not already running."""
        if not self.is_running:
            self._runtime.start()

    def status(self) -> dict[str, Any]:
        """Runtime status view (phase, engines, processes, active counts)."""
        return self._runtime.status().model_dump(mode="json")

    def health(self) -> list[dict[str, Any]]:
        """Health probe results for every engine plus the system check."""
        return [check.model_dump(mode="json") for check in self._runtime.health()]

    def health_summary(self) -> dict[str, Any]:
        """Aggregated healthy/degraded/unhealthy counts."""
        return self._runtime.health_summary()

    def metrics(self) -> dict[str, Any]:
        """Runtime metrics snapshot (gauges, counters, timers)."""
        return self._runtime.metrics().model_dump(mode="json")

    def engine_states(self) -> list[dict[str, Any]]:
        """Lifecycle + health state of every registered engine."""
        return [
            state.model_dump(mode="json") for state in self._runtime.engine_states()
        ]

    def close(self) -> None:
        """Best-effort graceful shutdown of the runtime (idempotent)."""
        try:
            status = self._runtime.status()
            if status.phase.value not in ("stopped", "failed"):
                self._runtime.stop(reason="server-shutdown")
        except Exception as exc:  # never mask the caller's shutdown path
            logger.debug("Runtime facade close skipped: %s", exc)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
