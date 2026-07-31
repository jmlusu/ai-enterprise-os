"""Workflow registry for managing workflow definitions and instances."""

from __future__ import annotations

import logging
from pathlib import Path

from ai_company.workflow.loader import WorkflowLoader
from ai_company.workflow.models import (
    WorkflowCategory,
    WorkflowDefinition,
    WorkflowRegistryEntry,
)

logger = logging.getLogger(__name__)


class WorkflowRegistry:
    """Registry for workflow definitions and metadata."""

    def __init__(self, workflows_dir: str | Path = "config/workflows"):
        self.loader = WorkflowLoader(workflows_dir)
        self._definitions: dict[str, WorkflowDefinition] = {}
        self._registry_entries: dict[str, WorkflowRegistryEntry] = {}
        self._initialized = False

    def initialize(self) -> None:
        """Initialize the registry by loading all workflows."""
        if self._initialized:
            return

        # Load registry entries
        entries = self.loader.load_registry()
        for entry in entries:
            self._registry_entries[entry.workflow_id] = entry

        # Load all definitions
        definitions = self.loader.load_all_workflows()
        for definition in definitions:
            self._definitions[definition.name] = definition

        self._initialized = True
        logger.info(
            f"Workflow registry initialized with {len(self._definitions)} workflows"
        )

    def get_definition(self, workflow_id: str) -> WorkflowDefinition:
        """Get a workflow definition by ID."""
        if not self._initialized:
            self.initialize()

        if workflow_id not in self._definitions:
            # Try to load on demand
            try:
                definition = self.loader.load_workflow(workflow_id)
                self._definitions[workflow_id] = definition
                return definition
            except FileNotFoundError:
                raise KeyError(f"Workflow not found: {workflow_id}")

        return self._definitions[workflow_id]

    def get_registry_entry(self, workflow_id: str) -> WorkflowRegistryEntry:
        """Get a registry entry by workflow ID."""
        if not self._initialized:
            self.initialize()

        if workflow_id not in self._registry_entries:
            raise KeyError(f"Registry entry not found: {workflow_id}")

        return self._registry_entries[workflow_id]

    def list_workflows(
        self,
        category: WorkflowCategory | None = None,
        enabled_only: bool = True,
    ) -> list[WorkflowRegistryEntry]:
        """List all registered workflows."""
        if not self._initialized:
            self.initialize()

        workflows = list(self._registry_entries.values())

        if category:
            workflows = [w for w in workflows if w.category == category]

        if enabled_only:
            workflows = [w for w in workflows if w.enabled]

        return workflows

    def list_workflow_ids(
        self,
        category: WorkflowCategory | None = None,
        enabled_only: bool = True,
    ) -> list[str]:
        """List all workflow IDs."""
        return [w.workflow_id for w in self.list_workflows(category, enabled_only)]

    def get_definition_ids(self) -> list[str]:
        """Get all loaded definition IDs."""
        if not self._initialized:
            self.initialize()
        return list(self._definitions.keys())

    def register_workflow(self, definition: WorkflowDefinition) -> None:
        """Register a workflow definition programmatically."""
        self._definitions[definition.name] = definition
        entry = WorkflowRegistryEntry(
            workflow_id=definition.name,
            name=definition.name,
            display_name=definition.display_name,
            description=definition.description,
            category=definition.category,
            version=definition.version,
            enabled=definition.enabled,
            definition_file=f"{definition.name}.yaml",
            tags=definition.tags,
        )
        self._registry_entries[definition.name] = entry

    def unregister_workflow(self, workflow_id: str) -> bool:
        """Unregister a workflow."""
        removed = False
        if workflow_id in self._definitions:
            del self._definitions[workflow_id]
            removed = True
        if workflow_id in self._registry_entries:
            del self._registry_entries[workflow_id]
            removed = True
        return removed

    def reload_workflow(self, workflow_id: str) -> WorkflowDefinition:
        """Reload a workflow definition from disk."""
        self.loader.clear_cache()
        definition = self.loader.load_workflow(workflow_id)
        self._definitions[workflow_id] = definition
        return definition

    def validate_workflow(self, workflow_id: str) -> list[str]:
        """Validate a workflow definition, return list of errors."""
        try:
            definition = self.get_definition(workflow_id)
            errors = []

            # Validate states
            if definition.initial_state not in definition.states:
                errors.append(
                    f"Initial state '{definition.initial_state}' not in states"
                )

            # Validate transitions
            for state_id, state in definition.states.items():
                for transition in state.transitions:
                    if transition.to not in definition.states:
                        errors.append(
                            f"State '{state_id}' references unknown target state '{transition.to}'"
                        )

            # Check for terminal states
            terminal_states = [
                s for s in definition.states.values() if s.type.value == "terminal"
            ]
            if not terminal_states:
                errors.append("No terminal states defined")

            # Validate approval states have approval config
            for state_id, state in definition.states.items():
                if state.type.value == "approval" and not state.approval:
                    errors.append(
                        f"Approval state '{state_id}' missing approval config"
                    )

            return errors
        except Exception as e:
            return [f"Validation error: {e!s}"]

    def get_categories(self) -> list[WorkflowCategory]:
        """Get all workflow categories."""
        if not self._initialized:
            self.initialize()
        return list(set(entry.category for entry in self._registry_entries.values()))

    def get_workflows_by_category(
        self,
    ) -> dict[WorkflowCategory, list[WorkflowRegistryEntry]]:
        """Get workflows grouped by category."""
        if not self._initialized:
            self.initialize()

        result: dict[WorkflowCategory, list[WorkflowRegistryEntry]] = {}
        for entry in self._registry_entries.values():
            if entry.category not in result:
                result[entry.category] = []
            result[entry.category].append(entry)
        return result

    def export_registry(self, output_path: str | Path) -> Path:
        """Export registry to YAML file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "1.0",
            "workflows": {
                entry.workflow_id: {
                    "name": entry.name,
                    "display_name": entry.display_name,
                    "description": entry.description,
                    "category": entry.category.value,
                    "version": entry.version,
                    "enabled": entry.enabled,
                    "definition_file": entry.definition_file,
                    "tags": entry.tags,
                }
                for entry in self._registry_entries.values()
            },
        }

        import yaml

        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Registry exported to {output_path}")
        return output_path
