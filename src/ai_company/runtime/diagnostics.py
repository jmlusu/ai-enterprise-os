"""Diagnostics — assembles a full DiagnosticReport for the runtime.

Collects runtime phase/status, engine states, health checks, metrics,
process info, scheduler stats, watchdog info, and configuration checksums
into a single :class:`DiagnosticReport`.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from ai_company.runtime.models import (
    DiagnosticReport,
    EngineState,
    HealthCheck,
    RuntimeMetrics,
    RuntimeStatus,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class DiagnosticCollector:
    """Collects runtime diagnostics from the engine's subsystems.

    Args:
        engine: The RuntimeEngine instance to inspect.
    """

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def collect(self) -> DiagnosticReport:
        """Gather diagnostics into a report."""
        engine = self.engine
        status: RuntimeStatus | None = None
        try:
            status = engine.status()
        except Exception as exc:
            logger.warning("Could not read runtime status: %s", exc)

        metrics: RuntimeMetrics | None = None
        try:
            metrics = engine.metrics()
        except Exception as exc:
            logger.warning("Could not read runtime metrics: %s", exc)

        health: list[HealthCheck] = []
        try:
            health = engine.health()
        except Exception as exc:
            logger.warning("Could not read runtime health: %s", exc)

        engine_states: list[EngineState] = []
        try:
            engine_states = engine.engine_states()
        except Exception as exc:
            logger.warning("Could not read engine states: %s", exc)

        warnings: list[str] = []
        errors: list[str] = []
        for check in health:
            if check.error:
                errors.append(f"{check.component}: {check.error}")

        scheduler_note = self._collect_scheduler_note()
        watchdog_note = self._collect_watchdog_note()
        process_note = self._collect_process_note()
        if scheduler_note:
            warnings.append(scheduler_note)
        if watchdog_note:
            warnings.append(watchdog_note)
        if process_note:
            warnings.append(process_note)

        config_sections: dict[str, str] = {}
        try:
            runtime_config = getattr(engine, "runtime_config", None)
            if runtime_config is not None:
                sections = getattr(runtime_config, "sections", None)
                if isinstance(sections, dict):
                    for section, data in sections.items():
                        config_sections[section] = _checksum(str(data))
        except Exception as exc:
            logger.warning("Could not compute config checksums: %s", exc)

        return DiagnosticReport(
            runtime_name=getattr(engine, "name", "AI Enterprise Runtime"),
            runtime_version=getattr(engine, "version", "1.0"),
            phase=status.phase if status is not None else None,
            uptime_seconds=(
                status.uptime_seconds
                if status is not None and status.uptime_seconds > 0
                else (metrics.uptime_seconds if metrics is not None else 0.0)
            ),
            engines=engine_states,
            health_checks=health,
            metrics=metrics or RuntimeMetrics(),
            config_sections=config_sections,
            warnings=warnings,
            errors=errors,
            recommendations=self._recommendations(errors),
        )

    def _collect_scheduler_note(self) -> str:
        scheduler = getattr(self.engine, "scheduler", None)
        if scheduler is None or not hasattr(scheduler, "snapshot"):
            return ""
        try:
            snap = scheduler.snapshot()
            return (
                f"scheduler: {snap['jobs']} jobs, {snap['executed']} executed, "
                f"{snap['failed']} failed"
            )
        except Exception as exc:
            logger.warning("Could not read scheduler snapshot: %s", exc)
            return ""

    def _collect_watchdog_note(self) -> str:
        watchdog = getattr(self.engine, "watchdog", None)
        if watchdog is None or not hasattr(watchdog, "snapshot"):
            return ""
        try:
            snap = watchdog.snapshot()
            return (
                f"watchdog: enabled={snap['enabled']}, running={snap['running']}, "
                f"tracked_tasks={snap['tracked_tasks']}"
            )
        except Exception as exc:
            logger.warning("Could not read watchdog snapshot: %s", exc)
            return ""

    def _collect_process_note(self) -> str:
        try:
            processes = self.engine.process_snapshot()
            return f"processes: {len(processes)} managed"
        except Exception as exc:
            logger.warning("Could not read process snapshot: %s", exc)
            return ""

    @staticmethod
    def _recommendations(errors: list[str]) -> list[str]:
        if not errors:
            return ["Runtime is healthy - no recommendations"]
        return [
            "Investigate failing health checks listed in errors",
            "Review runtime logs for stack traces around the failing components",
            "Check recovery policies in config/runtime/recovery.yaml",
        ]
