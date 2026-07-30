"""Workflow manager for AI Enterprise OS Orchestration Layer."""

from __future__ import annotations

import logging
from typing import Any


class WorkflowDefinition:
    """Defines a workflow with a sequence of steps."""

    def __init__(
        self,
        name: str,
        description: str = "",
        steps: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.steps = steps or []
        self.metadata = metadata or {}


class WorkflowManager:
    """Manages workflow definitions for the orchestration layer."""

    def __init__(self) -> None:
        self._workflows: dict[str, WorkflowDefinition] = {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self._register_default_workflows()

    def _register_default_workflows(self) -> None:
        """Register built-in default workflows."""
        self._workflows["generate_company"] = WorkflowDefinition(
            name="generate_company",
            description="Generate all company artifacts from registry",
            steps=[
                {
                    "type": "load_registry",
                    "name": "load_registry",
                    "params": {"action": "load"},
                },
                {
                    "type": "generate",
                    "name": "generate_prompts",
                    "params": {"target": "prompts"},
                },
                {
                    "type": "generate",
                    "name": "generate_docs",
                    "params": {"target": "docs"},
                },
                {
                    "type": "generate",
                    "name": "generate_config",
                    "params": {"target": "config"},
                },
            ],
        )

        self._workflows["validate_all"] = WorkflowDefinition(
            name="validate_all",
            description="Run all validations",
            steps=[
                {
                    "type": "validate",
                    "name": "validate_yaml",
                    "params": {"target": "yaml"},
                },
                {
                    "type": "validate",
                    "name": "validate_templates",
                    "params": {"target": "templates"},
                },
                {
                    "type": "validate",
                    "name": "validate_manifest",
                    "params": {"target": "manifest"},
                },
            ],
        )

        self._workflows["bootstrap"] = WorkflowDefinition(
            name="bootstrap",
            description="Bootstrap a new company from scratch",
            steps=[
                {
                    "type": "load_registry",
                    "name": "load_registry",
                    "params": {"action": "load"},
                },
                {
                    "type": "generate",
                    "name": "generate_all",
                    "params": {"target": "all"},
                },
                {
                    "type": "save_memory",
                    "name": "record_bootstrap",
                    "params": {"action": "save", "memory_type": "company"},
                },
                {
                    "type": "audit_record",
                    "name": "audit_bootstrap",
                    "params": {"action": "record", "event_type": "bootstrap"},
                },
            ],
        )

    def register_workflow(self, workflow: WorkflowDefinition) -> None:
        """Register a workflow definition."""
        self._workflows[workflow.name] = workflow
        self.logger.info(
            f"Workflow registered: {workflow.name} ({len(workflow.steps)} steps)"
        )

    def get_workflow(self, name: str) -> WorkflowDefinition | None:
        """Get a workflow definition by name."""
        return self._workflows.get(name)

    def list_workflows(self) -> list[dict[str, Any]]:
        """List all registered workflows."""
        return [
            {"name": w.name, "description": w.description, "steps": len(w.steps)}
            for w in self._workflows.values()
        ]

    def remove_workflow(self, name: str) -> bool:
        """Remove a workflow definition."""
        return self._workflows.pop(name, None) is not None
