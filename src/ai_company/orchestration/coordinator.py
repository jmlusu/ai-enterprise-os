"""Coordinator — the glue layer of the Enterprise Orchestration Engine.

The coordinator acts as the COO: it does not implement business logic
itself. It holds references to the engines (Registry, Bootstrap,
Generator, Workflow, Decision, Memory, Event Bus, Graph, Reporting,
Audit) and dispatches each pipeline task to the owning engine.

Task dispatch is pluggable: ``register_handler(task_type, callable)``
adds or overrides how a task type is executed. Built-in handlers cover
the standard engine operations used by the declarative pipeline catalog.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ai_company.orchestration.exceptions import EngineNotReadyError
from ai_company.orchestration.models import PipelineTask

logger = logging.getLogger(__name__)


class Coordinator:
    """Dispatches pipeline tasks to engine implementations.

    Args:
        engines: Mapping of logical engine name -> engine instance.
    """

    def __init__(
        self,
        engines: dict[str, Any] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._engines: dict[str, Any] = dict(engines or {})
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._handlers: dict[str, Callable[[PipelineTask, dict[str, Any]], Any]] = {}
        self._register_default_handlers()

    # ── Engine registry ───────────────────────────────────────────

    def register_engine(self, name: str, engine: Any) -> None:
        """Register (or replace) an engine under a logical name."""
        self._engines[name] = engine
        self.logger.debug("Engine registered: %s", name)

    def unregister_engine(self, name: str) -> bool:
        """Remove an engine by logical name."""
        return self._engines.pop(name, None) is not None

    def engine(self, name: str) -> Any | None:
        """Return the engine registered under a logical name."""
        return self._engines.get(name)

    def list_engines(self) -> list[str]:
        """Return the names of all registered engines."""
        return sorted(self._engines)

    # ── Handler registry ──────────────────────────────────────────

    def register_handler(
        self,
        task_type: str,
        handler: Callable[[PipelineTask, dict[str, Any]], Any],
    ) -> None:
        """Register (or replace) a dispatch handler for a task type."""
        self._handlers[task_type] = handler

    def unregister_handler(self, task_type: str) -> bool:
        """Remove a dispatch handler."""
        return self._handlers.pop(task_type, None) is not None

    def list_handlers(self) -> list[str]:
        """Return the supported task types."""
        return sorted(self._handlers)

    # ── Dispatch ──────────────────────────────────────────────────

    def execute(
        self,
        task: PipelineTask,
        context: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a pipeline task through its handler.

        Raises:
            EngineNotReadyError: If no handler exists for the task type.
        """
        handler = self._handlers.get(task.task_type)
        if handler is None:
            raise EngineNotReadyError(
                task.engine, f"no handler for task type {task.task_type!r}"
            )
        return handler(task, context or {})

    # ── Built-in handlers ─────────────────────────────────────────

    def _register_default_handlers(self) -> None:
        self.register_handler("load_registry", self._handle_load_registry)
        self.register_handler("generate", self._handle_generate)
        self.register_handler("validate", self._handle_validate)
        self.register_handler("memory_save", self._handle_memory_save)
        self.register_handler("memory_search", self._handle_memory_search)
        self.register_handler("audit_record", self._handle_audit_record)
        self.register_handler("decision", self._handle_decision)
        self.register_handler("workflow", self._handle_workflow)
        self.register_handler("graph_build", self._handle_graph_build)
        self.register_handler("report", self._handle_report)
        self.register_handler("event_publish", self._handle_event_publish)
        self.register_handler("noop", self._handle_noop)

    def _require(self, name: str) -> Any:
        engine = self._engines.get(name)
        if engine is None:
            raise EngineNotReadyError(name)
        return engine

    def _current_registry(self, context: dict[str, Any]) -> Any | None:
        """Return the last loaded CompanyRegistry, if any."""
        registry_engine = self._engines.get("registry")
        if registry_engine is None:
            return None
        last = getattr(registry_engine, "last_result", None)
        return getattr(last, "registry", None) if last else None

    def _handle_load_registry(
        self, task: PipelineTask, context: dict[str, Any]
    ) -> dict[str, Any]:
        engine = self._require("registry")
        result = engine.load()
        if not result.success:
            raise RuntimeError(f"Registry load failed: {', '.join(result.errors)}")
        registry = result.registry
        return {
            "success": True,
            "executives": len(getattr(registry, "executives", [])),
            "departments": len(getattr(registry, "departments", {})),
            "specialists": len(getattr(registry, "specialists", [])),
            "workflows": len(getattr(registry, "workflows", [])),
            "warnings": list(getattr(result, "warnings", [])),
        }

    def _handle_generate(
        self, task: PipelineTask, context: dict[str, Any]
    ) -> dict[str, Any]:
        generator = self._require("generator")
        target = str(task.params.get("target", "all"))
        method = self._generate_method(generator, target)
        result = method()
        summary: dict[str, Any] = {"success": True, "target": target}
        summary_method = getattr(result, "summary", None)
        if callable(summary_method):
            try:
                summary.update(summary_method())
            except Exception:
                pass
        return summary

    @staticmethod
    def _generate_method(generator: Any, target: str) -> Callable[[], Any]:
        """Map a generation target to a CompanyGenerator method."""
        mapping: dict[str, str] = {
            "all": "generate_all",
            "organization": "generate",
            "org": "generate",
            "board": "generate_board",
            "executives": "generate_executives",
            "departments": "generate_departments",
            "specialists": "generate_specialists",
            "workflows": "generate_workflows",
            "prompts": "generate_prompts",
            "docs": "generate_docs",
            "graph": "generate_graph_export",
        }
        method_name = mapping.get(target)
        if method_name is None:
            raise EngineNotReadyError(
                "generator", f"unknown generation target {target!r}"
            )
        method = getattr(generator, method_name, None)
        if method is None:
            raise EngineNotReadyError(
                "generator", f"generator has no method {method_name!r}"
            )
        return method

    def _handle_validate(
        self, task: PipelineTask, context: dict[str, Any]
    ) -> dict[str, Any]:
        engine = self._require("validator")
        result = engine.validate_all()
        return {
            "success": bool(result.passed),
            "summary": result.summary(),
        }

    def _handle_memory_save(
        self, task: PipelineTask, context: dict[str, Any]
    ) -> dict[str, Any]:
        engine = self._require("memory")
        entry = engine.save(
            content=dict(task.params.get("content", {})),
            memory_type=str(task.params.get("memory_type", "system")),
            namespace=str(task.params.get("namespace", "global")),
            tags=list(task.params.get("tags", [])),
            source=str(task.params.get("source", "orchestrator")),
            metadata=dict(task.params.get("metadata", {})),
        )
        return {"success": True, "memory_id": entry.id}

    def _handle_memory_search(
        self, task: PipelineTask, context: dict[str, Any]
    ) -> dict[str, Any]:
        engine = self._require("memory")
        entries = engine.search(
            query=str(task.params.get("query", "")),
            namespace=task.params.get("namespace"),
            limit=int(task.params.get("limit", 20)),
        )
        return {
            "success": True,
            "count": len(entries),
            "ids": [e.id for e in entries],
        }

    def _handle_audit_record(
        self, task: PipelineTask, context: dict[str, Any]
    ) -> dict[str, Any]:
        engine = self._require("audit")
        event = engine.record(
            event_type=str(task.params.get("event_type", "orchestration")),
            engine=str(task.params.get("engine", "orchestrator")),
            module=str(task.params.get("module", "orchestration")),
            action=str(task.params.get("action", "")),
            result=str(task.params.get("result", "success")),
            error=task.params.get("error"),
            metadata=dict(task.params.get("metadata", {})),
        )
        to_dict = getattr(event, "to_dict", None)
        if callable(to_dict):
            data = to_dict()
            return {"success": True, "audit_event": data}
        return {"success": True, "audit_event": str(event)}

    def _handle_decision(
        self, task: PipelineTask, context: dict[str, Any]
    ) -> dict[str, Any]:
        engine = self._require("decision")
        title = task.params.get("title")
        if title:
            decision = engine.create_decision(
                title=str(title),
                description=str(task.params.get("description", "")),
                requester=str(task.params.get("requester", "orchestrator")),
                tags=list(task.params.get("tags", [])),
            )
            return {
                "success": True,
                "decision_id": getattr(decision, "id", None),
            }
        stats = engine.get_statistics()
        return {"success": True, "statistics": stats}

    def _handle_workflow(
        self, task: PipelineTask, context: dict[str, Any]
    ) -> dict[str, Any]:
        engine = self._require("workflow")
        name = task.params.get("name")
        if name:
            workflow = engine.get_workflow(str(name))
            if workflow is None:
                raise EngineNotReadyError("workflow", f"unknown workflow {name!r}")
            return {
                "success": True,
                "workflow": workflow.name,
                "steps": len(workflow.steps),
            }
        workflows = engine.list_workflows()
        return {
            "success": True,
            "count": len(workflows),
            "workflows": workflows,
        }

    def _handle_graph_build(
        self, task: PipelineTask, context: dict[str, Any]
    ) -> dict[str, Any]:
        registry = self._current_registry(context)
        if registry is None:
            raise EngineNotReadyError(
                "registry", "load the registry before building the graph"
            )
        from ai_company.company.organization import OrganizationGenerator

        result = OrganizationGenerator(registry).generate()
        metadata = result.metadata
        return {
            "success": True,
            "nodes": metadata.total_nodes,
            "edges": metadata.total_edges,
            "max_depth": metadata.max_depth,
            "orphans": list(metadata.orphans),
            "cycles": list(metadata.cycles),
            "warnings": list(result.warnings),
        }

    def _handle_report(
        self, task: PipelineTask, context: dict[str, Any]
    ) -> dict[str, Any]:
        registry = self._current_registry(context)
        if registry is None:
            raise EngineNotReadyError(
                "registry", "load the registry before generating a report"
            )
        from ai_company.company.organization import OrganizationGenerator

        result = OrganizationGenerator(registry).generate()
        metadata = result.metadata
        return {
            "success": True,
            "nodes": metadata.total_nodes,
            "edges": metadata.total_edges,
            "max_depth": metadata.max_depth,
            "span_of_control": dict(metadata.span_of_control),
            "orphans": list(metadata.orphans),
            "cycles": list(metadata.cycles),
            "warnings": list(metadata.warnings),
        }

    def _handle_event_publish(
        self, task: PipelineTask, context: dict[str, Any]
    ) -> dict[str, Any]:
        bus = self._require("event_bus")
        from ai_company.events.models import EventType

        event_type = EventType(
            str(task.params.get("event_type", "system.health_check"))
        )
        results = bus.publish_event(
            event_type=event_type,
            payload=dict(task.params.get("payload", {})),
            source=str(task.params.get("source", "orchestrator")),
            correlation_id=context.get("correlation_id"),
        )
        return {
            "success": True,
            "delivered": [r.subscriber_name for r in results],
        }

    def _handle_noop(
        self, task: PipelineTask, context: dict[str, Any]
    ) -> dict[str, Any]:
        return {"success": True, "status": "noop", "task_id": task.id}


