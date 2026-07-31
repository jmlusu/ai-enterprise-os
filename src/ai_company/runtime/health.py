"""Health monitoring — probes engines and aggregates HealthCheck results.

The health monitor probes every registered engine via its ``health()``
method (falling back to a heartbeat check), measures system resources with
psutil when available, and compares results against the ``health`` config
thresholds (CPU/memory percent, queue sizes, error rate).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ai_company.runtime.models import (
    HealthCheck,
    HealthStatus,
)

logger = logging.getLogger(__name__)

try:  # psutil is an optional dependency
    import psutil

    _HAS_PSUTIL = True
except Exception:  # pragma: no cover
    _HAS_PSUTIL = False


def _utcnow() -> datetime:
    return datetime.now(UTC)


class HealthMonitor:
    """Runs health probes against runtime components.

    Args:
        config: The ``health`` config section dict.
        probe: Optional override callable ``(name, component) -> dict``
            returning a probe result; the default probes ``health()``.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        probe: Callable[[str, Any], dict[str, Any]] | None = None,
    ) -> None:
        self.config = config or {}
        nested = self.config.get("thresholds", {})
        self.thresholds = nested if isinstance(nested, dict) and nested else self.config
        self._components: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._probe = probe or self._default_probe

    # ── Registration ───────────────────────────────────────────────

    def register(self, name: str, component: Any) -> None:
        """Register a component to be probed."""
        with self._lock:
            self._components[name] = component

    def unregister(self, name: str) -> bool:
        with self._lock:
            existed = name in self._components
            self._components.pop(name, None)
            return existed

    def components(self) -> list[str]:
        return list(self._components)

    # ── Probing ────────────────────────────────────────────────────

    @staticmethod
    def _default_probe(name: str, component: Any) -> dict[str, Any]:
        health = getattr(component, "health", None)
        if callable(health):
            try:
                result = health()
                if isinstance(result, dict):
                    return result
                if hasattr(result, "model_dump"):
                    return result.model_dump()
                return {"status": "healthy"}
            except Exception as exc:
                return {"status": "unhealthy", "error": str(exc)}
        return {"status": "healthy"}

    def _probe_component(self, name: str, component: Any) -> HealthCheck:
        try:
            result = self._probe(name, component)
        except Exception as exc:
            return HealthCheck(
                name=f"check_{name}",
                component=name,
                status=HealthStatus.UNHEALTHY,
                error=str(exc),
            )
        status_raw = str(result.get("status", "healthy")).lower()
        try:
            status = HealthStatus(status_raw)
        except ValueError:
            status = (
                HealthStatus.HEALTHY
                if status_raw in ("ok", "healthy", "running", "active")
                else HealthStatus.UNHEALTHY
            )
        details = {
            key: value for key, value in result.items() if key not in ("status",)
        }
        return HealthCheck(
            name=f"check_{name}",
            component=name,
            status=status,
            **({"details": details} if details else {}),
            error=result.get("error"),
        )

    def check_all(self) -> list[HealthCheck]:
        """Probe every registered component."""
        checks: list[HealthCheck] = []
        with self._lock:
            components = dict(self._components)
        for name, component in components.items():
            checks.append(self._probe_component(name, component))
        checks.append(self._system_check())
        return checks

    # ── System resources ───────────────────────────────────────────

    def _system_check(self) -> HealthCheck:
        if not _HAS_PSUTIL:
            return HealthCheck(
                name="check_system",
                component="system",
                status=HealthStatus.HEALTHY,
                details={"note": "psutil not available"},
            )
        try:
            cpu = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory().percent
            load = None
            try:
                load = psutil.getloadavg()[0]
            except Exception:
                pass
            details: dict[str, Any] = {
                "cpu_percent": round(cpu, 2),
                "memory_percent": round(memory, 2),
            }
            if load is not None:
                details["load_1m"] = round(load, 2)
            status = HealthStatus.HEALTHY
            problems: list[str] = []
            cpu_threshold = float(
                self.thresholds.get(
                    "cpu_percent", self.thresholds.get("cpu_percent_high", 80)
                )
            )
            memory_threshold = float(
                self.thresholds.get(
                    "memory_percent", self.thresholds.get("memory_percent_high", 80)
                )
            )
            if cpu > cpu_threshold:
                status = HealthStatus.DEGRADED
                problems.append(f"cpu={cpu:.1f}% > {cpu_threshold:.0f}%")
            if memory > memory_threshold:
                status = HealthStatus.DEGRADED
                problems.append(f"memory={memory:.1f}% > {memory_threshold:.0f}%")
            if problems:
                details["problems"] = problems
            return HealthCheck(
                name="check_system",
                component="system",
                status=status,
                details=details,
            )
        except Exception as exc:
            return HealthCheck(
                name="check_system",
                component="system",
                status=HealthStatus.UNHEALTHY,
                error=str(exc),
            )

    # ── Aggregation ────────────────────────────────────────────────

    def aggregate(self, checks: list[HealthCheck] | None = None) -> HealthStatus:
        """Return the worst status across checks."""
        checks = checks or self.check_all()
        if any(c.status is HealthStatus.UNHEALTHY for c in checks):
            return HealthStatus.UNHEALTHY
        if any(c.status is HealthStatus.DEGRADED for c in checks):
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    def summary(self) -> dict[str, Any]:
        """Return a compact health summary."""
        checks = self.check_all()
        status = self.aggregate(checks)
        return {
            "status": status.value,
            "checks": [
                {
                    "component": c.component,
                    "status": c.status.value,
                    "error": c.error,
                }
                for c in checks
            ],
            "healthy": sum(1 for c in checks if c.status is HealthStatus.HEALTHY),
            "degraded": sum(1 for c in checks if c.status is HealthStatus.DEGRADED),
            "unhealthy": sum(1 for c in checks if c.status is HealthStatus.UNHEALTHY),
        }
