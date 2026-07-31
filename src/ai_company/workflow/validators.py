"""Validators for workflow definitions and execution."""

from __future__ import annotations

import logging
import re
from typing import Any

from ai_company.workflow.models import (
    WorkflowContext,
    WorkflowDefinition,
    WorkflowState,
    WorkflowStateType,
    WorkflowTerminalStatus,
)

logger = logging.getLogger(__name__)


class WorkflowValidator:
    """Validates workflow definitions for correctness."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate_definition(self, definition: WorkflowDefinition) -> bool:
        """Validate a complete workflow definition."""
        self.errors = []
        self.warnings = []

        # Required fields
        self._validate_required_fields(definition)
        # States
        self._validate_states(definition)
        # Data schema
        self._validate_data_schema(definition)
        # Config
        self._validate_config(definition)

        return len(self.errors) == 0

    def _validate_required_fields(self, definition: WorkflowDefinition) -> None:
        if not definition.name:
            self.errors.append("Workflow missing name")
        if not definition.display_name:
            self.warnings.append("Workflow missing display_name")
        if not definition.version:
            self.warnings.append("Workflow missing version")
        if not definition.initial_state:
            self.errors.append("Workflow missing initial_state")

    def _validate_states(self, definition: WorkflowDefinition) -> None:
        if not definition.states:
            self.errors.append("No states defined")
            return

        # Initial state exists
        if definition.initial_state not in definition.states:
            self.errors.append(
                f"Initial state '{definition.initial_state}' not in states"
            )

        # At least one terminal state
        terminal_states = [
            s
            for s in definition.states.values()
            if s.type == WorkflowStateType.TERMINAL
        ]
        if not terminal_states:
            self.errors.append("No terminal states defined")

        # Validate each state
        for state_id, state in definition.states.items():
            self._validate_state(state_id, state, definition)

    def _validate_state(
        self,
        state_id: str,
        state: WorkflowState,
        definition: WorkflowDefinition,
    ) -> None:
        # State ID format
        if not re.match(r"^[a-z_][a-z0-9_]*$", state_id):
            self.warnings.append(
                f"State ID '{state_id}' should be lowercase with underscores"
            )

        # Terminal states need terminal_status
        if state.type == WorkflowStateType.TERMINAL:
            if not state.terminal_status:
                self.errors.append(
                    f"Terminal state '{state_id}' missing terminal_status"
                )
            elif state.terminal_status not in [
                WorkflowTerminalStatus.SUCCESS,
                WorkflowTerminalStatus.REJECTED,
                WorkflowTerminalStatus.CANCELLED,
                WorkflowTerminalStatus.FAILED,
            ]:
                self.warnings.append(
                    f"Terminal state '{state_id}' has unusual terminal_status"
                )

        # Approval states need approval config
        if state.type == WorkflowStateType.APPROVAL:
            if not state.approval:
                self.errors.append(
                    f"Approval state '{state_id}' missing approval config"
                )
            else:
                if state.approval.required and not state.approval.approver_role:
                    self.errors.append(
                        f"Approval state '{state_id}' requires approval but no approver_role"
                    )

        # Action states need action config
        if state.type == WorkflowStateType.ACTION:
            if not state.action:
                self.errors.append(f"Action state '{state_id}' missing action config")
            elif not state.action.handler:
                self.warnings.append(f"Action state '{state_id}' missing handler")

        # Wait states need wait config
        if state.type == WorkflowStateType.WAIT:
            if not state.wait:
                self.errors.append(f"Wait state '{state_id}' missing wait config")
            elif not state.wait.wait_for:
                self.errors.append(f"Wait state '{state_id}' missing wait_for field")

        # Validate transitions
        for transition in state.transitions:
            if transition.to not in definition.states:
                self.errors.append(
                    f"State '{state_id}' transition to unknown state '{transition.to}'"
                )

    def _validate_data_schema(self, definition: WorkflowDefinition) -> None:
        if not definition.data_schema:
            self.warnings.append("No data schema defined")
            return

        for field_name, field_schema in definition.data_schema.items():
            if not isinstance(field_schema, dict):
                self.warnings.append(f"Field '{field_name}' schema should be a dict")
                continue

            if "type" not in field_schema:
                self.warnings.append(f"Field '{field_name}' missing type")

            valid_types = [
                "string",
                "number",
                "integer",
                "boolean",
                "array",
                "object",
                "date",
                "datetime",
            ]
            if field_schema.get("type") not in valid_types:
                self.warnings.append(
                    f"Field '{field_name}' has unknown type: {field_schema.get('type')}"
                )

    def _validate_config(self, definition: WorkflowDefinition) -> None:
        if not definition.config:
            return

        config = definition.config
        if config.timeout_hours is not None and config.timeout_hours <= 0:
            self.warnings.append("timeout_hours should be positive")

        if config.retry_policy:
            if config.retry_policy["max_retries"] < 0:
                self.warnings.append("max_retries should be non-negative")
            if config.retry_policy["backoff_seconds"] < 0:
                self.warnings.append("backoff_seconds should be non-negative")

    def get_report(self) -> dict[str, Any]:
        return {
            "valid": len(self.errors) == 0,
            "errors": self.errors,
            "warnings": self.warnings,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }


class ExecutionValidator:
    """Validates workflow execution state."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate_context(
        self,
        context: WorkflowContext,
        definition: WorkflowDefinition,
    ) -> bool:
        """Validate execution context against definition."""
        self.errors = []
        self.warnings = []

        # Check current state exists
        if context.current_state not in definition.states:
            self.errors.append(
                f"Current state '{context.current_state}' not in workflow definition"
            )

        # Check data schema compliance
        if definition.data_schema:
            self._validate_data(context.data, definition.data_schema)

        return len(self.errors) == 0

    def _validate_data(
        self,
        data: dict[str, Any],
        schema: dict[str, Any],
    ) -> None:
        for field_name, field_schema in schema.items():
            required = field_schema.get("required", False)
            field_type = field_schema.get("type")

            if required and field_name not in data:
                self.errors.append(f"Required field missing: {field_name}")
                continue

            if field_name not in data:
                continue

            value = data[field_name]

            if field_type == "string" and not isinstance(value, str):
                self.errors.append(f"Field '{field_name}' should be string")
            elif field_type in ("number", "integer") and not isinstance(
                value, (int, float)
            ):
                self.errors.append(f"Field '{field_name}' should be number")
            elif field_type == "boolean" and not isinstance(value, bool):
                self.errors.append(f"Field '{field_name}' should be boolean")
            elif field_type == "array" and not isinstance(value, list):
                self.errors.append(f"Field '{field_name}' should be array")

            # Enum validation
            if "enum" in field_schema:
                if value not in field_schema["enum"]:
                    self.errors.append(
                        f"Field '{field_name}' value '{value}' not in enum: {field_schema['enum']}"
                    )

    def get_report(self) -> dict[str, Any]:
        return {
            "valid": len(self.errors) == 0,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_workflow_yaml(yaml_content: str) -> dict[str, Any]:
    """Validate workflow YAML content."""
    import yaml

    from ai_company.workflow.models import WorkflowDefinition

    try:
        data = yaml.safe_load(yaml_content)
        if not data:
            return {"valid": False, "errors": ["Empty YAML"]}

        if "workflow" in data:
            data = data["workflow"]

        definition = WorkflowDefinition(**data)
        validator = WorkflowValidator()
        validator.validate_definition(definition)
        report = validator.get_report()
        report["definition"] = definition
        return report
    except Exception as e:
        return {"valid": False, "errors": [str(e)]}
