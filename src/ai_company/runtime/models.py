"""Pydantic models for the Enterprise Runtime Engine.

Defines the data contract of the runtime: configuration, state, engine
and process lifecycles, heartbeats, health checks, startup/shutdown
sequences, diagnostics, recovery policies, and metrics.

Every model supports JSON and YAML serialization plus versioning through
:class:`_SerializableModel`.

Exceptions raised across the runtime package live here too (kept in one
module so the package layout matches the sprint structure exactly).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

__all__ = [
    "DiagnosticReport",
    "EngineState",
    "EngineStateStatus",
    "HealthCheck",
    "HealthStatus",
    "Heartbeat",
    "JobKind",
    "JobStatus",
    "ProcessStatus",
    "RecoveryPolicy",
    "RecoveryResult",
    "RuntimeConfig",
    "RuntimeMetrics",
    "RuntimePhase",
    "RuntimeProcess",
    "RuntimeState",
    "RuntimeStatus",
    "RuntimeTask",
    "ShutdownSequence",
    "ShutdownStep",
    "ShutdownStepStatus",
    "StartupSequence",
    "StartupStep",
    "StartupStepStatus",
    "RUNTIME_EVENT_TYPES",
    "CircuitBreakerOpenError",
]

RUNTIME_EVENT_TYPES: list[str] = [
    "runtime.started",
    "runtime.stopped",
    "runtime.restarted",
    "runtime.reloaded",
    "runtime.degraded",
    "runtime.recovered",
    "runtime.state_recovered",
    "runtime.component_failed",
    "runtime.component_restarted",
    "runtime.heartbeat_missed",
    "runtime.job_executed",
    "runtime.job_failed",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


# ── Exceptions ─────────────────────────────────────────────────────


class RuntimeError(Exception):
    """Base error for the Enterprise Runtime Engine."""


class RuntimeConfigError(RuntimeError):
    """Raised when runtime configuration is invalid or unloadable."""


class InvalidRuntimeTransitionError(RuntimeError):
    """Raised when an illegal runtime phase transition is attempted."""


class EngineNotRegisteredError(RuntimeError):
    """Raised when an engine/component is not known to the runtime."""


class StartupError(RuntimeError):
    """Raised when the startup sequence fails."""


class ShutdownError(RuntimeError):
    """Raised when the shutdown sequence fails."""


class JobRegistrationError(RuntimeError):
    """Raised when a runtime job cannot be registered."""


class RecoveryError(RuntimeError):
    """Raised when recovery for a component fails or is exhausted."""


class CircuitBreakerOpenError(RuntimeError):
    """Raised when circuit breaker is open and preventing operation."""


# ── Enums ──────────────────────────────────────────────────────────


class RuntimePhase(str, Enum):
    """Lifecycle phase of the runtime engine."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    RECOVERING = "recovering"
    STOPPING = "stopping"
    FAILED = "failed"


class EngineStateStatus(str, Enum):
    """Lifecycle status of a registered engine."""

    REGISTERED = "registered"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPING = "stopping"
    STOPPED = "stopped"


class ProcessStatus(str, Enum):
    """Lifecycle status of a managed process."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPED = "stopped"


class HealthStatus(str, Enum):
    """Health classification for checks, engines, and heartbeats."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class JobKind(str, Enum):
    """Scheduling kind of a runtime job."""

    ONE_TIME = "one_time"
    RECURRING = "recurring"
    CRON = "cron"
    DEPENDENCY = "dependency"
    EVENT = "event"


