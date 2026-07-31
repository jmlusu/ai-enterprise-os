"""Exceptions for workflow engine."""

from __future__ import annotations

from typing import Any


class WorkflowError(Exception):
    """Base exception for workflow errors."""

    def __init__(
        self,
        message: str,
        workflow_id: str | None = None,
        execution_id: str | None = None,
    ):
        super().__init__(message)
        self.workflow_id = workflow_id
        self.execution_id = execution_id


class WorkflowNotFoundError(WorkflowError):
    """Workflow definition not found."""

    pass


class WorkflowValidationError(WorkflowError):
    """Workflow definition validation failed."""

    pass


class InvalidStateError(WorkflowError):
    """Invalid state transition attempted."""

    pass


class StateNotFoundError(WorkflowError):
    """State not found in workflow definition."""

    pass


class TransitionError(WorkflowError):
    """State transition failed."""

    pass


class ApprovalRequiredError(WorkflowError):
    """Approval required but not provided."""

    pass


class ApprovalTimeoutError(WorkflowError):
    """Approval request timed out."""

    pass


class ApprovalRejectedError(WorkflowError):
    """Approval was rejected."""

    def __init__(self, message: str, reason: str = "", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.reason = reason


class ExecutionNotFoundError(WorkflowError):
    """Workflow execution not found."""

    pass


class ExecutionNotRunningError(WorkflowError):
    """Execution is not in running state."""

    pass


class ExecutionAlreadyCompletedError(WorkflowError):
    """Execution already completed."""

    pass


class ContextError(WorkflowError):
    """Workflow context error."""

    pass


class ContextNotFoundError(WorkflowError):
    """Execution context not found."""

    pass


class ActionError(WorkflowError):
    """Action execution error."""

    pass


class ActionTimeoutError(ActionError):
    """Action execution timed out."""

    pass


class ActionNotFoundError(ActionError):
    """Action handler not found."""

    pass


class WaitError(WorkflowError):
    """Wait state error."""

    pass


class WaitTimeoutError(WaitError):
    """Wait condition timed out."""

    pass


class ConditionEvaluationError(WorkflowError):
    """Condition evaluation failed."""

    pass


class DataValidationError(WorkflowError):
    """Workflow data validation failed."""

    pass


class SchedulerError(WorkflowError):
    """Scheduler error."""

    pass


class RegistryError(WorkflowError):
    """Workflow registry error."""

    pass


class HandlerError(WorkflowError):
    """Handler execution error."""

    pass


class RetryExhaustedError(WorkflowError):
    """All retries exhausted."""

    def __init__(self, message: str, attempts: int, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.attempts = attempts


class ConcurrentModificationError(WorkflowError):
    """Concurrent modification of execution context."""

    pass
