"""Health checking for the orchestration engine.

The :class:`HealthChecker` probes each coordinated engine with a small
callable and produces :class:`HealthStatus` entries. The engine exposes
these through ``health()`` and aggregates them into
:class:`EngineStatus`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ai_company.orchestration.models import (
    EngineStatus,
    HealthStatus,
)

logger = logging.getLogger(__name__)

Probe = Callable[[], tuple[bool, str, dict[str, Any]]]


class HealthChecker:
    """Runs probes against engines and aggregates health status.

    Args:
        coordinator: Coordinator holding the engine instances.
        config: Monitoring/health config (optional).
    """

    def __init__(
        self,
        coordinator: Any | None = None,
        config: dict[str, Any] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.coordinator = coordinator
        self.config = config or {}
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._probes: dict[str, Probe] = {}
        self._register_default_probes()

    # ── Probe registry ────────────────────────────────────────────

    def register_probe(self, engine: str, probe: Probe) -> None:
        """Register a health probe for an engine."""
        self._probes[engine] = probe

    def unregister_probe(self, engine: str) -> bool:
        """Remove a health probe."""
        return self._probes.pop(engine, None) is not None

    # ── Checks ────────────────────────────────────────────────────

    def check(self, engine: str) -> HealthStatus:
        """Run a single engine's probe."""
        probe = self._probes.get(engine)
        if probe is None:
            return HealthStatus(
                engine=engine,
                healthy=False,
                message="No health probe registered",
            )
        try:
            healthy, message, details = probe()
            return HealthStatus(
                engine=engine,
                healthy=bool(healthy),
                message=message,
                details=details,
            )
        except Exception as exc:
            self.logger.warning("Health check failed for %s: %s", engine, exc)
            return HealthStatus(
                engine=engine,
                healthy=False,
                message=f"{type(exc).__name__}: {exc}",
            )

    def check_all(self) -> list[HealthStatus]:
        """Probe every registered engine."""
        statuses: list[HealthStatus] = []
        for engine in sorted(self._probes):
            statuses.append(self.check(engine))
        # Include registered-but-unprobed engines as unavailable.
        if self.coordinator is not None:
            probed = set(self._probes)
            for name in self.coordinator.list_engines():
                if name not in probed:
                    statuses.append(
                        HealthStatus(
                            engine=name,
                            healthy=False,
                            message="Engine registered without a health probe",
                        )
                    )
        return statuses

    def engine_status(
        self,
        name: str = "Enterprise Orchestration Engine",
        version: str = "1.0",
        running: bool = True,
        started_at: Any | None = None,
        metrics: Any | None = None,
        active_plans: int = 0,
    ) -> EngineStatus:
        """Build an EngineStatus view from current health + metrics."""
        return EngineStatus(
            name=name,
            version=version,
            running=running,
            started_at=started_at,
            health=self.check_all(),
            metrics=metrics or self.config.get("metrics"),
            active_plans=active_plans,
        )

    # ── Default probes ────────────────────────────────────────────

    def _register_default_probes(self) -> None:
        self.register_probe("registry", self._probe_registry)
        self.register_probe("memory", self._probe_memory)
        self.register_probe("event_bus", self._probe_event_bus)
        self.register_probe("generator", self._probe_presence("generator"))
        self.register_probe("validator", self._probe_presence("validator"))
        self.register_probe("workflow", self._probe_presence("workflow"))
        self.register_probe("decision", self._probe_presence("decision"))
        self.register_probe("audit", self._probe_presence("audit"))

    def _probe_registry(self) -> tuple[bool, str, dict[str, Any]]:
        if self.coordinator is None:
            return False, "coordinator not configured", {}
        engine = self.coordinator.engine("registry")
        if engine is None:
            return False, "registry engine not registered", {}
        last = getattr(engine, "last_result", None)
        if last is None:
            return False, "registry not loaded yet", {}
        return (
            bool(last.success),
            "registry loaded" if last.success else "registry load failed",
            {"errors": list(getattr(last, "errors", []))},
        )

    def _probe_memory(self) -> tuple[bool, str, dict[str, Any]]:
        if self.coordinator is None:
            return False, "coordinator not configured", {}
        engine = self.coordinator.engine("memory")
        if engine is None:
            return False, "memory engine not registered", {}
        stats = engine.get_statistics()
        return (
            True,
            "memory engine operational",
            {"entries": stats.get("total_memories", 0)},
        )

    def _probe_event_bus(self) -> tuple[bool, str, dict[str, Any]]:
        if self.coordinator is None:
            return False, "coordinator not configured", {}
        engine = self.coordinator.engine("event_bus")
        if engine is None:
            return False, "event bus not registered", {}
        running = bool(getattr(engine, "running", False))
        return (
            True,
            "event bus operational" if running else "event bus available (not started)",
            {"running": running},
        )

    def _probe_presence(self, name: str) -> Probe:
        def probe() -> tuple[bool, str, dict[str, Any]]:
            if self.coordinator is None:
                return False, "coordinator not configured", {}
            engine = self.coordinator.engine(name)
            if engine is None:
                return False, f"{name} engine not registered", {}
            return True, f"{name} engine available", {}

        return probe