def default_coordinator(
    memory_engine: Any | None = None,
    event_bus: Any | None = None,
    audit_engine: Any | None = None,
) -> Coordinator:
    """Build a coordinator wired to the real engine implementations.

    Engines that fail to construct (e.g. missing configuration) are
    skipped with a warning; tasks routed to a missing engine fail with
    :class:`EngineNotReadyError`.
    """
    from ai_company.audit.engine import AuditEngine
    from ai_company.company.generator import CompanyGenerator
    from ai_company.decision.engine import DecisionEngine
    from ai_company.events.bus import EventBus
    from ai_company.memory.engine import MemoryEngine
    from ai_company.orchestrator.workflow import WorkflowManager
    from ai_company.registry.registry import RegistryEngine
    from ai_company.validator.engine import ValidatorEngine

    engines: dict[str, Any] = {}
    candidates: list[tuple[str, Any]] = [
        ("registry", RegistryEngine()),
        ("generator", CompanyGenerator()),
        ("validator", ValidatorEngine()),
        ("workflow", WorkflowManager()),
        ("memory", memory_engine or MemoryEngine(storage_path="memory/store.jsonl")),
        ("decision", DecisionEngine()),
        ("audit", audit_engine or AuditEngine()),
        ("event_bus", event_bus or EventBus()),
    ]
    for name, engine in candidates:
        try:
            engines[name] = engine
        except Exception as exc:  # defensive: skip broken engines
            logger.warning("Could not construct engine %r: %s", name, exc)
    return Coordinator(engines)
