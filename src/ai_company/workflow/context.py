"""Workflow execution context management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4


from ai_company.workflow.models import (
    WorkflowContext,
    WorkflowStatus,
    ExecutionHistoryEntry,
)


@dataclass
class StepContext:
    """Context for a single workflow step execution."""

    step_id: str
    execution_id: str
    workflow_id: str
    state_id: str
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class ContextManager:
    """Manages workflow execution contexts."""

    def __init__(self) -> None:
        self._contexts: Dict[str, WorkflowContext] = {}
        self._step_contexts: Dict[str, List[StepContext]] = {}

    def create_context(
        self,
        workflow_id: str,
        initial_state: str,
        initial_data: Optional[Dict[str, Any]] = None,
        execution_id: Optional[str] = None,
    ) -> WorkflowContext:
        """Create a new workflow execution context."""
        ctx = WorkflowContext(
            workflow_id=workflow_id,
            execution_id=execution_id or str(uuid4()),
            current_state=initial_state,
            data=initial_data or {},
            status=WorkflowStatus.PENDING,
            previous_state=None,
            terminal_status=None,
        )
        self._contexts[ctx.execution_id] = ctx
        self._step_contexts[ctx.execution_id] = []
        return ctx

    def get_context(self, execution_id: str) -> Optional[WorkflowContext]:
        """Get an execution context."""
        return self._contexts.get(execution_id)

    def update_context(
        self,
        execution_id: str,
        **updates: Any,
    ) -> Optional[WorkflowContext]:
        """Update an execution context."""
        ctx = self._contexts.get(execution_id)
        if not ctx:
            return None

        for key, value in updates.items():
            if hasattr(ctx, key):
                setattr(ctx, key, value)

        ctx.updated_at = datetime.utcnow()
        return ctx

    def update_data(
        self,
        execution_id: str,
        data: Dict[str, Any],
        merge: bool = True,
    ) -> Optional[WorkflowContext]:
        """Update context data."""
        ctx = self._contexts.get(execution_id)
        if not ctx:
            return None

        if merge:
            ctx.data.update(data)
        else:
            ctx.data = data

        ctx.updated_at = datetime.utcnow()
        return ctx

    def transition_state(
        self,
        execution_id: str,
        from_state: str,
        to_state: str,
    ) -> Optional[WorkflowContext]:
        """Record a state transition."""
        ctx = self._contexts.get(execution_id)
        if not ctx:
            return None

        ctx.previous_state = ctx.current_state
        ctx.current_state = to_state
        ctx.updated_at = datetime.utcnow()
        return ctx

    def start_execution(self, execution_id: str) -> Optional[WorkflowContext]:
        """Mark execution as started."""
        ctx = self._contexts.get(execution_id)
        if not ctx:
            return None

        ctx.status = WorkflowStatus.RUNNING
        ctx.started_at = datetime.utcnow()
        ctx.updated_at = datetime.utcnow()
        return ctx

    def pause_execution(self, execution_id: str) -> Optional[WorkflowContext]:
        """Pause execution."""
        ctx = self._contexts.get(execution_id)
        if not ctx:
            return None

        ctx.status = WorkflowStatus.PAUSED
        ctx.paused_at = datetime.utcnow()
        ctx.updated_at = datetime.utcnow()
        return ctx

    def resume_execution(self, execution_id: str) -> Optional[WorkflowContext]:
        """Resume execution."""
        ctx = self._contexts.get(execution_id)
        if not ctx:
            return None

        ctx.status = WorkflowStatus.RUNNING
        ctx.paused_at = None
        ctx.updated_at = datetime.utcnow()
        return ctx

    def complete_execution(
        self,
        execution_id: str,
        terminal_status: str,
    ) -> Optional[WorkflowContext]:
        """Mark execution as complete."""
        ctx = self._contexts.get(execution_id)
        if not ctx:
            return None

        ctx.status = WorkflowStatus.COMPLETED
        ctx.completed_at = datetime.utcnow()
        ctx.terminal_status = terminal_status
        ctx.updated_at = datetime.utcnow()
        return ctx

    def fail_execution(
        self,
        execution_id: str,
        error: str,
    ) -> Optional[WorkflowContext]:
        """Mark execution as failed."""
        ctx = self._contexts.get(execution_id)
        if not ctx:
            return None

        ctx.status = WorkflowStatus.FAILED
        ctx.error = error
        ctx.completed_at = datetime.utcnow()
        ctx.updated_at = datetime.utcnow()
        return ctx

    def cancel_execution(self, execution_id: str) -> Optional[WorkflowContext]:
        """Cancel execution."""
        ctx = self._contexts.get(execution_id)
        if not ctx:
            return None

        ctx.status = WorkflowStatus.CANCELLED
        ctx.completed_at = datetime.utcnow()
        ctx.updated_at = datetime.utcnow()
        return ctx

    def add_history_entry(
        self,
        execution_id: str,
        entry: ExecutionHistoryEntry,
    ) -> None:
        """Add a history entry."""
        if execution_id not in self._contexts:
            return

        # Also add to step contexts
        if execution_id in self._step_contexts:
            step_ctx = StepContext(
                step_id=entry.id,
                execution_id=execution_id,
                workflow_id=self._contexts[execution_id].workflow_id,
                state_id=entry.to_state or "",
                data=entry.data_snapshot,
            )
            self._step_contexts[execution_id].append(step_ctx)

    def get_step_contexts(self, execution_id: str) -> List[StepContext]:
        """Get all step contexts for an execution."""
        return self._step_contexts.get(execution_id, [])

    def remove_context(self, execution_id: str) -> bool:
        """Remove a context (cleanup)."""
        if execution_id in self._contexts:
            del self._contexts[execution_id]
            if execution_id in self._step_contexts:
                del self._step_contexts[execution_id]
            return True
        return False

    def list_active_contexts(self) -> List[WorkflowContext]:
        """List all active (non-terminal) contexts."""
        active_statuses = {
            WorkflowStatus.PENDING,
            WorkflowStatus.RUNNING,
            WorkflowStatus.PAUSED,
            WorkflowStatus.WAITING_APPROVAL,
            WorkflowStatus.WAITING_EXTERNAL,
        }
        return [ctx for ctx in self._contexts.values() if ctx.status in active_statuses]

    def get_context_by_workflow(self, workflow_id: str) -> List[WorkflowContext]:
        """Get all contexts for a workflow."""
        return [
            ctx for ctx in self._contexts.values() if ctx.workflow_id == workflow_id
        ]
