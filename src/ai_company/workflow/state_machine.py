"""State machine for workflow execution."""

from __future__ import annotations

import logging
from typing import Any

from ai_company.workflow.models import (
    ApprovalConfig,
    WorkflowContext,
    WorkflowDefinition,
    WorkflowState,
    WorkflowStateType,
)

logger = logging.getLogger(__name__)


class TransitionResult:
    """Result of a state transition evaluation."""

    def __init__(
        self,
        success: bool,
        next_state: str | None = None,
        error: str | None = None,
        approval_required: bool = False,
        approval_config: ApprovalConfig | None = None,
        action_required: bool = False,
        action_config: dict[str, Any] | None = None,
        wait_required: bool = False,
        wait_config: dict[str, Any] | None = None,
    ):
        self.success = success
        self.next_state = next_state
        self.error = error
        self.approval_required = approval_required
        self.approval_config = approval_config
        self.action_required = action_required
        self.action_config = action_config
        self.wait_required = wait_required
        self.wait_config = wait_config


class StateMachine:
    """State machine for workflow execution."""

    def __init__(self, definition: WorkflowDefinition):
        self.definition = definition
        self._validate_definition()

    def _validate_definition(self) -> None:
        """Validate the workflow definition."""
        # Check initial state exists
        if self.definition.initial_state not in self.definition.states:
            raise ValueError(
                f"Initial state '{self.definition.initial_state}' not found in states"
            )

        # Check all transitions reference valid states
        for state_id, state in self.definition.states.items():
            for transition in state.transitions:
                if transition.to not in self.definition.states:
                    raise ValueError(
                        f"Transition from '{state_id}' to unknown state '{transition.to}'"
                    )

    def get_initial_state(self) -> WorkflowState:
        """Get the initial state."""
        return self.definition.states[self.definition.initial_state]

    def get_state(self, state_id: str) -> WorkflowState:
        """Get a state by ID."""
        if state_id not in self.definition.states:
            raise KeyError(f"State not found: {state_id}")
        return self.definition.states[state_id]

    def evaluate_transitions(
        self,
        current_state_id: str,
        context: WorkflowContext,
    ) -> TransitionResult:
        """Evaluate transitions from the current state."""
        current_state = self.get_state(current_state_id)

        # Handle terminal states
        if current_state.type == WorkflowStateType.TERMINAL:
            return TransitionResult(
                success=True,
                next_state=None,
                error="Workflow is in terminal state",
            )

        # Evaluate each transition in order
        for transition in current_state.transitions:
            if self._evaluate_condition(transition.condition, context):
                next_state = self.get_state(transition.to)

                # Check what the next state requires
                if next_state.type == WorkflowStateType.APPROVAL:
                    if not next_state.approval:
                        return TransitionResult(
                            success=False,
                            error=f"Approval state '{transition.to}' missing approval config",
                        )
                    return TransitionResult(
                        success=True,
                        next_state=transition.to,
                        approval_required=True,
                        approval_config=next_state.approval,
                    )
                elif next_state.type == WorkflowStateType.ACTION:
                    if not next_state.action:
                        return TransitionResult(
                            success=False,
                            error=f"Action state '{transition.to}' missing action config",
                        )
                    return TransitionResult(
                        success=True,
                        next_state=transition.to,
                        action_required=True,
                        action_config={
                            "type": next_state.action.type,
                            "handler": next_state.action.handler,
                            "parameters": next_state.action.parameters,
                            "timeout_seconds": next_state.action.timeout_seconds,
                        },
                    )
                elif next_state.type == WorkflowStateType.WAIT:
                    if not next_state.wait:
                        return TransitionResult(
                            success=False,
                            error=f"Wait state '{transition.to}' missing wait config",
                        )
                    return TransitionResult(
                        success=True,
                        next_state=transition.to,
                        wait_required=True,
                        wait_config={
                            "wait_for": next_state.wait.wait_for,
                            "timeout_hours": next_state.wait.timeout_hours,
                            "polling_interval_seconds": next_state.wait.polling_interval_seconds,
                        },
                    )
                elif next_state.type == WorkflowStateType.TERMINAL:
                    return TransitionResult(
                        success=True,
                        next_state=transition.to,
                    )
                else:
                    # Initial or other state - just transition
                    return TransitionResult(
                        success=True,
                        next_state=transition.to,
                    )

        return TransitionResult(
            success=False,
            error=f"No valid transition from state '{current_state_id}'",
        )

    def _evaluate_condition(self, condition: str, context: WorkflowContext) -> bool:
        """Evaluate a transition condition against the workflow context."""
        if not condition or condition == "auto":
            return True

        # Simple condition evaluation
        # For complex conditions, use a safe expression evaluator
        try:
            # Replace context references
            eval_context = {
                **context.data,
                "auto": True,
            }
            return bool(eval(condition, {"__builtins__": {}}, eval_context))
        except Exception as e:
            logger.warning(f"Condition evaluation failed: {condition}, error: {e}")
            return False

    def get_valid_transitions(self, state_id: str) -> list[str]:
        """Get all valid transition target states from a state."""
        state = self.get_state(state_id)
        return [t.to for t in state.transitions]

    def is_terminal_state(self, state_id: str) -> bool:
        """Check if a state is terminal."""
        state = self.get_state(state_id)
        return state.type == WorkflowStateType.TERMINAL

    def get_terminal_status(self, state_id: str) -> str | None:
        """Get the terminal status of a terminal state."""
        state = self.get_state(state_id)
        if state.type == WorkflowStateType.TERMINAL and state.terminal_status:
            return state.terminal_status.value
        return None

    def can_transition(self, from_state: str, to_state: str) -> bool:
        """Check if a direct transition is possible."""
        state = self.get_state(from_state)
        return any(t.to == to_state for t in state.transitions)

    def get_all_states(self) -> dict[str, WorkflowState]:
        """Get all states in the workflow."""
        return self.definition.states.copy()

    def get_state_type(self, state_id: str) -> WorkflowStateType:
        """Get the type of a state."""
        return self.get_state(state_id).type
