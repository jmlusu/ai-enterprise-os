"""Execution state management.

The :class:`ExecutionStateStore` keeps the live state of every plan run
in memory and optionally persists it to the Memory Engine so a restarted
process can resume interrupted runs. It also maintains the execution
history consumed by ``ai-company orchestrate history``.
"""

from __future__ import annotations

import logging
from typing import Any

from ai_company.orchestration.models import (
    ExecutionRecord,
    ExecutionState,
)

logger = logging.getLogger(__name__)

_MEMORY_TAG = "orchestration"
_MEMORY_KIND_STATE = "orchestration_state"
_MEMORY_KIND_RECORD = "orchestration_record"


class ExecutionStateStore:
    """In-memory + optional Memory Engine backed state store.

    Args:
        memory_engine: Optional Memory Engine for durable persistence.
        namespace: Memory namespace used for persisted entries.
        memory_type: Memory type used for persisted entries.
        persist: Whether to write to the Memory Engine.
        max_records: Cap on retained history records (0 = unlimited).
    """

    def __init__(
        self,
        memory_engine: Any | None = None,
        namespace: str = "orchestration",
        memory_type: str = "system",
        persist: bool = True,
        max_records: int = 1000,
        logger: logging.Logger | None = None,
    ) -> None:
        self.memory_engine = memory_engine
        self.namespace = namespace
        self.memory_type = memory_type
        self.persist = persist
        self.max_records = max_records
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._states: dict[str, ExecutionState] = {}
        self._records: list[ExecutionRecord] = []

    # ── State ─────────────────────────────────────────────────────

    def save_state(self, state: ExecutionState) -> ExecutionState:
        """Save a state snapshot (in-memory, optionally persisted)."""
        state.updated_at = state.updated_at
        self._states[state.plan_id] = state
        if self.persist and self.memory_engine is not None:
            self._persist_state(state)
        return state

    def get_state(self, plan_id: str) -> ExecutionState | None:
        """Get the live state for a plan, or None."""
        return self._states.get(plan_id)

    def list_states(self) -> list[ExecutionState]:
        """Return all live states, most recently updated first."""
        return sorted(
            self._states.values(),
            key=lambda s: s.updated_at,
            reverse=True,
        )

    def remove_state(self, plan_id: str) -> bool:
        """Drop the live state of a plan."""
        return self._states.pop(plan_id, None) is not None

    # ── History ───────────────────────────────────────────────────

    def record(self, record: ExecutionRecord) -> ExecutionRecord:
        """Append an execution record to history."""
        self._records.append(record)
        if self.max_records > 0 and len(self._records) > self.max_records:
            self._records = self._records[-self.max_records :]
        if self.persist and self.memory_engine is not None:
            self._persist_record(record)
        return record

    def history(self, plan_id: str | None = None) -> list[ExecutionRecord]:
        """Return execution records, newest first."""
        records = [r for r in self._records if plan_id is None or r.plan_id == plan_id]
        return sorted(records, key=lambda r: r.recorded_at, reverse=True)

    def last_record(self, plan_id: str) -> ExecutionRecord | None:
        """Return the most recent record for a plan, or None."""
        records = self.history(plan_id)
        return records[0] if records else None

    def clear(self) -> None:
        """Clear all live states and history."""
        self._states.clear()
        self._records.clear()

    # ── Memory Engine persistence ─────────────────────────────────

    def _persist_state(self, state: ExecutionState) -> None:
        try:
            self.memory_engine.save(
                content={
                    "kind": _MEMORY_KIND_STATE,
                    "plan_id": state.plan_id,
                    "state": state.model_dump(mode="json"),
                },
                memory_type=self.memory_type,
                namespace=self.namespace,
                tags=[_MEMORY_TAG, "state"],
                source="orchestrator",
                metadata={
                    "kind": _MEMORY_KIND_STATE,
                    "plan_id": state.plan_id,
                },
            )
        except Exception as exc:  # persistence failures are non-fatal
            self.logger.warning("State persistence failed: %s", exc)

    def _persist_record(self, record: ExecutionRecord) -> None:
        try:
            self.memory_engine.save(
                content={
                    "kind": _MEMORY_KIND_RECORD,
                    "plan_id": record.plan_id,
                    "record": record.model_dump(mode="json"),
                },
                memory_type=self.memory_type,
                namespace=self.namespace,
                tags=[_MEMORY_TAG, "history"],
                source="orchestrator",
                metadata={
                    "kind": _MEMORY_KIND_RECORD,
                    "plan_id": record.plan_id,
                },
            )
        except Exception as exc:  # persistence failures are non-fatal
            self.logger.warning("Record persistence failed: %s", exc)

    def load_states_from_memory(self) -> list[ExecutionState]:
        """Rebuild live states from Memory Engine entries.

        Returns:
            Reconstructed states (empty list when memory is unavailable).
        """
        if self.memory_engine is None:
            return []
        try:
            entries = self.memory_engine.search(
                namespace=self.namespace,
                metadata_filter={"kind": _MEMORY_KIND_STATE},
                limit=500,
            )
        except Exception as exc:
            self.logger.warning("State load from memory failed: %s", exc)
            return []
        states: list[ExecutionState] = []
        for entry in entries:
            try:
                states.append(ExecutionState.model_validate(entry.content["state"]))
            except Exception as exc:
                self.logger.warning(
                    "Skipping unparsable state entry %s: %s",
                    getattr(entry, "id", "?"),
                    exc,
                )
                continue
        for state in states:
            self._states[state.plan_id] = state
        return states
