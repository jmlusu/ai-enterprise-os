"""Runtime state persistence.

Persists :class:`RuntimeState` (active pipelines, workflows, decisions,
meetings, projects, agents, processes) to disk (``runtime/runtime_state.json``
by default) and optionally mirrors it into the Memory Engine under the
``global`` namespace (tagged ``runtime``) so it survives restarts and is
queryable.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_company.runtime.models import (
    EngineState,
    RuntimePhase,
    RuntimeProcess,
    RuntimeState,
)

logger = logging.getLogger(__name__)

_STATE_FILENAME = "runtime_state.json"

# MemoryNamespace values supported by the Memory Engine (runtime has no
# dedicated namespace; state records are tagged "runtime" instead).
_MEMORY_NAMESPACE = "global"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RuntimeStateStore:
    """Loads, updates, and persists runtime state.

    Args:
        config: The ``runtime`` config section dict.
        memory_engine: Optional Memory Engine for cross-restart durability.
        memory_namespace: Memory namespace for state records.
        state_dir: Override for the state directory (defaults to config).
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        memory_engine: Any | None = None,
        memory_namespace: str = _MEMORY_NAMESPACE,
        state_dir: str | Path | None = None,
    ) -> None:
        self.config = config or {}
        self.memory_engine = memory_engine
        self.memory_namespace = memory_namespace or _MEMORY_NAMESPACE
        self.state_dir = Path(state_dir or self.config.get("state_dir", "runtime"))
        self.state_file = self.state_dir / _STATE_FILENAME
        # RLock: update()/set_engine()/set_process() hold the lock and call
        # save()/load() which re-acquire it.
        self._lock = threading.RLock()
        self._state = RuntimeState()
        self._loaded = False

    @property
    def state(self) -> RuntimeState:
        """The current in-memory runtime state."""
        return self._state

    @property
    def loaded(self) -> bool:
        """Whether state was loaded from disk/memory."""
        return self._loaded

    # ── Loading ────────────────────────────────────────────────────

    def load(self) -> RuntimeState:
        """Load persisted state from disk (falling back to memory).

        Returns:
            The recovered RuntimeState (fresh defaults when nothing is
            persisted).
        """
        with self._lock:
            state = self._load_from_disk()
            if state is None and self.memory_engine is not None:
                state = self._load_from_memory()
            if state is None:
                logger.info("No persisted runtime state found — starting fresh")
                self._state = RuntimeState()
            else:
                self._state = state
            self._loaded = True
            return self._state

    def _load_from_disk(self) -> RuntimeState | None:
        if not self.state_file.exists():
            return None
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            state = RuntimeState.model_validate(data)
            logger.info("Recovered runtime state from %s", self.state_file)
            return state
        except Exception as exc:
            logger.warning("Could not recover runtime state from disk: %s", exc)
            return None

    def _load_from_memory(self) -> RuntimeState | None:
        try:
            entries = self.memory_engine.search(
                namespace=self.memory_namespace,
                memory_type="system",
                limit=5,
            )
            for entry in entries:
                metadata = dict(entry.metadata or {})
                serialized = metadata.get("runtime_state")
                if serialized:
                    return RuntimeState.model_validate_json(str(serialized))
        except Exception as exc:
            logger.warning("Could not recover runtime state from memory: %s", exc)
        return None

    # ── Persisting ─────────────────────────────────────────────────

    def save(self) -> RuntimeState:
        """Persist the current state to disk (and memory when available)."""
        with self._lock:
            self._state.last_saved_at = _utcnow()
            self.state_dir.mkdir(parents=True, exist_ok=True)
            payload = self._state.model_dump(mode="json")
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)
            self._mirror_to_memory()
            return self._state

    def _mirror_to_memory(self) -> None:
        if self.memory_engine is None:
            return
        try:
            self.memory_engine.save(
                content={
                    "phase": self._state.phase.value,
                    "started_at": self._state.started_at,
                    "active": self._state.snapshot(),
                },
                memory_type="system",
                namespace=self.memory_namespace,
                tags=["runtime", "state"],
                source="runtime",
                metadata={
                    "runtime_state": self._state.model_dump_json(),
                    "phase": self._state.phase.value,
                },
            )
        except Exception as exc:
            logger.warning("Could not mirror runtime state to memory: %s", exc)

    def clear(self) -> None:
        """Reset state to defaults and remove persisted artifacts."""
        with self._lock:
            self._state = RuntimeState()
            if self.state_file.exists():
                self.state_file.unlink(missing_ok=True)

    # ── Mutation helpers ───────────────────────────────────────────

    def update(self, **fields: Any) -> RuntimeState:
        """Update state fields and persist.

        ``active_*`` list fields can be replaced wholesale (``=``) or
        extended via ``+=`` (e.g. ``update(active_pipelines_append="p1")``
        is not supported; use :meth:`add_active` instead).
        """
        with self._lock:
            for key, value in fields.items():
                if hasattr(self._state, key):
                    setattr(self._state, key, value)
            if self.config.get("persist_state", True):
                self.save()
            return self._state

    def add_active(self, kind: str, item_id: str) -> RuntimeState:
        """Add an item to an ``active_*`` list (deduplicated)."""
        field = f"active_{kind}"
        if not hasattr(self._state, field):
            raise ValueError(f"Unknown active-entity kind: {kind!r}")
        values: list[str] = list(getattr(self._state, field))
        if item_id not in values:
            values.append(item_id)
        return self.update(**{field: values})

    def remove_active(self, kind: str, item_id: str) -> RuntimeState:
        """Remove an item from an ``active_*`` list."""
        field = f"active_{kind}"
        if not hasattr(self._state, field):
            raise ValueError(f"Unknown active-entity kind: {kind!r}")
        values: list[str] = list(getattr(self._state, field))
        if item_id in values:
            values.remove(item_id)
        return self.update(**{field: values})

    def set_phase(self, phase: RuntimePhase) -> RuntimeState:
        """Update the persisted phase and save."""
        return self.update(phase=phase)

    def set_started(self, started_at: datetime | None = None) -> RuntimeState:
        """Record the runtime start time."""
        return self.update(
            phase=RuntimePhase.RUNNING,
            started_at=started_at or _utcnow(),
            stopped_at=None,
        )

    def set_stopped(self, stopped_at: datetime | None = None) -> RuntimeState:
        """Record the runtime stop time."""
        return self.update(
            phase=RuntimePhase.STOPPED,
            stopped_at=stopped_at or _utcnow(),
        )

    def set_process(self, process: RuntimeProcess) -> RuntimeState:
        """Persist a process record."""
        with self._lock:
            self._state.processes[process.name] = process
            if self.config.get("persist_state", True):
                self.save()
            return self._state

    def remove_process(self, name: str) -> bool:
        """Remove a persisted process record."""
        with self._lock:
            existed = name in self._state.processes
            self._state.processes.pop(name, None)
            if existed and self.config.get("persist_state", True):
                self.save()
            return existed

    def set_engine(self, engine: EngineState) -> RuntimeState:
        """Persist an engine record (survives restarts)."""
        with self._lock:
            self._state.metadata.setdefault("engines", {})[engine.name] = (
                engine.to_dict()
            )
            if self.config.get("persist_state", True):
                self.save()
            return self._state

    # ── Inspection ─────────────────────────────────────────────────

    def engine_states(self) -> list[EngineState]:
        """Return persisted engine records."""
        raw = self._state.metadata.get("engines", {})
        return [EngineState.model_validate(item) for item in raw.values()]

    def active_counts(self) -> dict[str, int]:
        """Return active-entity counts keyed by kind."""
        return {
            "pipelines": len(self._state.active_pipelines),
            "workflows": len(self._state.active_workflows),
            "decisions": len(self._state.active_decisions),
            "meetings": len(self._state.active_meetings),
            "projects": len(self._state.active_projects),
            "agents": len(self._state.active_agents),
        }
