"""Unit tests for the canonical status service (risk R12).

Covers the four-state derivation rules and the ``build_canonical_status``
wiring — the single source of truth shared by the CLI ``runtime status``,
``GET /api/status``, and the dashboard pulse/System Health views.
"""

from __future__ import annotations

import pytest

from ai_company.runtime import create_runtime
from ai_company.runtime.models import RuntimePhase
from ai_company.services.status_service import (
    CanonicalState,
    _overall_for,
    build_canonical_status,
)

_MISSING_CONFIG = "__missing__"


def _summary(*, healthy: int = 0, degraded: int = 0, unhealthy: int = 0) -> dict:
    return {
        "status": "ok",
        "checks": [],
        "healthy": healthy,
        "degraded": degraded,
        "unhealthy": unhealthy,
    }


# ── Derivation rules (pure) ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("phase", "summary", "expected"),
    [
        # failed dominates everything -> action (needs action)
        (RuntimePhase.FAILED, _summary(healthy=3), CanonicalState.ACTION),
        # unhealthy probes -> action
        (RuntimePhase.RUNNING, _summary(healthy=1, unhealthy=1), CanonicalState.ACTION),
        # degraded probes -> watch
        (RuntimePhase.RUNNING, _summary(healthy=1, degraded=1), CanonicalState.WATCH),
        # running + clean -> ok
        (RuntimePhase.RUNNING, _summary(healthy=3), CanonicalState.OK),
        # running but nothing probed yet -> unknown (cannot determine)
        (RuntimePhase.RUNNING, _summary(), CanonicalState.UNKNOWN),
        # stopped is NOT broken (R12) -> watch, never action
        (RuntimePhase.STOPPED, _summary(), CanonicalState.WATCH),
        (RuntimePhase.STOPPED, _summary(unhealthy=3), CanonicalState.WATCH),
        (RuntimePhase.STOPPING, _summary(), CanonicalState.WATCH),
        # transitional phases -> watch
        (RuntimePhase.STARTING, _summary(), CanonicalState.WATCH),
        (RuntimePhase.RECOVERING, _summary(), CanonicalState.WATCH),
        (RuntimePhase.DEGRADED, _summary(), CanonicalState.WATCH),
    ],
)
def test_overall_for(
    phase: RuntimePhase, summary: dict, expected: CanonicalState
) -> None:
    assert _overall_for(phase, summary) is expected


# ── build_canonical_status wiring (stopped runtime, hermetic) ─────────────


def test_build_canonical_status_stopped_runtime() -> None:
    runtime = create_runtime(config_dir=_MISSING_CONFIG)
    canonical = build_canonical_status(runtime)

    # Four-state overall + timestamp (R12).
    assert canonical.overall is CanonicalState.WATCH  # stopped != broken
    assert canonical.timestamp is not None
    assert canonical.phase == "stopped"
    assert canonical.name == runtime.name

    # Legacy RuntimeStatus keys preserved (additive change).
    assert canonical.version
    assert canonical.uptime_seconds >= 0
    assert isinstance(canonical.engines, list)
    assert isinstance(canonical.processes, list)
    assert canonical.active_pipelines == 0
    assert canonical.active_workflows == 0
    assert canonical.active_decisions == 0
    assert canonical.active_meetings == 0
    assert canonical.active_projects == 0
    assert canonical.active_agents == 0

    # Health summary attached (single probe pass).
    assert "healthy" in canonical.health_summary
    assert "degraded" in canonical.health_summary
    assert "unhealthy" in canonical.health_summary


def test_facade_status_is_canonical() -> None:
    """The facade status() view now carries overall + timestamp (R12)."""
    from ai_company.services.runtime_facade import RuntimeFacade

    runtime = create_runtime(config_dir=_MISSING_CONFIG)
    facade = RuntimeFacade(config_dir=_MISSING_CONFIG, runtime=runtime)

    body = facade.status()
    assert body["overall"] in ("ok", "watch", "action", "unknown")
    assert body["overall"] == "watch"  # stopped -> watch (stopped != broken)
    assert body["phase"] == "stopped"
    assert body["timestamp"], "R12: every status is time-stamped"
    assert "name" in body  # legacy key preserved
