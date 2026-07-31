"""Pydantic models for the Workflow Engine.

All models support validation, YAML import/export, JSON serialization, and versioning.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class WorkflowStateType(str, Enum):
    """Types of workflow states."""

    INITIAL = "initial"
    ACTION = "action"
    APPROVAL = "approval"
    WAIT = "wait"
    TERMINAL = "terminal"


class WorkflowTerminalStatus(str, Enum):
    """Terminal status values."""

    SUCCESS = "success"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    FAILED = "failed"


class WorkflowCategory(str, Enum):
    """Workflow categories."""

    HR = "hr"
    FINANCIAL = "financial"
    PROJECT = "project"
    OPERATIONAL = "operational"
    GOVERNANCE = "governance"
    STRATEGY = "strategy"
    SECURITY = "security"
    COMPLIANCE = "compliance"


class WorkflowStatus(str, Enum):
    """Workflow execution status."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_EXTERNAL = "waiting_external"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class ApprovalStatus(str, Enum):
    """Approval decision status."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    TIMED_OUT = "timed_out"


class TransitionConditionType(str, Enum):
    """Types of transition conditions."""

    AUTO = "auto"
    CONDITION = "condition"
    APPROVAL = "approval"
    TIMEOUT = "timeout"


class Transition(BaseModel):
    """A transition between workflow states."""

    to: str = Field(..., description="Target state ID")
    condition: str = Field(default="auto", description="Condition for transition")
    condition_type: TransitionConditionType = Field(
        default=TransitionConditionType.AUTO, description="Type of condition"
    )
    action: str | None = Field(None, description="Action to execute on transition")
    description: str | None = Field(None, description="Transition description")

    model_config = {"extra": "forbid"}


class ApprovalConfig(BaseModel):
    """Configuration for approval steps."""

    required: bool = Field(default=True, description="Whether approval is required")
    approver_role: str | None = Field(None, description="Role of approver")
    escalation_role: str | None = Field(None, description="Escalation role")
    decision_engine_integration: bool = Field(
        default=False, description="Use Decision Engine for approval"
    )
    approval_matrix: str | None = Field(None, description="Approval matrix key")
    context_fields: list[str] = Field(
        default_factory=list, description="Context fields to pass to Decision Engine"
    )
    escalation_level: int = Field(default=0, description="Escalation level")
    timeout_hours: int = Field(default=48, description="Approval timeout in hours")
    minimum_approvers: int = Field(default=1, description="Minimum approvers required")
    board_approval_required: bool = Field(
        default=False, description="Board approval needed"
    )

    model_config = {"extra": "forbid"}


class ActionConfig(BaseModel):
    """Configuration for action steps."""

    type: str = Field(..., description="Action type identifier")
    handler: str = Field(..., description="Handler function name")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Action parameters"
    )
    timeout_seconds: int = Field(default=300, description="Action timeout")

    model_config = {"extra": "forbid"}


class WaitConfig(BaseModel):
    """Configuration for wait states."""

    wait_for: str = Field(..., description="Event or condition to wait for")
    timeout_hours: int = Field(default=24, description="Wait timeout in hours")
    polling_interval_seconds: int = Field(default=60, description="Polling interval")

    model_config = {"extra": "forbid"}


class WorkflowState(BaseModel):
    """A single state in a workflow."""

    id: str = Field(..., description="Unique state identifier")
    name: str = Field(..., description="Human-readable state name")
    description: str = Field(default="", description="State description")
    type: WorkflowStateType = Field(..., description="State type")
    transitions: list[Transition] = Field(
        default_factory=list, description="Possible transitions from this state"
    )
    approval: ApprovalConfig | None = Field(
        None, description="Approval configuration (for approval states)"
    )
    action: ActionConfig | None = Field(
        None, description="Action configuration (for action states)"
    )
    wait: WaitConfig | None = Field(
        None, description="Wait configuration (for wait states)"
    )
    terminal_status: WorkflowTerminalStatus | None = Field(
        None, description="Terminal status (for terminal states)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional state metadata"
    )

    @model_validator(mode="after")
    def validate_state(self) -> WorkflowState:
        """Validate state configuration matches its type."""
        if self.type == WorkflowStateType.APPROVAL and not self.approval:
            raise ValueError("Approval state must have approval configuration")
        if self.type == WorkflowStateType.ACTION and not self.action:
            raise ValueError("Action state must have action configuration")
        if self.type == WorkflowStateType.WAIT and not self.wait:
            raise ValueError("Wait state must have wait configuration")
        if self.type == WorkflowStateType.TERMINAL and not self.terminal_status:
            raise ValueError("Terminal state must have terminal_status")
        return self

    model_config = {"extra": "forbid"}


class WorkflowConfig(BaseModel):
    """Workflow runtime configuration."""

    timeout_hours: int = Field(default=168, description="Default workflow timeout")
    retry_policy: dict[str, Any] = Field(
        default_factory=lambda: {"max_retries": 3, "backoff_seconds": 300}
    )
    notifications: dict[str, bool] = Field(
        default_factory=lambda: {
            "on_start": True,
            "on_complete": True,
            "on_failure": True,
            "on_approval_required": True,
        }
    )
    priority_based_routing: bool = Field(default=False)

    model_config = {"extra": "forbid"}


class DataSchemaField(BaseModel):
    """A field in the workflow data schema."""

    type: str = Field(..., description="Field type")
    required: bool = Field(default=False, description="Whether field is required")
    description: str = Field(default="", description="Field description")
    default: Any = Field(None, description="Default value")
    minimum: float | None = Field(None, description="Minimum value (numbers)")
    maximum: float | None = Field(None, description="Maximum value (numbers)")
    enum: list[str] | None = Field(None, description="Allowed values (strings)")
    format: str | None = Field(None, description="Format string (dates, etc.)")
    items: DataSchemaField | None = Field(None, description="Array item schema")

    model_config = {"extra": "forbid"}


class WorkflowDefinition(BaseModel):
    """Complete workflow definition."""

    version: str = Field(default="1.0", description="Workflow version")
    name: str = Field(..., description="Unique workflow identifier")
    display_name: str = Field(..., description="Human-readable name")
    description: str = Field(default="", description="Workflow description")
    category: WorkflowCategory = Field(default=WorkflowCategory.OPERATIONAL)
    tags: list[str] = Field(default_factory=list, description="Workflow tags")
    enabled: bool = Field(default=True, description="Whether workflow is enabled")
    config: WorkflowConfig = Field(default_factory=WorkflowConfig)
    states: dict[str, WorkflowState] = Field(..., description="Workflow states")
    data_schema: dict[str, DataSchemaField] = Field(
        default_factory=dict, description="Data validation schema"
    )
    initial_state: str = Field(..., description="Initial state ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def validate_workflow(self) -> WorkflowDefinition:
        """Validate workflow definition consistency."""
        if self.initial_state not in self.states:
            raise ValueError(
                f"Initial state '{self.initial_state}' not found in states"
            )

        # Validate all transitions reference valid states
        for state_id, state in self.states.items():
            for transition in state.transitions:
                if transition.to not in self.states:
                    raise ValueError(
                        f"State '{state_id}' references unknown target state '{transition.to}'"
                    )

        # Ensure at least one terminal state exists
        terminal_states = [
            s for s in self.states.values() if s.type == WorkflowStateType.TERMINAL
        ]
        if not terminal_states:
            raise ValueError("Workflow must have at least one terminal state")

        return self

    model_config = {"extra": "forbid"}


class WorkflowContext(BaseModel):
    """Runtime context for workflow execution."""

    workflow_id: str = Field(..., description="Workflow definition ID")
    execution_id: str = Field(default_factory=lambda: str(uuid4()))
    current_state: str = Field(..., description="Current state ID")
    status: WorkflowStatus = Field(default=WorkflowStatus.PENDING)
    data: dict[str, Any] = Field(default_factory=dict, description="Workflow data")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    previous_state: str | None = Field(None, description="Previous state ID")
    terminal_status: str | None = Field(None, description="Terminal status value")
    started_at: datetime | None = Field(
        default=None, description="When execution started"
    )
    completed_at: datetime | None = Field(
        default=None, description="When execution completed"
    )
    paused_at: datetime | None = Field(
        default=None, description="When execution paused"
    )
    error: str | None = Field(default=None, description="Error message if failed")
    retry_count: int = Field(default=0, description="Number of retries")
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class WorkflowExecution(BaseModel):
    """A workflow execution instance."""

    execution_id: str = Field(..., description="Unique execution ID")
    workflow_id: str = Field(..., description="Workflow definition ID")
    workflow_version: str = Field(
        default="1.0", description="Workflow version at start"
    )
    context: WorkflowContext
    history: list[ExecutionHistoryEntry] = Field(
        default_factory=list, description="Execution history"
    )
    status: WorkflowStatus = Field(default=WorkflowStatus.PENDING)

    model_config = {"extra": "forbid"}


class ExecutionHistoryEntry(BaseModel):
    """A single entry in the execution history."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    execution_id: str = Field(..., description="Execution ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    from_state: str | None = Field(None, description="Previous state")
    to_state: str | None = Field(None, description="Next state")
    event_type: str = Field(..., description="Event type")
    actor: str | None = Field(None, description="Actor (user, system, etc.)")
    action: str | None = Field(None, description="Action performed")
    data_snapshot: dict[str, Any] = Field(
        default_factory=dict, description="Data snapshot at this point"
    )
    approval_result: ApprovalStatus | None = Field(None, description="Approval result")
    error: str | None = Field(None, description="Error if any")
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class TaskAssignment(BaseModel):
    """Task assignment to an agent/role."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    execution_id: str = Field(..., description="Execution ID")
    step_id: str = Field(..., description="Workflow step/state ID")
    assignee_role: str = Field(..., description="Assigned role")
    assignee_id: str | None = Field(None, description="Specific assignee ID")
    title: str = Field(..., description="Task title")
    description: str = Field(default="", description="Task description")
    status: str = Field(default="pending", description="Task status")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    assigned_at: datetime | None = Field(None)
    started_at: datetime | None = Field(None)
    completed_at: datetime | None = Field(None)
    due_at: datetime | None = Field(None)
    result: dict[str, Any] | None = Field(None, description="Task result")
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class WorkflowEvent(BaseModel):
    """Event emitted during workflow execution."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    execution_id: str = Field(..., description="Execution ID")
    workflow_id: str = Field(..., description="Workflow definition ID")
    event_type: str = Field(..., description="Event type")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    state_id: str | None = Field(None, description="Current state")
    data: dict[str, Any] = Field(default_factory=dict)
    actor: str | None = Field(None, description="Actor who triggered event")

    model_config = {"extra": "forbid"}


class WorkflowResult(BaseModel):
    """Result of a workflow execution."""

    execution_id: str
    workflow_id: str
    status: WorkflowStatus
    final_state: str | None = None
    terminal_status: WorkflowTerminalStatus | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    history: list[ExecutionHistoryEntry] = Field(default_factory=list)
    error: str | None = None

    model_config = {"extra": "forbid"}


class WorkflowRegistryEntry(BaseModel):
    """Registry entry for a workflow."""

    workflow_id: str
    name: str
    display_name: str
    description: str
    category: WorkflowCategory
    version: str
    enabled: bool
    definition_file: str
    tags: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


# Forward references
ExecutionHistoryEntry.model_rebuild()
WorkflowExecution.model_rebuild()
