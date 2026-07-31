"""Checkpoint management for pipeline recovery.

Checkpoints are durable snapshots of execution state taken after task
and stage completion. They are kept in memory, optionally mirrored to
the Memory Engine and/or JSON files on disk, and are the primary input
to the recovery flow.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ai_company.orchestration.exceptions import CheckpointError
from ai_company.orchestration.models import (
    Checkpoint,
    ExecutionState,
    OrchestrationPlan,
)

logger = logging.getLogger(__name__)

_MEMORY_TAG = "orchestration"
_MEMORY_KIND = "orchestration_checkpoint"


def _sort_key(checkpoint: Checkpoint) -> tuple[Any, int, int]:
    """Deterministic ordering: created_at, then stage/task index."""
    return (checkpoint.created_at, checkpoint.stage_index, checkpoint.task_index)


class CheckpointManager:
    """Creates, stores, and restores pipeline checkpoints.

    Args:
        config: Checkpoint config (see config/orchestration/checkpoints.yaml).
        memory_engine: Optional Memory Engine for durable persistence.
        disk_path: Directory for JSON checkpoints when disk persistence
            is enabled.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        memory_engine: Any | None = None,
        disk_path: str | Path | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config or {}
        self.memory_engine = memory_engine
        self.disk_path = Path(disk_path or self.config.get("disk_path", "checkpoints"))
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._checkpoints: dict[str, Checkpoint] = {}

    # ── Creation ──────────────────────────────────────────────────

    def create(
        self,
        plan: OrchestrationPlan,
        state: ExecutionState,
        stage_index: int = 0,
        task_index: int = 0,
        context: dict[str, Any] | None = None,
    ) -> Checkpoint:
        """Snapshot the current execution state as a checkpoint.

        Raises:
            CheckpointError: If the checkpoint cannot be built.
        """
        try:
            checkpoint = Checkpoint(
                pipeline_id=plan.pipeline.id,
                plan_id=plan.id,
                state=state.model_copy(deep=True),
                stage_index=stage_index,
                task_index=task_index,
                context={k: v for k, v in (context or {}).items() if k != "plan"},
                metadata={"pipeline": plan.pipeline.name},
            )
        except Exception as exc:
            raise CheckpointError(f"Checkpoint build failed: {exc}") from exc

        self._checkpoints[checkpoint.id] = checkpoint
        self._enforce_cap(plan.pipeline.id)
        self._persist(checkpoint)
        self.logger.info(
            "Checkpoint %s created for plan %s (stage %d)",
            checkpoint.id,
            plan.id,
            stage_index,
        )
        return checkpoint

    # ── Lookup ────────────────────────────────────────────────────

    def restore(self, checkpoint_id: str) -> Checkpoint | None:
        """Return a checkpoint by id (memory-persisted included)."""
        checkpoint = self._checkpoints.get(checkpoint_id)
        if checkpoint is not None:
            return checkpoint
        if self.memory_engine is not None:
            try:
                entries = self.memory_engine.search(
                    metadata_filter={
                        "kind": _MEMORY_KIND,
                        "checkpoint_id": checkpoint_id,
                    },
                    limit=1,
                )
                if entries:
                    content = entries[0].content
                    restored = Checkpoint.model_validate(content["checkpoint"])
                    self._checkpoints[restored.id] = restored
                    return restored
            except Exception as exc:
                self.logger.warning(
                    "Checkpoint %s restore from memory failed: %s",
                    checkpoint_id,
                    exc,
                )
        return None

    def latest(self, pipeline_id: str) -> Checkpoint | None:
        """Return the most recent checkpoint of a pipeline."""
        matches = [
            ck for ck in self._checkpoints.values() if ck.pipeline_id == pipeline_id
        ]
        if not matches:
            return None
        return max(matches, key=_sort_key)

    def list_for(self, pipeline_id: str) -> list[Checkpoint]:
        """Return all checkpoints of a pipeline, newest first."""
        matches = [
            ck for ck in self._checkpoints.values() if ck.pipeline_id == pipeline_id
        ]
        return sorted(matches, key=_sort_key, reverse=True)

    def all(self) -> list[Checkpoint]:
        """Return all checkpoints, newest first."""
        return sorted(self._checkpoints.values(), key=_sort_key, reverse=True)

    def delete(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint."""
        return self._checkpoints.pop(checkpoint_id, None) is not None

    def clear(self, pipeline_id: str | None = None) -> int:
        """Delete checkpoints (optionally for one pipeline)."""
        if pipeline_id is None:
            count = len(self._checkpoints)
            self._checkpoints.clear()
            return count
        ids = [
            ck.id for ck in self._checkpoints.values() if ck.pipeline_id == pipeline_id
        ]
        for ck_id in ids:
            self._checkpoints.pop(ck_id, None)
        return len(ids)

    # ── Internals ─────────────────────────────────────────────────

    def _enforce_cap(self, pipeline_id: str) -> None:
        cap = int(self.config.get("max_checkpoints_per_pipeline", 10))
        if cap <= 0:
            return
        matches = [
            ck for ck in self._checkpoints.values() if ck.pipeline_id == pipeline_id
        ]
        if len(matches) > cap:
            matches.sort(key=lambda ck: ck.created_at)
            for old in matches[: len(matches) - cap]:
                self._checkpoints.pop(old.id, None)

    def _persist(self, checkpoint: Checkpoint) -> None:
        if self.config.get("persist_to_memory", True) and self.memory_engine:
            try:
                self.memory_engine.save(
                    content={
                        "kind": _MEMORY_KIND,
                        "checkpoint_id": checkpoint.id,
                        "pipeline_id": checkpoint.pipeline_id,
                        "checkpoint": checkpoint.model_dump(mode="json"),
                    },
                    memory_type="system",
                    namespace="orchestration",
                    tags=[_MEMORY_TAG, "checkpoint"],
                    source="orchestrator",
                    metadata={
                        "kind": _MEMORY_KIND,
                        "checkpoint_id": checkpoint.id,
                    },
                )
            except Exception as exc:
                self.logger.warning(
                    "Checkpoint %s memory persistence failed: %s",
                    checkpoint.id,
                    exc,
                )

        if self.config.get("persist_to_disk", False):
            try:
                self.disk_path.mkdir(parents=True, exist_ok=True)
                target = self.disk_path / f"{checkpoint.id}.json"
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(
                        checkpoint.model_dump(mode="json"),
                        f,
                        indent=2,
                    )
            except Exception as exc:
                self.logger.warning(
                    "Checkpoint %s disk persistence failed: %s",
                    checkpoint.id,
                    exc,
                )
