"""Transition validation and utilities for workflow state transitions."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ai_company.workflow.models import (
    WorkflowDefinition,
    WorkflowState,
    WorkflowStateType,
    Transition,
    WorkflowContext,
)

logger = logging.getLogger(__name__)


class TransitionValidator:
    """Validates workflow transitions and ensures state machine integrity."""

    def __init__(self, definition: WorkflowDefinition):
        self.definition = definition
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate(self) -> bool:
        """Run all validations, return True if valid."""
        self.errors = []
        self.warnings = []

        self._validate_states()
        self._validate_transitions()
        self._validate_initial_state()
        self._validate_terminal_states()
        self._validate_approval_states()
        self._validate_action_states()
        self._validate_wait_states()
        self._check_reachability()
        self._check_deadlocks()

        return len(self.errors) == 0

    def _validate_states(self) -> None:
        """Validate all states exist and have required fields."""
        for state_id, state in self.definition.states.items():
            if not state.name:
                self.warnings.append(f"State '{state_id}' missing display name")

    def _validate_transitions(self) -> None:
        """Validate all transitions reference valid states."""
        for state_id, state in self.definition.states.items():
            for transition in state.transitions:
                if transition.to not in self.definition.states:
                    self.errors.append(
                        f"Transition from '{state_id}' references unknown state '{transition.to}'"
                    )

                # Validate condition syntax
                if transition.condition and transition.condition != "auto":
                    if not self._is_valid_condition(transition.condition):
                        self.warnings.append(
                            f"Transition '{state_id}' -> '{transition.to}' has complex condition: "
                            f"'{transition.condition}'"
                        )

    def _is_valid_condition(self, condition: str) -> bool:
        """Check if a condition is syntactically valid (basic check)."""
        try:
            compile(condition, "<condition>", "eval")
            return True
        except SyntaxError:
            return False

    def _validate_initial_state(self) -> None:
        """Validate initial state exists."""
        if self.definition.initial_state not in self.definition.states:
            self.errors.append(
                f"Initial state '{self.definition.initial_state}' not found in states"
            )

    def _validate_terminal_states(self) -> None:
        """Validate at least one terminal state exists."""
        terminal_states = [
            s
            for s in self.definition.states.values()
            if s.type == WorkflowStateType.TERMINAL
        ]
        if not terminal_states:
            self.errors.append("No terminal states defined")
        elif len(terminal_states) == 1:
            self.warnings.append("Only one terminal state defined")

    def _validate_approval_states(self) -> None:
        """Validate approval states have proper configuration."""
        for state_id, state in self.definition.states.items():
            if state.type == WorkflowStateType.APPROVAL:
                if not state.approval:
                    self.errors.append(
                        f"Approval state '{state_id}' missing approval config"
                    )
                else:
                    if not state.approval.required:
                        self.warnings.append(
                            f"Approval state '{state_id}' has required=false"
                        )
                    if not state.approval.approver_role:
                        self.warnings.append(
                            f"Approval state '{state_id}' missing approver_role"
                        )

    def _validate_action_states(self) -> None:
        """Validate action states have action configuration."""
        for state_id, state in self.definition.states.items():
            if state.type == WorkflowStateType.ACTION:
                if not state.action:
                    self.errors.append(
                        f"Action state '{state_id}' missing action config"
                    )
                elif not state.action.handler:
                    self.warnings.append(f"Action state '{state_id}' missing handler")

    def _validate_wait_states(self) -> None:
        """Validate wait states have wait configuration."""
        for state_id, state in self.definition.states.items():
            if state.type == WorkflowStateType.WAIT:
                if not state.wait:
                    self.errors.append(f"Wait state '{state_id}' missing wait config")
                elif not state.wait.wait_for:
                    self.warnings.append(f"Wait state '{state_id}' missing wait_for")

    def _check_reachability(self) -> None:
        """Check that all states are reachable from initial state."""
        reachable = self._get_reachable_states()
        all_states = set(self.definition.states.keys())
        unreachable = all_states - reachable

        for state_id in unreachable:
            if state_id != self.definition.initial_state:
                self.warnings.append(
                    f"State '{state_id}' is unreachable from initial state"
                )

    def _get_reachable_states(self) -> set[str]:
        """Get all states reachable from initial state via transitions."""
        reachable = {self.definition.initial_state}
        changed = True

        while changed:
            changed = False
            for state_id in list(reachable):
                if state_id in self.definition.states:
                    state = self.definition.states[state_id]
                    for transition in state.transitions:
                        if transition.to not in reachable:
                            reachable.add(transition.to)
                            changed = True
        return reachable

    def _check_deadlocks(self) -> None:
        """Check for potential deadlocks (states with no outgoing transitions)."""
        for state_id, state in self.definition.states.items():
            if state.type != WorkflowStateType.TERMINAL:
                if not state.transitions:
                    self.errors.append(
                        f"Non-terminal state '{state_id}' has no outgoing transitions"
                    )

    def get_validation_report(self) -> Dict[str, Any]:
        """Get a full validation report."""
        return {
            "valid": len(self.errors) == 0,
            "errors": self.errors,
            "warnings": self.warnings,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }


class TransitionEvaluator:
    """Evaluates transition conditions against workflow context."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def evaluate(
        self,
        condition: str,
        context: WorkflowContext,
        additional_vars: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Evaluate a transition condition."""
        if not condition or condition == "auto":
            return True

        # Build evaluation context
        eval_context: dict[str, Any] = {
            **context.data,
            "state": context.current_state,
            "previous_state": context.previous_state or "",
            "execution_id": context.execution_id,
        }

        if additional_vars:
            eval_context.update(additional_vars)

        try:
            # Use safe evaluation - only allow basic operations
            result = eval(condition, {"__builtins__": {}}, eval_context)
            return bool(result)
        except Exception as e:
            self.logger.warning(f"Condition evaluation failed: {condition}, error: {e}")
            return False

    def evaluate_transitions(
        self,
        state: WorkflowState,
        context: WorkflowContext,
    ) -> List[Transition]:
        """Evaluate all transitions from a state, return matching ones."""
        matching = []
        for transition in state.transitions:
            if self.evaluate(transition.condition, context):
                matching.append(transition)
        return matching


def validate_workflow_definition(definition: WorkflowDefinition) -> Dict[str, Any]:
    """Validate a workflow definition and return report."""
    validator = TransitionValidator(definition)
    validator.validate()
    return validator.get_validation_report()


def create_transition(
    to: str,
    condition: str = "auto",
    action: Optional[str] = None,
    description: Optional[str] = None,
) -> Transition:
    """Factory function to create a transition."""
    return Transition(
        to=to,
        condition=condition,
        action=action,
        description=description,
    )
