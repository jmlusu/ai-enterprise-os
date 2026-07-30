"""Orchestration engine for AI Enterprise OS.

Coordinates all platform engines - loading registry, calling generator,
decision, memory, and audit engines, and returning execution reports.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ai_company.orchestrator.executor import TaskExecutor
from ai_company.orchestrator.router import TaskRouter
from ai_company.orchestrator.scheduler import TaskScheduler
from ai_company.orchestrator.state import ExecutionState
from ai_company.orchestrator.workflow import WorkflowManager

if TYPE_CHECKING:
    from ai_company.audit.engine import AuditEngine
    from ai_company.decision.engine import DecisionEngine
    from ai_company.generator.engine import GeneratorEngine
    from ai_company.memory.engine import MemoryEngine
    from ai_company.registry.registry import RegistryEngine


class OrchestrationEngine:
    """Central orchestrator that coordinates all platform engines.

    Responsibilities:
    1. Load the company registry
    2. Validate registry data
    3. Execute generation tasks via Generator Engine
    4. Track decisions via Decision Engine
    5. Maintain history via Memory Engine
    6. Record all operations via Audit Engine
    7. Return comprehensive execution reports

    Args:
        registry: Registry engine
        generator: Generator engine
        decision: Decision engine
        memory: Memory engine
        audit: Audit engine
        scheduler: Task scheduler
        executor: Task executor
        router: Task router
        state: Execution state manager
        workflow: Workflow manager
    """

    def __init__(
        self,
        registry: RegistryEngine | None = None,
        generator: GeneratorEngine | None = None,
        decision: DecisionEngine | None = None,
        memory: MemoryEngine | None = None,
        audit: AuditEngine | None = None,
        scheduler: TaskScheduler | None = None,
        executor: TaskExecutor | None = None,
        router: TaskRouter | None = None,
        state: ExecutionState | None = None,
        workflow: WorkflowManager | None = None,
    ) -> None:
        self.registry = registry
        self.generator = generator
        self.decision = decision
        self.memory = memory
        self.audit = audit
        self.scheduler = scheduler or TaskScheduler()
        self.executor = executor or TaskExecutor()
        self.router = router or TaskRouter()
        self.state = state or ExecutionState()
        self.workflow = workflow or WorkflowManager()
        self.logger = logging.getLogger(self.__class__.__name__)

    def execute(
        self,
        workflow_name: str,
        params: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute a named workflow through the orchestration pipeline.

        Args:
            workflow_name: Name of the workflow to execute
            params: Workflow parameters
            dry_run: If True, simulate without side effects

        Returns:
            Execution report with results from all engines
        """
        self.state.start(workflow_name, params or {}, dry_run)

        try:
            # Record start
            if self.audit:
                self.audit.record(
                    event_type="workflow_start",
                    engine="orchestrator",
                    module="OrchestrationEngine",
                    action=f"execute:{workflow_name}",
                    metadata={"workflow": workflow_name, "params": params},
                )

            # Get workflow definition
            workflow = self.workflow.get_workflow(workflow_name)
            if not workflow:
                error_msg = f"Workflow not found: {workflow_name}"
                self.state.fail(error_msg)
                return self._build_report(status="failed", error=error_msg)

            # Create execution plan
            plan = self.scheduler.create_plan(workflow)
            self.state.set_plan(plan)

            # Execute tasks in order
            for step in plan:
                task_type = step.get("type", "")
                task_params = step.get("params", {})

                # Route task to appropriate engine
                target = self.router.route(task_type, task_params)

                if target == "registry" and self.registry:
                    result = self._execute_registry(task_params, dry_run)
                elif target == "generator" and self.generator:
                    result = self._execute_generator(task_params, dry_run)
                elif target == "decision" and self.decision:
                    result = self._execute_decision(task_params, dry_run)
                elif target == "memory" and self.memory:
                    result = self._execute_memory(task_params, dry_run)
                elif target == "audit" and self.audit:
                    result = self._execute_audit(task_params, dry_run)
                else:
                    result = {
                        "status": "skipped",
                        "reason": f"No engine for target: {target}",
                    }

                self.state.record_step(task_type, result)

            self.state.complete()
            report = self._build_report(status="completed")

        except Exception as e:
            self.logger.error(f"Orchestration failed: {e}")
            self.state.fail(str(e))
            report = self._build_report(status="failed", error=str(e))

        # Record completion
        if self.audit:
            self.audit.record(
                event_type="workflow_complete",
                engine="orchestrator",
                module="OrchestrationEngine",
                action=f"execute:{workflow_name}",
                result=report["status"],
                duration=report.get("duration"),
                metadata={"workflow": workflow_name, "report_status": report["status"]},
            )

        return report

    def execute_task(
        self,
        task_type: str,
        task_params: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute a single task directly."""
        task_params = task_params or {}
        target = self.router.route(task_type, task_params)
        result = self.executor.execute(target, task_type, task_params, dry_run)
        return result

    def register_engine(self, name: str, engine: Any) -> None:
        """Register an engine with the orchestrator."""
        setattr(self, name, engine)

    def get_status(self) -> dict[str, Any]:
        """Get current orchestration status."""
        return self.state.get_status()

    def _execute_registry(
        self, params: dict[str, Any], dry_run: bool = False
    ) -> dict[str, Any]:
        if not self.registry:
            return {"status": "error", "message": "Registry engine not available"}
        action = params.get("action", "load")
        if action == "load":
            result = self.registry.load()
            return {
                "status": "completed",
                "action": "load_registry",
                "result": str(result),
            }
        return {"status": "skipped", "action": f"registry:{action}"}

    def _execute_generator(
        self, params: dict[str, Any], dry_run: bool = False
    ) -> dict[str, Any]:
        if not self.generator:
            return {"status": "error", "message": "Generator engine not available"}
        try:
            result = self.generator.generate(plan_overrides=params)
            return {"status": "completed", "action": "generate", "result": result}
        except Exception as e:
            return {"status": "error", "action": "generate", "error": str(e)}

    def _execute_decision(
        self, params: dict[str, Any], dry_run: bool = False
    ) -> dict[str, Any]:
        if not self.decision:
            return {"status": "error", "message": "Decision engine not available"}
        action = params.get("action", "create")
        if action == "create":
            decision = self.decision.create_decision(
                title=params.get("title", "Untitled"),
                description=params.get("description", ""),
                category=params.get("category", "operational"),
                priority=params.get("priority", "medium"),
                requester=params.get("requester", ""),
                owner=params.get("owner", ""),
            )
            return {
                "status": "completed",
                "action": "create_decision",
                "decision_id": decision.id,
            }
        return {"status": "skipped", "action": f"decision:{action}"}

    def _execute_memory(
        self, params: dict[str, Any], dry_run: bool = False
    ) -> dict[str, Any]:
        if not self.memory:
            return {"status": "error", "message": "Memory engine not available"}
        action = params.get("action", "save")
        if action == "save":
            entry = self.memory.save(
                content=params.get("content", {}),
                memory_type=params.get("memory_type", "system"),
                tags=params.get("tags", []),
                source=params.get("source", "orchestrator"),
            )
            return {
                "status": "completed",
                "action": "save_memory",
                "memory_id": entry.id,
            }
        return {"status": "skipped", "action": f"memory:{action}"}

    def _execute_audit(
        self, params: dict[str, Any], dry_run: bool = False
    ) -> dict[str, Any]:
        if not self.audit:
            return {"status": "error", "message": "Audit engine not available"}
        action = params.get("action", "record")
        if action == "record":
            self.audit.record(
                event_type=params.get("event_type", "orchestrated"),
                engine="orchestrator",
                module="OrchestrationEngine",
                action=params.get("action_name", "execute"),
                user=params.get("user", "system"),
            )
            return {"status": "completed", "action": "record_audit"}
        return {"status": "skipped", "action": f"audit:{action}"}

    def _build_report(
        self, status: str = "completed", error: str | None = None
    ) -> dict[str, Any]:
        return self.state.get_report(status, error)
