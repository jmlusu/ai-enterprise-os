"""Startup sequence — boots the runtime from ``config/runtime/startup.yaml``.

Each configured step is either:

* an **internal target** (``load_constitution``, ``load_project_state``,
  ``load_configuration``, ``start_runtime``, ``ready``) executed by the
  executor itself, or
* a **class step** (``module`` + ``class`` + ``engine`` name + ``params``)
  instantiated via importlib and registered on the runtime.

Steps whose engine name is already registered are reused, not re-created
(``reused=True`` on the StartupStep). Progress and results are recorded in
a :class:`StartupSequence`.
"""

from __future__ import annotations

import importlib
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_company.runtime.models import (
    RuntimePhase,
    StartupError,
    StartupSequence,
    StartupStep,
    StartupStepStatus,
    load_yaml,
    publish_runtime_event,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, StartupStepStatus, str], None]

_INTERNAL_TARGETS = {
    "load_constitution",
    "load_project_state",
    "load_configuration",
    "start_runtime",
    "ready",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


class StartupExecutor:
    """Executes the startup sequence.

    Args:
        engine: The RuntimeEngine being booted (duck-typed: needs
            ``engines``, ``register_engine``, ``state_store``,
            ``runtime_config``, ``config_dir``, ``event_bus``,
            ``start_workers``, ``mark_ready``).
        config: The ``startup`` config section dict.
        steps: Step definitions (defaults to ``config["steps"]``).
        on_progress: Optional ``(step_name, status, message)`` callback.
    """

    def __init__(
        self,
        engine: Any,
        config: dict[str, Any] | None = None,
        steps: list[dict[str, Any]] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self.engine = engine
        self.config = config or {}
        self.steps = steps or self.config.get("steps", [])
        self.on_progress = on_progress
        self.continue_on_error = bool(self.config.get("continue_on_error", False))
        self.recover_persisted_state = bool(
            self.config.get("recover_persisted_state", True)
        )
        self.timeout_seconds = float(self.config.get("timeout_seconds", 60))
        self.sequence = StartupSequence(name="runtime-startup")

    # ── Main entry ─────────────────────────────────────────────────

    def run(self) -> StartupSequence:
        """Execute every step in order. Returns the StartupSequence."""
        logger.info("Starting runtime startup sequence (%d steps)", len(self.steps))
        for definition in self.steps:
            step = self._run_step(definition)
            self.sequence.steps.append(step)
            if step.status is StartupStepStatus.FAILED and not self.continue_on_error:
                self.sequence.completed_at = _utcnow()
                raise StartupError(
                    f"Startup failed at step '{step.name}': {step.error}"
                )
        self.sequence.completed_at = _utcnow()
        self.sequence.success = self.sequence.failed_steps == 0
        return self.sequence

    # ── Step execution ─────────────────────────────────────────────

    def _run_step(self, definition: dict[str, Any]) -> StartupStep:
        name = str(definition.get("name", "unnamed"))
        target = definition.get("target")
        step = StartupStep(
            name=name,
            description=str(definition.get("description", "")),
            status=StartupStepStatus.RUNNING,
            started_at=_utcnow(),
        )
        self._notify(step, "started")
        started = time.monotonic()
        try:
            if target in _INTERNAL_TARGETS:
                step.reused = False
                self._run_internal(target, step, definition)
            else:
                step.reused = self._run_class_step(definition, step)
        except Exception as exc:
            step.status = StartupStepStatus.FAILED
            step.error = str(exc)
            step.completed_at = _utcnow()
            step.duration_ms = round((time.monotonic() - started) * 1000, 2)
            logger.error("Startup step %s failed: %s", name, exc)
            self._notify(step, "failed")
            return step
        step.status = StartupStepStatus.COMPLETED
        step.completed_at = _utcnow()
        step.duration_ms = round((time.monotonic() - started) * 1000, 2)
        self._notify(step, "completed")
        return step

    def _notify(self, step: StartupStep, message: str) -> None:
        if self.on_progress is not None:
            try:
                self.on_progress(step.name, step.status, message)
            except Exception as exc:
                logger.warning("Startup progress callback error: %s", exc)

    # ── Internal targets ───────────────────────────────────────────

    def _run_internal(
        self,
        target: str,
        step: StartupStep,
        definition: dict[str, Any],
    ) -> None:
        if target == "load_constitution":
            self._load_constitution()
        elif target == "load_project_state":
            self._load_project_state()
        elif target == "load_configuration":
            self._load_configuration()
        elif target == "start_runtime":
            self._start_runtime()
        elif target == "ready":
            self._ready()

    def _load_constitution(self) -> None:
        config_dir = Path(getattr(self.engine, "config_dir", "config"))
        company_dir = config_dir / "company"
        constitution: dict[str, dict[str, Any]] = {}
        if company_dir.is_dir():
            for path in sorted(company_dir.glob("*.yaml")):
                data = load_yaml(path)
                if data is not None:
                    constitution[path.stem] = data
        else:
            logger.info("No config/company directory — constitution stays empty")
        self.engine.constitution = constitution
        logger.info("Constitution loaded: %d sections", len(constitution))

    def _load_project_state(self) -> None:
        state_store = getattr(self.engine, "state_store", None)
        if state_store is None:
            logger.warning("No state store — skipping state recovery")
            return
        if not self.recover_persisted_state:
            logger.info("State recovery disabled by config")
            return
        recovered = state_store.load()
        if recovered is None:
            logger.warning("No persisted state to recover — starting fresh")
            return
        logger.info(
            "State recovered: phase=%s active_workflows=%d",
            recovered.phase.value,
            len(recovered.active_workflows),
        )
        self._publish(
            "runtime.state_recovered",
            {
                "phase": recovered.phase.value,
                "active_workflows": len(recovered.active_workflows),
            },
        )

    def _load_configuration(self) -> None:
        runtime_config = getattr(self.engine, "runtime_config", None)
        if runtime_config is None:
            logger.warning("No runtime_config — configuration load skipped")
            return
        sections = (
            runtime_config.to_dict() if hasattr(runtime_config, "to_dict") else {}
        )
        logger.info("Runtime configuration loaded (%d sections)", len(sections))

    def _start_runtime(self) -> None:
        start_workers = getattr(self.engine, "start_workers", None)
        if callable(start_workers):
            start_workers()
        else:
            logger.warning("Engine has no start_workers() — workers not started")

    def _ready(self) -> None:
        mark_ready = getattr(self.engine, "mark_ready", None)
        if callable(mark_ready):
            mark_ready()
        else:
            lifecycle = getattr(self.engine, "lifecycle", None)
            if lifecycle is not None and hasattr(lifecycle, "transition"):
                lifecycle.transition(RuntimePhase.RUNNING)

    # ── Class steps ────────────────────────────────────────────────

    def _run_class_step(self, definition: dict[str, Any], step: StartupStep) -> bool:
        module_name = definition.get("module")
        class_name = definition.get("class")
        engine_name = definition.get("engine") or self._default_engine_name(step.name)
        params = definition.get("params") or {}
        if not module_name or not class_name:
            raise StartupError(
                f"Step '{step.name}' is neither an internal target nor a "
                "class step (module/class required)"
            )
        registered = getattr(self.engine, "engines", {})
        existing = registered.get(engine_name) if isinstance(registered, dict) else None
        if existing is not None:
            logger.info(
                "Engine %s already registered — reusing (step %s)",
                engine_name,
                step.name,
            )
            return True
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        resolved = self._resolve_params(params)
        instance = cls(**resolved)
        register = getattr(self.engine, "register_engine", None)
        if callable(register):
            register(engine_name, instance)
        else:
            logger.warning(
                "Engine has no register_engine — %s not registered", engine_name
            )
        return False

    @staticmethod
    def _default_engine_name(step_name: str) -> str:
        return step_name.removeprefix("initialize_") or step_name

    def _resolve_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Resolve ``@``-prefixed parameter values against the engine."""
        resolved: dict[str, Any] = {}
        for key, value in params.items():
            resolved[key] = self._resolve_value(value)
        return resolved

    def _resolve_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self._resolve_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_value(v) for v in value]
        if not isinstance(value, str) or not value.startswith("@"):
            return value
        marker, _, rest = value.partition(":")
        if marker == "@engine":
            return self._lookup_engine(rest)
        if marker == "@config":
            return self._lookup_config(rest)
        if marker == "@state_dir":
            state_store = getattr(self.engine, "state_store", None)
            if state_store is not None:
                return str(state_store.state_dir)
            return str(getattr(self.engine, "state_dir", "runtime"))
        if marker == "@event_bus":
            return getattr(self.engine, "event_bus", None)
        if marker == "@runtime_config":
            return getattr(self.engine, "runtime_config", None)
        if marker == "@runtime":
            return self.engine
        return value

    def _lookup_engine(self, name: str) -> Any:
        registered = getattr(self.engine, "engines", {})
        if isinstance(registered, dict) and name in registered:
            return registered[name]
        raise StartupError(f"Referenced engine not registered: {name}")

    def _lookup_config(self, name: str) -> dict[str, Any]:
        runtime_config = getattr(self.engine, "runtime_config", None)
        if runtime_config is None or not hasattr(runtime_config, "section"):
            return {}
        return runtime_config.section(name) or {}

    # ── Helpers ────────────────────────────────────────────────────

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event_bus = getattr(self.engine, "event_bus", None)
        publish_runtime_event(event_bus, event_type, payload, source="runtime.startup")
