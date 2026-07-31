"""Enterprise Runtime Engine — the kernel/OS layer of the AI Company.

The runtime starts the AI company, initializes all engines, supervises
agent lifecycles, monitors health, recovers from failures, schedules
recurring work, executes autonomous workflows, maintains persisted
state, coordinates shutdown, and supports hot config reload.

Modules:
    models          — data contracts (state, heartbeats, health, jobs, ...)
    configuration   — YAML-driven runtime configuration (+ hot reload)
    lifecycle       — runtime phase state machine
    dependency_graph— engine start/stop ordering
    state           — persisted runtime state (JSON + memory mirror)
    process_manager — managed runtime processes
    heartbeat       — component liveness tracking
    watchdog        — stale-component and task-deadline enforcement
    scheduler       — recurring/cron/dependency/event job execution
    health          — engine probes + system resource checks
    metrics         — counters, gauges, timers
    diagnostics     — DiagnosticReport assembly
    supervisor      — failure detection + recovery coordination
    recovery        — recovery policy execution
    startup         — startup sequence executor
    shutdown        — shutdown sequence executor
    engine          — RuntimeEngine facade
    runtime         — create_runtime / main_loop entry points
"""

from ai_company.runtime.configuration import RuntimeConfiguration
from ai_company.runtime.dependency_graph import (
    DependencyCycleError,
    RuntimeDependencyGraph,
)
from ai_company.runtime.diagnostics import DiagnosticCollector
from ai_company.runtime.engine import RuntimeEngine
from ai_company.runtime.health import HealthMonitor
from ai_company.runtime.heartbeat import HeartbeatManager
from ai_company.runtime.lifecycle import RuntimeLifecycle
from ai_company.runtime.metrics import MetricsRegistry
from ai_company.runtime.models import (
    RUNTIME_EVENT_TYPES,
    DiagnosticReport,
    EngineNotRegisteredError,
    EngineState,
    EngineStateStatus,
    HealthCheck,
    HealthStatus,
    Heartbeat,
    InvalidRuntimeTransitionError,
    JobKind,
    JobRegistrationError,
    JobStatus,
    ProcessStatus,
    RecoveryError,
    RecoveryPolicy,
    RecoveryResult,
    RuntimeConfig,
    RuntimeConfigError,
    RuntimeError,
    RuntimeMetrics,
    RuntimePhase,
    RuntimeProcess,
    RuntimeState,
    RuntimeStatus,
    RuntimeTask,
    ShutdownError,
    ShutdownSequence,
    ShutdownStep,
    ShutdownStepStatus,
    StartupError,
    StartupSequence,
    StartupStep,
    StartupStepStatus,
    load_yaml,
    publish_runtime_event,
    save_yaml,
)
from ai_company.runtime.process_manager import ProcessManager
from ai_company.runtime.recovery import RecoveryManager
from ai_company.runtime.runtime import create_runtime, main_loop
from ai_company.runtime.scheduler import JobScheduler
from ai_company.runtime.shutdown import ShutdownExecutor
from ai_company.runtime.startup import StartupExecutor
from ai_company.runtime.state import RuntimeStateStore
from ai_company.runtime.supervisor import Supervisor
from ai_company.runtime.watchdog import Watchdog

__all__ = [
    # Facade + entry points
    "RuntimeEngine",
    "create_runtime",
    "main_loop",
    # Configuration
    "RuntimeConfiguration",
    # Lifecycle
    "RuntimeLifecycle",
    "RuntimePhase",
    "InvalidRuntimeTransitionError",
    # Dependency graph
    "RuntimeDependencyGraph",
    "DependencyCycleError",
    # State + processes
    "RuntimeStateStore",
    "RuntimeState",
    "RuntimeProcess",
    "ProcessStatus",
    "ProcessManager",
    # Heartbeat / watchdog
    "HeartbeatManager",
    "Heartbeat",
    "Watchdog",
    # Health / metrics / diagnostics
    "HealthMonitor",
    "HealthCheck",
    "HealthStatus",
    "MetricsRegistry",
    "RuntimeMetrics",
    "DiagnosticCollector",
    "DiagnosticReport",
    # Scheduler
    "JobScheduler",
    "JobKind",
    "JobStatus",
    "RuntimeTask",
    "JobRegistrationError",
    # Startup / shutdown
    "StartupExecutor",
    "StartupSequence",
    "StartupStep",
    "StartupStepStatus",
    "ShutdownExecutor",
    "ShutdownSequence",
    "ShutdownStep",
    "ShutdownStepStatus",
    "StartupError",
    "ShutdownError",
    # Supervision / recovery
    "Supervisor",
    "RecoveryManager",
    "RecoveryPolicy",
    "RecoveryResult",
    "RecoveryError",
    # Engines
    "EngineState",
    "EngineStateStatus",
    "EngineNotRegisteredError",
    # Config + helpers
    "RuntimeConfig",
    "RuntimeStatus",
    "RuntimeError",
    "RuntimeConfigError",
    "RUNTIME_EVENT_TYPES",
    "load_yaml",
    "save_yaml",
    "publish_runtime_event",
]
