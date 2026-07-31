"""Unit tests for the runtime lifecycle state machine."""

from __future__ import annotations

import pytest

from ai_company.runtime.lifecycle import RUNTIME_TRANSITIONS, RuntimeLifecycle
from ai_company.runtime.models import (
    InvalidRuntimeTransitionError,
    RuntimePhase,
)


def test_starts_stopped() -> None:
    lifecycle = RuntimeLifecycle()
    assert lifecycle.phase is RuntimePhase.STOPPED
    assert not lifecycle.is_active()


def test_valid_startup_sequence() -> None:
    lifecycle = RuntimeLifecycle()
    assert lifecycle.transition(RuntimePhase.STARTING) is RuntimePhase.STARTING
    assert lifecycle.transition(RuntimePhase.RUNNING) is RuntimePhase.RUNNING
    assert lifecycle.is_active()


def test_full_lifecycle_circuit() -> None:
    lifecycle = RuntimeLifecycle()
    lifecycle.transition(RuntimePhase.STARTING)
    lifecycle.transition(RuntimePhase.RUNNING)
    lifecycle.transition(RuntimePhase.DEGRADED)
    lifecycle.transition(RuntimePhase.RECOVERING)
    lifecycle.transition(RuntimePhase.RUNNING)
    lifecycle.transition(RuntimePhase.STOPPING)
    assert lifecycle.transition(RuntimePhase.STOPPED) is RuntimePhase.STOPPED
    assert not lifecycle.is_active()


def test_illegal_transition_raises() -> None:
    lifecycle = RuntimeLifecycle()
    with pytest.raises(InvalidRuntimeTransitionError):
        lifecycle.transition(RuntimePhase.RUNNING)  # stopped -> running is illegal


def test_failed_from_starting() -> None:
    lifecycle = RuntimeLifecycle()
    lifecycle.transition(RuntimePhase.STARTING)
    lifecycle.transition(RuntimePhase.FAILED)
    assert lifecycle.phase is RuntimePhase.FAILED


def test_failed_can_restart() -> None:
    lifecycle = RuntimeLifecycle()
    lifecycle.transition(RuntimePhase.STARTING)
    lifecycle.transition(RuntimePhase.FAILED)
    lifecycle.transition(RuntimePhase.STARTING)
    assert lifecycle.phase is RuntimePhase.STARTING


def test_force_skips_validation() -> None:
    lifecycle = RuntimeLifecycle()
    lifecycle.force(RuntimePhase.RUNNING)
    assert lifecycle.phase is RuntimePhase.RUNNING


def test_transition_same_phase_is_noop() -> None:
    lifecycle = RuntimeLifecycle()
    assert lifecycle.transition(RuntimePhase.STOPPED) is RuntimePhase.STOPPED


def test_all_transitions_declared() -> None:
    for source, targets in RUNTIME_TRANSITIONS.items():
        for target in targets:
            lifecycle = RuntimeLifecycle(source)
            assert lifecycle.can_transition(target), f"{source} -> {target}"
            assert (
                not lifecycle.can_transition(
                    RuntimePhase.STOPPED
                    if target is not RuntimePhase.STOPPED
                    else RuntimePhase.STARTING
                )
                or target in targets
            )


def test_snapshot() -> None:
    lifecycle = RuntimeLifecycle(RuntimePhase.RUNNING)
    assert lifecycle.snapshot() == {"phase": "running"}
