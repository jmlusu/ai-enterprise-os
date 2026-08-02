"""Canonical runtime status service (risk R12).

One canonical four-state vocabulary — ``ok`` / ``watch`` / ``action`` /
``unknown`` — with a timestamp on every status, shared by every surface so
no surface invents its own wording and "stopped" never reads as "broken".

Surfaces that derive from this single service:

- CLI ``ai-company runtime status`` (Overall line)
- API ``GET /api/status`` (``overall`` + ``timestamp`` keys)
- Dashboard pulse / System Health views (overall chip)

Derivation rules (single source of truth, phase state machine dominates):

- ``action`` — runtime phase ``failed``, or unhealthy probes while running
- ``watch``  — runtime ``stopped``/``stopping`` (stopped is a legitimate
  state, not a failure — R12; probes against a stopped runtime are ignored),
  a transitional phase (``starting``, ``recovering``, ``degraded``), or
  degraded probes while running
- ``ok``     — runtime ``running`` with a clean health summary
- ``unknown``— the runtime is running but nothing has been probed yet
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from ai_company.runtime.engine import RuntimeEngine
from ai_company.runtime.models import RuntimePhase

__all__ = ["CanonicalState", "CanonicalStatus", "build_canonical_status"]


class CanonicalState(str, Enum):
    """The four states every status can be in (R12)."""

    OK = "ok"
    WATCH = "watch"
    ACTION = "action"
    UNKNOWN = "unknown"


class CanonicalStatus(BaseModel):
    """Canonical, time-stamped status snapshot shared by every surface.

    Superset of the legacy ``RuntimeStatus`` payload: every legacy key is
    preserved (additive change), plus the four-state ``overall``, the
    ``health_summary``, and the snapshot ``timestamp`` (R12).
    """

    overall: CanonicalState
    timestamp: datetime
    name: str = "AI Enterprise Runtime"
    version: str = "1.0"
    phase: str = "stopped"
    started_at: str | None = None
    uptime_seconds: float = 0.0
    engines: list[dict[str, Any]] = Field(default_factory=list)
    processes: list[dict[str, Any]] = Field(default_factory=list)
    active_pipelines: int = 0
    active_workflows: int = 0
    active_decisions: int = 0
    active_meetings: int = 0
    active_projects: int = 0
    active_agents: int = 0
    health_summary: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


def _overall_for(phase: RuntimePhase, health_summary: dict[str, Any]) -> CanonicalState:
    """Derive the canonical four-state overall from phase + probes.

    The phase state machine dominates for terminal phases — probes only mean
    something while the runtime is actually running (R12: stopped is not
    broken; probe results against a stopped runtime are expected to be red).
    """
    if phase is RuntimePhase.FAILED:
        return CanonicalState.ACTION
    if phase in (RuntimePhase.STOPPED, RuntimePhase.STOPPING):
        return CanonicalState.WATCH
    if phase is RuntimePhase.RUNNING:
        unhealthy = int(health_summary.get("unhealthy") or 0)
        degraded = int(health_summary.get("degraded") or 0)
        if unhealthy > 0:
            return CanonicalState.ACTION
        if degraded > 0:
            return CanonicalState.WATCH
        total_checks = unhealthy + degraded + int(health_summary.get("healthy") or 0)
        return CanonicalState.OK if total_checks > 0 else CanonicalState.UNKNOWN
    if phase in (RuntimePhase.STARTING, RuntimePhase.DEGRADED, RuntimePhase.RECOVERING):
        return CanonicalState.WATCH
    return CanonicalState.UNKNOWN


def build_canonical_status(runtime: RuntimeEngine) -> CanonicalStatus:
    """Snapshot the runtime through the canonical lens (R12).

    Single source of truth for the status surface: ``runtime status``,
    ``GET /api/status``, and the dashboard pulse/health views all derive
    from this one function, so the four-state vocabulary can never drift
    between surfaces.
    """
    raw = runtime.status().model_dump(mode="json")
    try:
        health_summary: dict[str, Any] = runtime.health_summary()
    except Exception:
        health_summary = {}
    phase = RuntimePhase(raw.get("phase") or RuntimePhase.STOPPED.value)
    return CanonicalStatus(
        overall=_overall_for(phase, health_summary),
        timestamp=datetime.now(UTC),
        name=raw.get("name", "AI Enterprise Runtime"),
        version=raw.get("version", "1.0"),
        phase=phase.value,
        started_at=raw.get("started_at"),
        uptime_seconds=raw.get("uptime_seconds", 0.0),
        engines=raw.get("engines", []),
        processes=raw.get("processes", []),
        active_pipelines=raw.get("active_pipelines", 0),
        active_workflows=raw.get("active_workflows", 0),
        active_decisions=raw.get("active_decisions", 0),
        active_meetings=raw.get("active_meetings", 0),
        active_projects=raw.get("active_projects", 0),
        active_agents=raw.get("active_agents", 0),
        health_summary=health_summary,
        message=raw.get("message", ""),
    )