class JobStatus(str, Enum):
    """Execution status of a runtime job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StartupStepStatus(str, Enum):
    """Execution status of a startup step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ShutdownStepStatus(str, Enum):
    """Execution status of a shutdown step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── Serialization mixin ────────────────────────────────────────────


class _SerializableModel(BaseModel):
    """Adds JSON/YAML serialization + versioning to a model."""

    version: str = Field(default="1.0", description="Model schema version")

    def to_json(self, **kwargs: Any) -> str:
        """Serialize to a JSON string."""
        return self.model_dump_json(**kwargs)

    @classmethod
    def from_json(cls, data: str, **kwargs: Any) -> _SerializableModel:
        """Deserialize from a JSON string."""
        return cls.model_validate_json(data, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return self.model_dump(mode="json")

    def to_yaml(self) -> str:
        """Serialize to a YAML string."""
        return yaml.safe_dump(
            self.model_dump(mode="json"), sort_keys=False, allow_unicode=True
        )

    @classmethod
    def from_yaml(cls, data: str) -> _SerializableModel:
        """Deserialize from a YAML string."""
        return cls.model_validate(yaml.safe_load(data))


# ── Core models ────────────────────────────────────────────────────


class RuntimeConfig(_SerializableModel):
    """Validated runtime configuration (top-level section of runtime.yaml)."""

    name: str = Field(default="AI Enterprise Runtime")
    environment: str = Field(default="development")
    state_dir: str = Field(default="runtime")
    persist_state: bool = Field(default=True)
    max_workers: int = Field(default=4, ge=1)
    loop_interval_seconds: float = Field(default=1.0, gt=0)
    default_engine_timeout_seconds: float = Field(default=30.0, gt=0)
    audit_events: bool = Field(default=True)


class EngineState(_SerializableModel):
    """Lifecycle + health state of a registered engine."""

    name: str
    status: EngineStateStatus = Field(default=EngineStateStatus.REGISTERED)
    health: HealthStatus = Field(default=HealthStatus.HEALTHY)
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    restart_count: int = Field(default=0, ge=0)
    last_heartbeat: datetime | None = None
    message: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeProcess(_SerializableModel):
    """A managed runtime process (thread-backed or tracked external)."""

    id: str = Field(default_factory=lambda: _new_id("proc"))
    name: str
    status: ProcessStatus = Field(default=ProcessStatus.CREATED)
    pid: int | None = None
    thread_alive: bool = False
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    restart_count: int = Field(default=0, ge=0)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeTask(_SerializableModel):
    """A scheduled runtime job.

    ``kind`` selects the scheduling semantics:

    - ``one_time`` — run once when ``scheduled_at`` is reached.
    - ``recurring`` — run every ``interval_seconds`` up to ``max_runs``.
    - ``cron`` — run when the ``cron`` expression matches the current time.
    - ``dependency`` — run after every job in ``depends_on`` completed.
    - ``event`` — run when the event ``event_type`` is triggered.
    """

    id: str = Field(default_factory=lambda: _new_id("job"))
    name: str
    kind: JobKind = Field(default=JobKind.ONE_TIME)
    handler: str = Field(default="noop")
    params: dict[str, Any] = Field(default_factory=dict)
    scheduled_at: datetime | None = None
    interval_seconds: float | None = None
    cron: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    event_type: str | None = None
    enabled: bool = Field(default=True)
    status: JobStatus = Field(default=JobStatus.PENDING)
    last_run: datetime | None = None
    next_run: datetime | None = None
    run_count: int = Field(default=0, ge=0)
    max_runs: int = Field(default=0, ge=0)  # 0 = unlimited
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HealthCheck(_SerializableModel):
    """Result of one health probe."""

    name: str
    component: str = Field(default="runtime")
    status: HealthStatus = Field(default=HealthStatus.HEALTHY)
    checked_at: datetime = Field(default_factory=_utcnow)
    latency_ms: float = Field(default=0.0, ge=0)
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class Heartbeat(_SerializableModel):
    """A heartbeat record for a registered component."""

    component: str
    sent_at: datetime = Field(default_factory=_utcnow)
    received_at: datetime = Field(default_factory=_utcnow)
    seq: int = Field(default=0, ge=0)
    interval_seconds: float = Field(default=5.0, gt=0)
    status: HealthStatus = Field(default=HealthStatus.HEALTHY)
    payload: dict[str, Any] = Field(default_factory=dict)


class StartupStep(_SerializableModel):
    """One step of the startup sequence."""

    name: str
    description: str = Field(default="")
    status: StartupStepStatus = Field(default=StartupStepStatus.PENDING)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float = Field(default=0.0, ge=0)
    error: str | None = None
    reused: bool = Field(default=False)


class StartupSequence(_SerializableModel):
    """The full startup sequence result."""

    id: str = Field(default_factory=lambda: _new_id("startup"))
    name: str = Field(default="runtime-startup")
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None
    success: bool = Field(default=False)
    steps: list[StartupStep] = Field(default_factory=list)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == StartupStepStatus.COMPLETED)

    @property
    def failed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == StartupStepStatus.FAILED)


class ShutdownStep(_SerializableModel):
    """One step of the shutdown sequence."""

    name: str
    description: str = Field(default="")
    status: ShutdownStepStatus = Field(default=ShutdownStepStatus.PENDING)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float = Field(default=0.0, ge=0)
    error: str | None = None


class ShutdownSequence(_SerializableModel):
    """The full shutdown sequence result."""

    id: str = Field(default_factory=lambda: _new_id("shutdown"))
    name: str = Field(default="runtime-shutdown")
    reason: str = Field(default="manual")
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None
    success: bool = Field(default=False)
    force: bool = Field(default=False)
    steps: list[ShutdownStep] = Field(default_factory=list)


class RecoveryPolicy(_SerializableModel):
    """Recovery policy applied to a failed component."""

    name: str = Field(default="engine")
    enabled: bool = Field(default=True)
    max_attempts: int | None = Field(default=None, ge=0)
    backoff_base_seconds: float = Field(default=1.0, ge=0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)
    max_backoff_seconds: float = Field(default=60.0, ge=0)
    actions: list[str] = Field(
        default_factory=lambda: ["restart", "reload_state", "isolate"]
    )


class RecoveryResult(_SerializableModel):
    """Outcome of a recovery attempt."""

    component: str
    success: bool = Field(default=False)
    actions_taken: list[str] = Field(default_factory=list)
    attempts: int = Field(default=0, ge=0)
    message: str = Field(default="")
    recovered_at: datetime | None = None


class RuntimeMetrics(_SerializableModel):
    """A snapshot of runtime metrics."""

    uptime_seconds: float = Field(default=0.0, ge=0)
    cpu_percent: float | None = None
    memory_percent: float | None = None
    active_engines: int = Field(default=0, ge=0)
    active_workflows: int = Field(default=0, ge=0)
    active_decisions: int = Field(default=0, ge=0)
    active_pipelines: int = Field(default=0, ge=0)
    active_meetings: int = Field(default=0, ge=0)
    active_projects: int = Field(default=0, ge=0)
    active_agents: int = Field(default=0, ge=0)
    queue_sizes: dict[str, int] = Field(default_factory=dict)
    engine_healthy: int = Field(default=0, ge=0)
    engine_degraded: int = Field(default=0, ge=0)
    engine_failed: int = Field(default=0, ge=0)
    heartbeat_misses: int = Field(default=0, ge=0)
    failed_events: int = Field(default=0, ge=0)
    error_rate: float = Field(default=0.0, ge=0)
    jobs_executed: int = Field(default=0, ge=0)
    jobs_failed: int = Field(default=0, ge=0)
    restarts: int = Field(default=0, ge=0)
    recovery_attempts: int = Field(default=0, ge=0)
    recovery_successes: int = Field(default=0, ge=0)
    recovery_failures: int = Field(default=0, ge=0)
    recovery_success_rate: float = Field(default=0.0, ge=0)
    counters: dict[str, int] = Field(default_factory=dict)
    timers: dict[str, float] = Field(default_factory=dict)


class RuntimeState(_SerializableModel):
    """Persisted runtime state; recovered after a restart."""

    version: str = Field(default="1.0")
    phase: RuntimePhase = Field(default=RuntimePhase.STOPPED)
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    active_pipelines: list[str] = Field(default_factory=list)
    active_workflows: list[str] = Field(default_factory=list)
    active_decisions: list[str] = Field(default_factory=list)
    active_meetings: list[str] = Field(default_factory=list)
    active_projects: list[str] = Field(default_factory=list)
    active_agents: list[str] = Field(default_factory=list)
    processes: dict[str, RuntimeProcess] = Field(default_factory=dict)
    last_saved_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        """Return a compact summary dict (for CLI/status output)."""
        return {
            "phase": self.phase.value,
            "started_at": self.started_at,
            "active_pipelines": len(self.active_pipelines),
            "active_workflows": len(self.active_workflows),
            "active_decisions": len(self.active_decisions),
            "active_meetings": len(self.active_meetings),
            "active_projects": len(self.active_projects),
            "active_agents": len(self.active_agents),
            "processes": len(self.processes),
        }


class DiagnosticReport(_SerializableModel):
    """Full diagnostic report for the runtime."""

    id: str = Field(default_factory=lambda: _new_id("diag"))
    generated_at: datetime = Field(default_factory=_utcnow)
    runtime_name: str = Field(default="AI Enterprise Runtime")
    runtime_version: str = Field(default="1.0")
    phase: RuntimePhase = Field(default=RuntimePhase.STOPPED)
    uptime_seconds: float = Field(default=0.0, ge=0)
    engines: list[EngineState] = Field(default_factory=list)
    health_checks: list[HealthCheck] = Field(default_factory=list)
    metrics: RuntimeMetrics = Field(default_factory=RuntimeMetrics)
    config_sections: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class RuntimeStatus(_SerializableModel):
    """Status view of the runtime (used by CLI and dashboard)."""

    name: str = Field(default="AI Enterprise Runtime")
    version: str = Field(default="1.0")
    phase: RuntimePhase = Field(default=RuntimePhase.STOPPED)
    started_at: datetime | None = None
    uptime_seconds: float = Field(default=0.0, ge=0)
    engines: list[EngineState] = Field(default_factory=list)
    processes: list[RuntimeProcess] = Field(default_factory=list)
    active_pipelines: int = Field(default=0, ge=0)
    active_workflows: int = Field(default=0, ge=0)
    active_decisions: int = Field(default=0, ge=0)
    active_meetings: int = Field(default=0, ge=0)
    active_projects: int = Field(default=0, ge=0)
    active_agents: int = Field(default=0, ge=0)
    message: str = Field(default="")

    def to_dict(self) -> dict[str, Any]:
        """Compact dict for CLI table rendering."""
        return {
            "name": self.name,
            "version": self.version,
            "phase": self.phase.value,
            "uptime_seconds": self.uptime_seconds,
            "active_pipelines": self.active_pipelines,
            "active_workflows": self.active_workflows,
            "active_decisions": self.active_decisions,
            "active_meetings": self.active_meetings,
            "active_projects": self.active_projects,
            "active_agents": self.active_agents,
            "message": self.message,
        }


# ── Event bus adapter ──────────────────────────────────────────────

# The Event Bus only carries built-in EventType values, so runtime.*
# contract events are mapped to the closest built-in type. The original
# type string is preserved in the payload under "runtime_event_type".
RUNTIME_EVENT_MAP: dict[str, Any] = {}


def publish_runtime_event(
    bus: Any,
    event_type: str,
    payload: dict[str, Any] | None = None,
    source: str = "runtime",
) -> None:
    """Publish a ``runtime.*`` event on the event bus (never raises).

    Maps the runtime contract event type to a built-in bus EventType and
    records the original type in the payload, so the 12 ``runtime.*``
    types remain observable even though the bus enum cannot carry them.
    """
    if bus is None:
        return
    try:
        from ai_company.events.models import EventType

        mapped = RUNTIME_EVENT_MAP.get(event_type)
        if mapped is None:
            try:
                mapped = EventType(event_type)
            except ValueError:
                mapped = (
                    EventType.SYSTEM_ERROR
                    if event_type.endswith("_failed")
                    else EventType.SYSTEM_HEALTH_CHECK
                )
        body = dict(payload or {})
        body.setdefault("runtime_event_type", event_type)
        bus.publish_event(
            event_type=mapped,
            payload=body,
            source=source,
        )
    except Exception as exc:
        logger.warning("Could not publish runtime event %s: %s", event_type, exc)


def _build_runtime_event_map() -> dict[str, Any]:
    from ai_company.events.models import EventType

    mapping = {
        "runtime.started": EventType.SYSTEM_STARTUP,
        "runtime.stopped": EventType.SYSTEM_SHUTDOWN,
        "runtime.restarted": EventType.SYSTEM_STARTUP,
        "runtime.reloaded": EventType.REGISTRY_RELOADED,
        "runtime.degraded": EventType.SYSTEM_HEALTH_CHECK,
        "runtime.recovered": EventType.SYSTEM_HEALTH_CHECK,
        "runtime.state_recovered": EventType.SYSTEM_STARTUP,
        "runtime.component_failed": EventType.SYSTEM_ERROR,
        "runtime.component_restarted": EventType.SYSTEM_HEALTH_CHECK,
        "runtime.heartbeat_missed": EventType.SYSTEM_HEALTH_CHECK,
        "runtime.job_executed": EventType.SYSTEM_HEALTH_CHECK,
        "runtime.job_failed": EventType.SYSTEM_ERROR,
    }
    return mapping


RUNTIME_EVENT_MAP = _build_runtime_event_map()


# ── Helpers ────────────────────────────────────────────────────────


def save_yaml(path: str | Path, data: dict[str, Any]) -> None:
    """Write a dict to a YAML file (creates parent directories)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def load_yaml(path: str | Path) -> dict[str, Any] | None:
    """Read a YAML file into a dict; return None when missing/invalid."""
    target = Path(path)
    if not target.exists():
        return None
    with open(target, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return None
    return data


def _json_dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, default=str)
