"""RuntimeEngine — the enterprise runtime kernel/facade.

The RuntimeEngine is the OS of the AI Company. It owns:

* the runtime lifecycle (phase state machine),
* the configuration registry (hot-reloadable),
* persisted runtime state (recovered across restarts),
* the engine registry (all subsystems: memory, event bus, decision,
  workflow, orchestration, ...),
* the dependency graph between engines (topological start/stop),
* background workers: heartbeat, watchdog, scheduler, supervisor,
* health monitoring, metrics, and diagnostics,
* recovery of failed components via the supervisor,
* startup/shutdown sequences driven from ``config/runtime/*.yaml``,
* event publishing of ``runtime.*`` lifecycle events.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_company.runtime.circuit_breaker import CircuitBreaker
from ai_company.runtime.configuration import RuntimeConfiguration
from ai_company.runtime.dependency_graph import RuntimeDependencyGraph
from ai_company.runtime.diagnostics import DiagnosticCollector
from ai_company.runtime.health import HealthMonitor
from ai_company.runtime.heartbeat import HeartbeatManager, HeartbeatSender
from ai_company.runtime.lifecycle import RuntimeLifecycle
from ai_company.runtime.metrics import MetricsRegistry
from ai_company.runtime.models import (
    CircuitBreakerOpenError,
    EngineNotRegisteredError,
    EngineState,
    EngineStateStatus,
    HealthStatus,
    JobKind,
    RecoveryError,
    RecoveryResult,
    RuntimeMetrics,
    RuntimePhase,
    RuntimeStatus,
    ShutdownError,
    ShutdownSequence,
    StartupError,
    StartupSequence,
    publish_runtime_event,
)
from ai_company.runtime.process_manager import ProcessManager
from ai_company.runtime.recovery import RecoveryManager
from ai_company.runtime.scheduler import JobScheduler
from ai_company.runtime.shutdown import ShutdownExecutor
from ai_company.runtime.startup import StartupExecutor
from ai_company.runtime.state import RuntimeStateStore
from ai_company.runtime.supervisor import Supervisor
from ai_company.runtime.watchdog import Watchdog

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RuntimeEngine:
    """Facade for the Enterprise Runtime Engine."""

    def __init__(
        self,
        config_dir: str | Path = "config",
        event_bus: Any | None = None,
        memory_engine: Any | None = None,
        name: str = "AI Enterprise Runtime",
        version: str = "1.0",
    ) -> None:
        self.name = name
        self.version = version
        self.config_dir = str(config_dir)
        self.runtime_config = RuntimeConfiguration(
            config_dir=str(Path(self.config_dir) / "runtime"), required=False
        )
        self.config = self.runtime_config.config

        # Lifecycle
        self.lifecycle = RuntimeLifecycle()
        self.runtime_id = f"rt_{_utcnow().strftime('%Y%m%d%H%M%S')}"
        self._started_at: datetime | None = None

        # Subsystems
        self.engines: dict[str, Any] = {}
        self._engine_states: dict[str, EngineState] = {}
        self.dependency_graph = RuntimeDependencyGraph()
        self.event_bus = event_bus
        self.memory_engine = memory_engine

        # State + processes
        self.state_store = RuntimeStateStore(
            config=self.config.model_dump(),
            memory_engine=self.memory_engine,
            state_dir=self.config.state_dir,
        )
        self.process_manager = ProcessManager()

        # Observability
        self.metrics_registry = MetricsRegistry()
        self.health_monitor = HealthMonitor(config=self._section("health"))
        self.heartbeats = HeartbeatManager(
            settings=self._section("heartbeat"),
            on_failure=self._on_component_failure,
        )
        # Liveness worker: beats for every registered engine so the
        # heartbeat monitor never declares healthy engines stale.
        self.heartbeat_sender = HeartbeatSender(
            heartbeats=self.heartbeats,
            engines=self.engines,
            isolated=self._isolated_components,
            interval_seconds=self.heartbeats.interval_seconds,
        )

        # Recovery + supervision
        self.recovery = RecoveryManager(
            config=self._section("recovery"),
            process_manager=self.process_manager,
            event_bus=self.event_bus,
            is_engine=lambda name: name in self.engines,
            metrics=self.metrics_registry,
        )
        self.supervisor = Supervisor(
            config=self._section("monitoring"),
            heartbeats=self.heartbeats,
            health=self.health_monitor,
            recovery=self.recovery,
            event_bus=self.event_bus,
            on_engine_failed=self._on_engine_failed,
        )
        self.watchdog = Watchdog(
            settings=self._section("monitoring"),
            heartbeats=self.heartbeats,
            on_failure=self._on_component_failure,
        )
        self.scheduler = JobScheduler(settings=self._section("scheduler"), runtime=self)
        self.diagnostic_collector = DiagnosticCollector(self)

        # Startup/shutdown sequence results
        self.startup_sequence: StartupSequence | None = None
        self.shutdown_sequence: ShutdownSequence | None = None

        # Circuit breakers for engine dependencies
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

        # Local runtime event handlers (keyed by runtime.* type string)
        self._handlers: dict[str, list[Callable[[str, dict[str, Any]], None]]] = {}
        self._handler_lock = threading.Lock()

        # Named job handlers from scheduler.yaml
        self._job_handlers: dict[str, Callable[[Any, Any], Any]] = {}
        self._register_builtin_job_handlers()

    # ── Configuration helpers ──────────────────────────────────────

    def _section(self, name: str) -> dict[str, Any]:
        return self.runtime_config.section(name) or {}

    # ── Engine registry ────────────────────────────────────────────

    def register_engine(
        self,
        name: str,
        instance: Any,
        metadata: dict[str, Any] | None = None,
    ) -> EngineState:
        """Register an engine/subcomponent with the runtime."""
        if name in self.engines:
            logger.warning(
                "Engine %s already registered — replacing previous instance",
                name,
            )
            self.unregister_engine(name)
        self.engines[name] = instance
        if name == "memory" and self.memory_engine is None:
            self.memory_engine = instance
        if name == "event_bus" and self.event_bus is None:
            self.event_bus = instance
        state = EngineState(
            name=name,
            status=EngineStateStatus.REGISTERED,
            metadata=metadata or {},
        )
        self._engine_states[name] = state
        self.dependency_graph.add_component(name)
        self.health_monitor.register(name, instance)
        self.heartbeats.register(name)
        # Register a restart factory so the supervisor can self-heal this
        # engine via the "restart" recovery action instead of isolating it.
        self.recovery.register_factory(
            name, lambda name=name: self._restart_engine(name)
        )
        self.state_store.set_engine(state)
        logger.info("Engine registered: %s", name)
        return state

    def register_engine_with_circuit_breaker(
        self,
        name: str,
        instance: Any,
        metadata: dict[str, Any] | None = None,
    ) -> EngineState:
        """Register an engine with circuit breaker protection."""
        state = self.register_engine(name, instance, metadata)

        # Add circuit breaker for this engine
        self._circuit_breakers[name] = CircuitBreaker(name)

        return state

    def unregister_engine(self, name: str) -> bool:
        """Remove an engine from the runtime registry."""
        if name not in self.engines:
            return False
        self.engines.pop(name, None)
        self._engine_states.pop(name, None)
        self.dependency_graph.remove_component(name)
        self.health_monitor.unregister(name)
        self.heartbeats.unregister(name)
        # Clean up circuit breaker for this engine
        self._circuit_breakers.pop(name, None)
        return True

    def get_engine(self, name: str) -> Any:
        """Return a registered engine instance."""
        engine = self.engines.get(name)
        if engine is None:
            raise EngineNotRegisteredError(f"Engine not registered: {name}")
        return engine

    def get_engine_optional(self, name: str) -> Any | None:
        """Return a registered engine instance, or None when unknown."""
        return self.engines.get(name)

    def add_dependency(self, component: str, depends_on: str) -> None:
        """Declare a dependency between registered components."""
        self.dependency_graph.add_dependency(component, depends_on)

    def engine_states(self) -> list[EngineState]:
        """Return lifecycle/health state for every registered engine."""
        return list(self._engine_states.values())

    def engine_state(self, name: str) -> EngineState | None:
        return self._engine_states.get(name)

    def _propagate_health_to_circuit_breakers(self):
        """Propagate health status to circuit breakers."""
        for name, engine_state in self._engine_states.items():
            if name in self._circuit_breakers:
                cb = self._circuit_breakers[name]
                if engine_state.health is HealthStatus.UNHEALTHY:
                    cb.on_failure()
                elif engine_state.health in (
                    HealthStatus.HEALTHY,
                    HealthStatus.DEGRADED,
                ):
                    cb.on_success()

    def _mark_engine_status(
        self,
        name: str,
        status: EngineStateStatus,
        health: HealthStatus | None = None,
        message: str = "",
    ) -> None:
        state = self._engine_states.get(name)
        if state is None:
            return
        state.status = status
        if health is not None:
            state.health = health
        if message:
            state.message = message
        if status in (EngineStateStatus.RUNNING, EngineStateStatus.REGISTERED):
            state.started_at = state.started_at or _utcnow()
            state.stopped_at = None
        if status in (EngineStateStatus.STOPPED, EngineStateStatus.FAILED):
            state.stopped_at = _utcnow()
        self.state_store.set_engine(state)

    # ── Handlers ───────────────────────────────────────────────────

    def register_handler(
        self, event_type: str, handler: Callable[[str, dict[str, Any]], None]
    ) -> None:
        """Register a local handler for a ``runtime.*`` event type."""
        with self._handler_lock:
            self._handlers.setdefault(event_type, []).append(handler)

    def _dispatch_local(self, event_type: str, payload: dict[str, Any]) -> None:
        with self._handler_lock:
            handlers = list(self._handlers.get(event_type, []))
        for handler in handlers:
            try:
                handler(event_type, payload)
            except Exception as exc:
                logger.error("Runtime event handler error for %s: %s", event_type, exc)

    def _publish(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        body = dict(payload or {})
        self._dispatch_local(event_type, body)
        bus = self.event_bus
        if bus is None:
            return
        running = getattr(bus, "is_running", True)
        if callable(running):
            running = running()
        if not running:
            logger.debug("Event bus not running — skipping %s", event_type)
            return
        publish_runtime_event(bus, event_type, body, source=self.name)

    # ── Lifecycle ──────────────────────────────────────────────────

    def start(self) -> RuntimeStatus:
        """Boot the runtime: run the startup sequence, then mark ready."""
        if self.lifecycle.is_active():
            logger.info("Runtime already active (phase=%s)", self.lifecycle.phase.value)
            return self.status()
        self.lifecycle.transition(RuntimePhase.STARTING)
        # Recover persisted state BEFORE any phase save, otherwise the
        # STARTING-phase save clobbers the on-disk state with an empty one.
        self.state_store.load()
        self.state_store.set_phase(RuntimePhase.STARTING)
        startup = self._section("startup")
        self.startup_executor = StartupExecutor(
            self,
            config=startup,
            steps=startup.get("steps", []),
        )
        try:
            self.startup_executor.run()
        except StartupError:
            self.lifecycle.transition(RuntimePhase.FAILED)
            self.state_store.set_phase(RuntimePhase.FAILED)
            self._publish(
                "runtime.component_failed",
                {"component": "startup", "reason": "startup_failed"},
            )
            raise
        self.startup_sequence = self.startup_executor.sequence
        self.mark_ready()
        return self.status()

    def mark_ready(self) -> None:
        """Mark the runtime RUNNING (called by the ``ready`` startup step)."""
        if self.lifecycle.phase is RuntimePhase.RUNNING:
            return
        if self.lifecycle.phase is RuntimePhase.STARTING:
            self.lifecycle.transition(RuntimePhase.RUNNING)
        else:
            self.lifecycle.force(RuntimePhase.RUNNING)
        self._started_at = _utcnow()
        self.state_store.set_started(self._started_at)
        self.metrics_registry.increment("starts")
        self._publish("runtime.started", {"runtime_id": self.runtime_id})
        logger.info("Runtime %s is RUNNING", self.runtime_id)

    def start_workers(self) -> None:
        """Start background workers (called by the ``start_runtime`` step)."""
        self._start_event_bus()
        self._start_registered_engines()
        self.heartbeat_sender.start()
        self.scheduler.start()
        self.watchdog.start()
        self.supervisor.start()
        self._register_config_jobs()
        logger.info("Runtime workers started")

    def _start_event_bus(self) -> None:
        bus = self.event_bus
        if bus is None:
            return

        # Check backpressure
        current_load = getattr(bus, "get_load", lambda: 0)()
        max_load = getattr(bus, "max_load", 100)

        if current_load > max_load * 0.9:
            # Backpressure detected, use circuit breaker to isolate
            if bus.name in self._circuit_breakers:
                cb = self._circuit_breakers[bus.name]
                cb.call(lambda: bus.stop())  # Force stop to prevent overload
            return

        running = getattr(bus, "is_running", False)
        if callable(running):
            running = running()
        if running:
            return
        start = getattr(bus, "start", None)
        if callable(start):
            try:
                start()
            except Exception as exc:
                logger.warning("Could not start event bus: %s", exc)

    def _start_engine_with_protection(self, name: str, instance: Any):
        """Start an engine with circuit breaker protection."""
        if name in self._circuit_breakers:
            cb = self._circuit_breakers[name]
            try:
                return cb.call(self._start_engine, name, instance)
            except CircuitBreakerOpenError:
                # Engine is isolated, mark as failed
                self._mark_engine_status(
                    name,
                    EngineStateStatus.FAILED,
                    HealthStatus.UNHEALTHY,
                    "Circuit breaker is open",
                )
                return False
        return self._start_engine(name, instance)

    def _start_engine(self, name: str, instance: Any):
        """Internal start method for engines."""
        import inspect

        if name in ("event_bus",):
            return

        start = getattr(instance, "start", None)
        if not callable(start):
            self._mark_engine_status(
                name, EngineStateStatus.RUNNING, HealthStatus.HEALTHY
            )
            return

        try:
            signature = inspect.signature(start)
            required = [
                param
                for param in signature.parameters.values()
                if param.default is inspect.Parameter.empty
                and param.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            ]
            if required:
                logger.info(
                    "Engine %s.start() requires %s — marking running without "
                    "starting it (start it explicitly via the engine)",
                    name,
                    [param.name for param in required],
                )
                self._mark_engine_status(
                    name, EngineStateStatus.RUNNING, HealthStatus.HEALTHY
                )
                return
            start()
            self._mark_engine_status(
                name, EngineStateStatus.RUNNING, HealthStatus.HEALTHY
            )
        except Exception as exc:
            logger.warning("Engine %s did not start cleanly: %s", name, exc)
            self._mark_engine_status(
                name, EngineStateStatus.DEGRADED, HealthStatus.DEGRADED, str(exc)
            )

    def _start_registered_engines(self) -> None:
        for name, instance in self.engines.items():
            if name in ("event_bus",):
                continue
            self._start_engine_with_protection(name, instance)

    def mark_stopped(self) -> None:
        """Mark the runtime STOPPED (called by the ``finalize`` shutdown step)."""
        if self.lifecycle.phase is RuntimePhase.STOPPED:
            return
        if self.lifecycle.can_transition(RuntimePhase.STOPPED):
            self.lifecycle.transition(RuntimePhase.STOPPED)
        else:
            self.lifecycle.force(RuntimePhase.STOPPED)
        self.state_store.set_stopped()
        self._publish("runtime.stopped", {"runtime_id": self.runtime_id})
        logger.info("Runtime %s is STOPPED", self.runtime_id)

    def stop(self, reason: str = "manual", force: bool = False) -> RuntimeStatus:
        """Shut the runtime down in dependency-safe order."""
        if not self.lifecycle.is_active():
            logger.info("Runtime not active — nothing to stop")
            return self.status()
        self.lifecycle.transition(RuntimePhase.STOPPING)
        self.state_store.set_phase(RuntimePhase.STOPPING)
        self.shutdown_executor = ShutdownExecutor(
            self,
            config=self._section("shutdown"),
            reason=reason,
            force=force,
        )
        try:
            self.shutdown_executor.run()
        except ShutdownError:
            self.lifecycle.transition(RuntimePhase.FAILED)
            self.state_store.set_phase(RuntimePhase.FAILED)
            raise
        self.shutdown_sequence = self.shutdown_executor.sequence
        return self.status()

    def restart(self, reason: str = "manual") -> RuntimeStatus:
        """Stop and start the runtime; publishes ``runtime.restarted``."""
        if self.lifecycle.is_active():
            self.stop(reason=reason)
        self.start()
        self.metrics_registry.increment("restarts")
        self._publish(
            "runtime.restarted",
            {"runtime_id": self.runtime_id, "reason": reason},
        )
        return self.status()

    def reload(self) -> list[str]:
        """Hot-reload configuration; returns changed section names."""
        changed = self.runtime_config.reload()
        self.config = self.runtime_config.config
        self._apply_reloaded_config()
        self._publish("runtime.reloaded", {"changed": changed})
        return changed

    def _apply_reloaded_config(self) -> None:
        self.heartbeats.settings = self._section("heartbeat")
        self.heartbeats.interval_seconds = float(
            self.heartbeats.settings.get("interval_seconds", 5.0)
        )
        self.heartbeats.timeout_seconds = float(
            self.heartbeats.settings.get("timeout_seconds", 15.0)
        )
        self.heartbeat_sender.interval_seconds = self.heartbeats.interval_seconds
        self.watchdog.settings = self._section("monitoring")
        self.supervisor.config = self._section("monitoring")
        scheduler = self._section("scheduler")
        self.scheduler.settings = scheduler
        self.scheduler.interval_seconds = float(
            scheduler.get("worker_interval_seconds", 1.0)
        )

    # ── Workers / jobs ─────────────────────────────────────────────

    def _register_builtin_job_handlers(self) -> None:
        self._job_handlers["noop"] = self._job_noop
        self._job_handlers["event_publish"] = self._job_event_publish
        self._job_handlers["memory_consolidation"] = self._job_memory_consolidation
        self._job_handlers["orchestrate_pipeline"] = self._job_orchestrate_pipeline
        self._job_handlers["telemetry_retention"] = self._job_telemetry_retention

    def register_job_handler(
        self, name: str, handler: Callable[[Any, Any], Any]
    ) -> None:
        """Register a named handler referenced by scheduler.yaml jobs."""
        self._job_handlers[name] = handler

    def _register_config_jobs(self) -> None:
        # Drop previously registered config jobs so restarts never collide.
        for old_name in list(getattr(self, "_config_job_names", ())):
            self.scheduler.unregister(old_name)
        self._config_job_names = set()
        jobs = self._section("scheduler").get("jobs", {})
        for job in jobs.values():
            if not isinstance(job, dict) or not job.get("enabled", True):
                continue
            task = self.submit_job(
                name=str(job.get("name", "job")),
                kind=job.get("kind", "one_time"),
                handler=self._job_handlers.get(
                    job.get("handler", "noop"), self._job_noop
                ),
                cron=job.get("cron"),
                interval_seconds=job.get("interval_seconds"),
                params=job.get("params") or {},
            )
            self._config_job_names.add(task.name)

    def submit_job(
        self,
        name: str,
        kind: JobKind | str = JobKind.ONE_TIME,
        handler: Callable[[Any, Any], Any] | None = None,
        scheduled_at: str | datetime | None = None,
        interval_seconds: float | None = None,
        cron: str | None = None,
        depends_on: list[str] | None = None,
        event_type: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Submit a job to the scheduler. Returns the RuntimeTask."""
        return self.scheduler.register(
            name=name,
            kind=kind,
            handler=handler,
            scheduled_at=scheduled_at,
            interval_seconds=interval_seconds,
            cron=cron,
            depends_on=depends_on,
            event_type=event_type,
            params=params,
        )

    def _job_noop(self, job: Any, runtime: Any) -> None:
        return None

    def _job_event_publish(self, job: Any, runtime: Any) -> None:
        params = job.params or {}
        event_type = params.get("event_type", "runtime.job_executed")
        self._publish(event_type, {"job": job.name, "message": params.get("message")})
        self.metrics_registry.increment("jobs_executed")

    def _job_memory_consolidation(self, job: Any, runtime: Any) -> None:
        engine = self.memory_engine
        if engine is None:
            logger.warning("memory_consolidation job skipped (no memory engine)")
            return
        try:
            engine.save(
                content={
                    "kind": "consolidation",
                    "job": job.name,
                    "triggered_at": _utcnow().isoformat(),
                },
                memory_type="system",
                namespace="global",
                tags=["runtime", "consolidation"],
                source="runtime.scheduler",
            )
        except Exception as exc:
            logger.warning("Memory consolidation failed: %s", exc)

    def _job_telemetry_retention(self, job: Any, runtime: Any) -> None:
        """Apply telemetry retention policies (rollup-then-truncate, fail-open).

        Backed by ``config/runtime/telemetry.yaml`` (sprint 5.4 T2). Never
        raises: a retention failure must not break the scheduler worker.
        """
        try:
            from ai_company.telemetry.retention import apply_retention, load_policies

            policies = load_policies(self._section("telemetry"))
            report = apply_retention(policies=policies, dry_run=False)
            logger.info(
                "Telemetry retention applied: %s rolled up, %s truncated",
                report.get("total_rolled_up", 0),
                report.get("total_truncated", 0),
            )
        except Exception as exc:
            logger.warning("Telemetry retention failed: %s", exc)

    def _job_orchestrate_pipeline(self, job: Any, runtime: Any) -> None:
        orchestration = self.get_engine_optional("orchestration")
        if orchestration is None:
            logger.warning("orchestrate_pipeline job skipped (no orchestration engine)")
            return
        pipeline = (job.params or {}).get("pipeline", "default")
        try:
            catalog = orchestration.list_pipelines()
            if pipeline not in catalog:
                logger.warning(
                    "Pipeline %r not in orchestration catalog (%s); skipping "
                    "orchestrate_pipeline job",
                    pipeline,
                    ", ".join(catalog) or "none",
                )
                return
            plan = orchestration.plan(pipeline)
            orchestration.run(plan)
        except Exception as exc:
            logger.warning("Pipeline orchestration job failed: %s", exc)
            self.metrics_registry.increment("jobs_failed")
            raise

    def track_task(self, task_id: str, deadline_seconds: float | None = None) -> None:
        """Track a task deadline with the watchdog."""
        self.watchdog.track_task(task_id, deadline_seconds)

    def untrack_task(self, task_id: str) -> None:
        """Stop tracking a task."""
        self.watchdog.untrack_task(task_id)

    def register_process(
        self,
        name: str,
        target: Callable[..., Any] | None = None,
        pid: int | None = None,
    ) -> Any:
        """Register a managed runtime process."""
        return self.process_manager.register(name, target=target, pid=pid)

    # ── Failure handling ───────────────────────────────────────────

    def _isolated_components(self) -> list[str]:
        """Return the names of isolated components (for the heartbeat sender)."""
        if self.supervisor is not None:
            return self.supervisor.isolated()
        return []

    def _on_component_failure(self, component: str, reason: str) -> None:
        """Heartbeat/watchdog failure → forward to the supervisor."""
        if self.supervisor is not None:
            self.supervisor.on_failure(component, reason)

    def _on_engine_failed(self, name: str, reason: str, result: RecoveryResult) -> None:
        if result.success:
            self._mark_engine_status(
                name,
                EngineStateStatus.RUNNING,
                HealthStatus.HEALTHY,
                f"recovered via {', '.join(result.actions_taken) or 'none'}",
            )
            self.metrics_registry.increment("recoveries")
            self._publish(
                "runtime.component_restarted",
                {"component": name, "reason": reason},
            )
            return
        self._mark_engine_status(
            name, EngineStateStatus.FAILED, HealthStatus.UNHEALTHY, reason
        )
        self.metrics_registry.increment("failures")
        if self.lifecycle.phase is RuntimePhase.RUNNING:
            try:
                self.lifecycle.transition(RuntimePhase.DEGRADED)
            except Exception:
                self.lifecycle.force(RuntimePhase.DEGRADED)
            self._publish("runtime.degraded", {"component": name, "reason": reason})

    def recover_engine(self, name: str, reason: str = "manual") -> RecoveryResult:
        """Manually trigger recovery for a component."""
        return self.recovery.recover(name, reason)

    def _restart_engine(self, name: str) -> None:
        """Restart a registered engine (used by the recovery manager).

        Tries ``instance.restart()`` when the engine exposes one, then
        re-admits the engine to supervision with a fresh liveness window so
        the supervisor gives it another chance before isolating it.
        """
        instance = self.engines.get(name)
        if instance is None:
            raise RecoveryError(f"Engine not registered: {name}")
        restart = getattr(instance, "restart", None)
        if callable(restart):
            try:
                restart()
            except Exception as exc:
                logger.warning("Engine %s restart() raised: %s", name, exc)
        # Reset the heartbeat so the engine gets a fresh window after
        # restart instead of being declared stale immediately.
        self.heartbeats.beat(name)
        logger.info("Engine %s restarted via recovery factory", name)

    def unisolate(self, name: str) -> None:
        """Re-admit an isolated component to supervision."""
        self.supervisor.unisolate(name)

    # ── Observability ──────────────────────────────────────────────

    def status(self) -> RuntimeStatus:
        """Return the runtime status view."""
        state = self.state_store.state
        uptime = 0.0
        if self._started_at is not None and self.lifecycle.is_active():
            uptime = max(0.0, (_utcnow() - self._started_at).total_seconds())
        return RuntimeStatus(
            name=self.name,
            version=self.version,
            phase=self.lifecycle.phase,
            started_at=self._started_at or state.started_at,
            uptime_seconds=round(uptime, 3),
            engines=self.engine_states(),
            processes=self.process_manager.list_processes(),
            active_pipelines=len(state.active_pipelines),
            active_workflows=len(state.active_workflows),
            active_decisions=len(state.active_decisions),
            active_meetings=len(state.active_meetings),
            active_projects=len(state.active_projects),
            active_agents=len(state.active_agents),
            message="",
        )

    def health(self) -> list[Any]:
        """Run health probes against all engines (+ system check)."""
        return self.health_monitor.check_all()

    def metrics(self) -> RuntimeMetrics:
        """Return the current runtime metrics snapshot."""
        self._refresh_gauges()
        return self.metrics_registry.to_metrics()

    def _refresh_gauges(self) -> None:
        metrics = self.metrics_registry
        state = self.state_store.state
        healthy = degraded = failed = 0
        for engine_state in self._engine_states.values():
            if engine_state.health is HealthStatus.UNHEALTHY:
                failed += 1
            elif engine_state.health is HealthStatus.DEGRADED:
                degraded += 1
            else:
                healthy += 1
        metrics.set_gauge("active_engines", len(self.engines))
        metrics.set_gauge("engine_healthy", healthy)
        metrics.set_gauge("engine_degraded", degraded)
        metrics.set_gauge("engine_failed", failed)
        metrics.set_gauge("active_pipelines", len(state.active_pipelines))
        metrics.set_gauge("active_workflows", len(state.active_workflows))
        metrics.set_gauge("active_decisions", len(state.active_decisions))
        metrics.set_gauge("active_meetings", len(state.active_meetings))
        metrics.set_gauge("active_projects", len(state.active_projects))
        metrics.set_gauge("active_agents", len(state.active_agents))
        metrics.set_gauge("heartbeat_misses", self.heartbeats.heartbeat_miss_count())
        if hasattr(self.scheduler, "queue_sizes"):
            metrics.set_gauge("queue_sizes", self.scheduler.queue_sizes())

    def diagnostics(self) -> Any:
        """Return a full DiagnosticReport."""
        return self.diagnostic_collector.collect()

    def process_snapshot(self) -> list[dict[str, Any]]:
        """Return the process manager snapshot entries."""
        return self.process_manager.snapshot()["processes"]

    def health_summary(self) -> dict[str, Any]:
        return self.health_monitor.summary()
