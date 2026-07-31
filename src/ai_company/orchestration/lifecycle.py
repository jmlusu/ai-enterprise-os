"""Lifecycle state machine for pipelines and tasks.

Enforces valid status transitions so a plan run cannot jump between
incompatible states (e.g. ``completed`` -> ``running``). Both task and
pipeline transitions are single-threaded in the runner: all concurrent
task outcomes are gathered before state is updated.
"""

from __future__ import annotations

from ai_company.orchestration.models import (
    PipelineStatus,
    TaskStatus,
)

# ── Task transitions ──────────────────────────────────────────────

TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {
        TaskStatus.READY,
        TaskStatus.RUNNING,
        TaskStatus.SKIPPED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.READY: {
        TaskStatus.RUNNING,
        TaskStatus.SKIPPED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.RUNNING: {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.SKIPPED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.FAILED: {
        TaskStatus.READY,  # retry / resume
        TaskStatus.CANCELLED,
    },
    TaskStatus.COMPLETED: set(),
    TaskStatus.SKIPPED: set(),
    TaskStatus.CANCELLED: set(),
}

# ── Pipeline transitions ──────────────────────────────────────────

PIPELINE_TRANSITIONS: dict[PipelineStatus, set[PipelineStatus]] = {
    PipelineStatus.PENDING: {
        PipelineStatus.SCHEDULED,
        PipelineStatus.RUNNING,
        PipelineStatus.CANCELLED,
    },
    PipelineStatus.SCHEDULED: {
        PipelineStatus.RUNNING,
        PipelineStatus.CANCELLED,
    },
    PipelineStatus.RUNNING: {
        PipelineStatus.COMPLETED,
        PipelineStatus.FAILED,
        PipelineStatus.PAUSED,
        PipelineStatus.RECOVERING,
    },
    PipelineStatus.PAUSED: {
        PipelineStatus.RUNNING,
        PipelineStatus.RECOVERING,
        PipelineStatus.CANCELLED,
    },
    PipelineStatus.RECOVERING: {
        PipelineStatus.RUNNING,
        PipelineStatus.FAILED,
        PipelineStatus.PAUSED,
    },
    PipelineStatus.FAILED: {
        PipelineStatus.RUNNING,  # retry / resume
        PipelineStatus.CANCELLED,
    },
    PipelineStatus.COMPLETED: set(),
    PipelineStatus.CANCELLED: set(),
}


def transition_task(current: TaskStatus, new: TaskStatus) -> TaskStatus:
    """Transition a task status, raising ValueError on invalid moves."""
    allowed = TASK_TRANSITIONS.get(current, set())
    if new not in allowed:
        raise ValueError(f"Invalid task transition: {current.value} -> {new.value}")
    return new


def transition_pipeline(current: PipelineStatus, new: PipelineStatus) -> PipelineStatus:
    """Transition a pipeline status, raising ValueError on invalid moves."""
    allowed = PIPELINE_TRANSITIONS.get(current, set())
    if new not in allowed:
        raise ValueError(f"Invalid pipeline transition: {current.value} -> {new.value}")
    return new


def can_transition_task(current: TaskStatus, new: TaskStatus) -> bool:
    """Return whether a task transition is legal."""
    return new in TASK_TRANSITIONS.get(current, set())


def can_transition_pipeline(current: PipelineStatus, new: PipelineStatus) -> bool:
    """Return whether a pipeline transition is legal."""
    return new in PIPELINE_TRANSITIONS.get(current, set())
