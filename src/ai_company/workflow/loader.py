"""Workflow loader for loading workflow definitions from YAML files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from ai_company.workflow.models import WorkflowDefinition, WorkflowRegistryEntry

logger = logging.getLogger(__name__)


class WorkflowLoader:
    """Loads workflow definitions from YAML files."""

    def __init__(self, workflows_dir: str | Path = "config/workflows"):
        self.workflows_dir = Path(workflows_dir)
        self._cache: Dict[str, WorkflowDefinition] = {}

    def load_workflow(self, workflow_id: str) -> WorkflowDefinition:
        """Load a single workflow definition by ID."""
        if workflow_id in self._cache:
            return self._cache[workflow_id]

        # Try to find the workflow file
        file_path = self._find_workflow_file(workflow_id)
        if not file_path:
            raise FileNotFoundError(f"Workflow definition not found: {workflow_id}")

        definition = self._load_from_file(file_path)
        self._cache[workflow_id] = definition
        return definition

    def load_all_workflows(self) -> List[WorkflowDefinition]:
        """Load all workflow definitions from the workflows directory."""
        workflows = []
        for file_path in self.workflows_dir.glob("*.yaml"):
            if file_path.name == "workflow_registry.yaml":
                continue  # Skip registry file
            if file_path.name == "template.yaml":
                continue  # Skip template file
            try:
                definition = self._load_from_file(file_path)
                workflows.append(definition)
                self._cache[definition.name] = definition
            except Exception as e:
                logger.warning(f"Failed to load workflow from {file_path}: {e}")
        return workflows

    def load_registry(self) -> List[WorkflowRegistryEntry]:
        """Load the workflow registry."""
        registry_path = self.workflows_dir / "workflow_registry.yaml"
        if not registry_path.exists():
            logger.warning("Workflow registry not found, building from definitions")
            return self._build_registry_from_definitions()

        with open(registry_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        entries = []
        for wf_id, wf_data in data.get("workflows", {}).items():
            entry = WorkflowRegistryEntry(workflow_id=wf_id, **wf_data)
            entries.append(entry)
        return entries

    def _find_workflow_file(self, workflow_id: str) -> Optional[Path]:
        """Find the YAML file for a workflow ID."""
        # Direct match
        direct_path = self.workflows_dir / f"{workflow_id}.yaml"
        if direct_path.exists():
            return direct_path

        # Check registry for definition_file
        registry = self.load_registry()
        for entry in registry:
            if entry.workflow_id == workflow_id:
                defined_path = self.workflows_dir / entry.definition_file
                if defined_path.exists():
                    return defined_path

        # Fallback: search all files for matching workflow name
        for file_path in self.workflows_dir.glob("*.yaml"):
            if file_path.name in ("workflow_registry.yaml", "template.yaml"):
                continue
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data.get("name") == workflow_id:
                    return file_path
            except Exception:
                continue

        return None

    def _load_from_file(self, file_path: Path) -> WorkflowDefinition:
        """Load a workflow definition from a YAML file."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"Empty workflow file: {file_path}")

        # Handle nested workflow structure
        if "workflow" in data:
            data = data["workflow"]

        return WorkflowDefinition(**data)

    def _build_registry_from_definitions(self) -> List[WorkflowRegistryEntry]:
        """Build registry entries from loaded definitions."""
        entries = []
        for file_path in self.workflows_dir.glob("*.yaml"):
            if file_path.name in ("workflow_registry.yaml", "template.yaml"):
                continue
            try:
                definition = self._load_from_file(file_path)
                entry = WorkflowRegistryEntry(
                    workflow_id=definition.name,
                    name=definition.name,
                    display_name=definition.display_name,
                    description=definition.description,
                    category=definition.category,
                    version=definition.version,
                    enabled=definition.enabled,
                    definition_file=file_path.name,
                    tags=definition.tags,
                )
                entries.append(entry)
            except Exception as e:
                logger.warning(f"Failed to build registry entry from {file_path}: {e}")
        return entries

    def reload_workflow(self, workflow_id: str) -> WorkflowDefinition:
        """Force reload a workflow definition (clear cache)."""
        if workflow_id in self._cache:
            del self._cache[workflow_id]
        return self.load_workflow(workflow_id)

    def clear_cache(self) -> None:
        """Clear the workflow cache."""
        self._cache.clear()
