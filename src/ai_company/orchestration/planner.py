"""Pipeline planning — declarative definitions to executable plans.

The :class:`PipelinePlanner` validates declarative pipeline definitions
(dict or YAML), converts them to :class:`Pipeline` models, binds them
into :class:`OrchestrationPlan` objects with a schedule mode, and
provides the built-in pipeline catalog (bootstrap, generation, report).
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ai_company.orchestration.dependencies import DependencyGraph
from ai_company.orchestration.exceptions import (
    DependencyError,
    InvalidPlanError,
    PlanNotFoundError,
)
from ai_company.orchestration.models import (
    OrchestrationPlan,
    Pipeline,
    ScheduleMode,
)

logger = logging.getLogger(__name__)

# ── Built-in pipeline catalog (fallback when config is unavailable) ──
# Mirrors the `pipelines:` section of config/orchestration/engine.yaml.

BUILTIN_PIPELINES_DATA: dict[str, dict[str, Any]] = {
    "bootstrap": {
        "name": "bootstrap",
        "description": (
            "Bootstrap a company from scratch: registry -> generation "
            "-> validation -> memory -> audit"
        ),
        "stages": [
            {
                "id": "registry",
                "name": "Load Registry",
                "mode": "sequential",
                "tasks": [
                    {
                        "id": "load_registry",
                        "name": "Load registry data",
                        "task_type": "load_registry",
                        "engine": "registry",
                        "params": {"action": "load"},
                    }
                ],
            },
            {
                "id": "generation",
                "name": "Generate Company",
                "mode": "sequential",
                "tasks": [
                    {
                        "id": "generate_all",
                        "name": "Generate all company artifacts",
                        "task_type": "generate",
                        "engine": "generator",
                        "params": {"target": "all"},
                    }
                ],
            },
            {
                "id": "validation",
                "name": "Validate Output",
                "mode": "sequential",
                "tasks": [
                    {
                        "id": "validate",
                        "name": "Validate generated artifacts",
                        "task_type": "validate",
                        "engine": "validator",
                        "params": {"action": "all"},
                    }
                ],
            },
            {
                "id": "persistence",
                "name": "Persist & Audit",
                "mode": "parallel",
                "tasks": [
                    {
                        "id": "save_memory",
                        "name": "Record bootstrap in memory",
                        "task_type": "memory_save",
                        "engine": "memory",
                        "params": {
                            "memory_type": "company",
                            "source": "orchestration",
                        },
                    },
                    {
                        "id": "audit_bootstrap",
                        "name": "Record audit trail",
                        "task_type": "audit_record",
                        "engine": "audit",
                        "params": {
                            "event_type": "bootstrap",
                            "engine": "orchestration",
                        },
                    },
                ],
            },
        ],
    },
    "generation": {
        "name": "generation",
        "description": (
            "Regenerate company artifacts with parallel prompts/docs/graph"
        ),
        "stages": [
            {
                "id": "registry",
                "name": "Load Registry",
                "mode": "sequential",
                "tasks": [
                    {
                        "id": "load_registry",
                        "name": "Load registry data",
                        "task_type": "load_registry",
                        "engine": "registry",
                        "params": {"action": "load"},
                    }
                ],
            },
            {
                "id": "generation",
                "name": "Generate Artifacts",
                "mode": "parallel",
                "tasks": [
                    {
                        "id": "generate_prompts",
                        "name": "Generate prompts",
                        "task_type": "generate",
                        "engine": "generator",
                        "params": {"target": "prompts"},
                    },
                    {
                        "id": "generate_docs",
                        "name": "Generate docs",
                        "task_type": "generate",
                        "engine": "generator",
                        "params": {"target": "docs"},
                    },
                    {
                        "id": "generate_graph",
                        "name": "Generate graph export",
                        "task_type": "generate",
                        "engine": "generator",
                        "params": {"target": "graph"},
                    },
                ],
            },
            {
                "id": "persistence",
                "name": "Persist & Audit",
                "mode": "sequential",
                "tasks": [
                    {
                        "id": "save_memory",
                        "name": "Record generation in memory",
                        "task_type": "memory_save",
                        "engine": "memory",
                        "params": {
                            "memory_type": "company",
                            "source": "orchestration",
                        },
                    },
                    {
                        "id": "audit_generation",
                        "name": "Record audit trail",
                        "task_type": "audit_record",
                        "engine": "audit",
                        "params": {
                            "event_type": "generation",
                            "engine": "orchestration",
                        },
                    },
                ],
            },
        ],
    },
    "report": {
        "name": "report",
        "description": "Analyse reporting structure and record the audit trail",
        "stages": [
            {
                "id": "registry",
                "name": "Load Registry",
                "mode": "sequential",
                "tasks": [
                    {
                        "id": "load_registry",
                        "name": "Load registry data",
                        "task_type": "load_registry",
                        "engine": "registry",
                        "params": {"action": "load"},
                    }
                ],
            },
            {
                "id": "analysis",
                "name": "Analyse Structure",
                "mode": "sequential",
                "tasks": [
                    {
                        "id": "graph_build",
                        "name": "Build organization graph",
                        "task_type": "graph_build",
                        "engine": "graph",
                        "params": {"action": "build"},
                    },
                    {
                        "id": "report",
                        "name": "Analyse reporting structure",
                        "task_type": "report",
                        "engine": "reporting",
                        "params": {"action": "analyse"},
                    },
                ],
            },
            {
                "id": "audit",
                "name": "Record Audit",
                "mode": "sequential",
                "tasks": [
                    {
                        "id": "audit_report",
                        "name": "Record audit trail",
                        "task_type": "audit_record",
                        "engine": "audit",
                        "params": {
                            "event_type": "report",
                            "engine": "orchestration",
                        },
                    }
                ],
            },
        ],
    },
}


def _normalize_dependencies(task_data: dict[str, Any]) -> dict[str, Any]:
    """Coerce typed dependency dicts to plain task-id strings."""
    deps = task_data.get("dependencies", [])
    normalized: list[str] = []
    for dep in deps:
        if isinstance(dep, dict):
            task_id = dep.get("task_id")
            if task_id:
                normalized.append(str(task_id))
        else:
            normalized.append(str(dep))
    task_data["dependencies"] = normalized
    return task_data


class PipelinePlanner:
    """Validates declarative pipelines and builds orchestration plans.

    Args:
        dependencies_config: Dependency resolution config.
        retries_config: Retry config (used for default task retries).
        config_pipelines: Pipelines from config/orchestration/engine.yaml.
    """

    def __init__(
        self,
        dependencies_config: dict[str, Any] | None = None,
        retries_config: dict[str, Any] | None = None,
        config_pipelines: dict[str, Any] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.dependencies_config = dependencies_config or {}
        self.retries_config = retries_config or {}
        self._config_pipelines = dict(config_pipelines or {})
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    # ── Parsing ───────────────────────────────────────────────────

    def parse_pipeline(self, data: dict[str, Any]) -> Pipeline:
        """Validate a declarative pipeline dict into a Pipeline model.

        Raises:
            InvalidPlanError: If the definition is malformed.
        """
        if not isinstance(data, dict) or "stages" not in data:
            raise InvalidPlanError(
                "Pipeline definition must be a dict with 'stages'",
                details={"keys": list(data.keys()) if isinstance(data, dict) else []},
            )

        # Deep-copy so normalization never mutates caller data.
        working = copy.deepcopy(data)
        for stage in working.get("stages", []):
            for task in stage.get("tasks", []):
                _normalize_dependencies(task)

        try:
            pipeline = Pipeline.model_validate(working)
        except ValidationError as exc:
            raise InvalidPlanError(
                "Invalid pipeline definition",
                details={"errors": exc.errors()},
            ) from exc

        try:
            DependencyGraph(pipeline, self.dependencies_config)
        except DependencyError as exc:
            raise InvalidPlanError(
                f"Dependency validation failed: {exc.message}",
                details={"cycle": exc.cycle},
            ) from exc

        return pipeline

    def pipeline_from_yaml(self, path: str | Path) -> Pipeline:
        """Load and validate a pipeline definition from YAML."""
        config_path = Path(path)
        if not config_path.exists():
            raise PlanNotFoundError(f"Pipeline file not found: {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise InvalidPlanError(f"Pipeline file is not a mapping: {config_path}")
        return self.parse_pipeline(data)

    # ── Plan building ─────────────────────────────────────────────

    def plan_from_pipeline(
        self,
        pipeline: Pipeline,
        name: str | None = None,
        description: str = "",
        schedule_mode: str | ScheduleMode = ScheduleMode.IMMEDIATE,
        scheduled_at: datetime | None = None,
        interval_seconds: float | None = None,
        max_runs: int = 0,
        depends_on: list[str] | None = None,
    ) -> OrchestrationPlan:
        """Bind a pipeline into an executable orchestration plan."""
        if isinstance(schedule_mode, str):
            try:
                schedule_mode = ScheduleMode(schedule_mode)
            except ValueError as exc:
                raise InvalidPlanError(
                    f"Unknown schedule mode {schedule_mode!r}"
                ) from exc
        return OrchestrationPlan(
            name=name or pipeline.name,
            description=description or pipeline.description,
            pipeline=pipeline,
            schedule_mode=schedule_mode,
            scheduled_at=scheduled_at,
            interval_seconds=interval_seconds,
            max_runs=max_runs,
            depends_on=list(depends_on or []),
        )

    def plan_from_yaml(self, path: str | Path) -> OrchestrationPlan:
        """Load a full plan definition (plan metadata + pipeline) from YAML."""
        config_path = Path(path)
        if not config_path.exists():
            raise PlanNotFoundError(f"Plan file not found: {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict) or "pipeline" not in data:
            raise InvalidPlanError(
                "Plan file must contain a 'pipeline' section",
                details={"path": str(config_path)},
            )

        schedule_mode = data.get("schedule_mode", ScheduleMode.IMMEDIATE.value)
        scheduled_at = data.get("scheduled_at")
        if isinstance(scheduled_at, str) and scheduled_at:
            scheduled_at = datetime.fromisoformat(scheduled_at)

        pipeline = self.parse_pipeline(data["pipeline"])
        return self.plan_from_pipeline(
            pipeline,
            name=data.get("name") or pipeline.name,
            description=data.get("description", ""),
            schedule_mode=schedule_mode,
            scheduled_at=scheduled_at,
            interval_seconds=data.get("interval_seconds"),
            max_runs=int(data.get("max_runs", 0)),
            depends_on=data.get("depends_on"),
        )

    # ── Pipeline catalog ──────────────────────────────────────────

    def config_pipelines(self) -> dict[str, Pipeline]:
        """Return parsed pipelines from config (or empty dict)."""
        parsed: dict[str, Pipeline] = {}
        for name, definition in self._config_pipelines.items():
            if not isinstance(definition, dict):
                continue
            working = copy.deepcopy(definition)
            working["name"] = working.get("name") or name
            parsed[name] = self.parse_pipeline(working)
        return parsed

    def builtin_pipelines(self) -> dict[str, Pipeline]:
        """Return the built-in pipeline catalog (config wins)."""
        parsed: dict[str, Pipeline] = self.config_pipelines()
        for name, definition in BUILTIN_PIPELINES_DATA.items():
            if name not in parsed:
                working = copy.deepcopy(definition)
                working["name"] = working.get("name") or name
                parsed[name] = self.parse_pipeline(working)
        return parsed

    def get_pipeline(self, name: str) -> Pipeline:
        """Return a pipeline by name (config, then built-in)."""
        pipelines = self.builtin_pipelines()
        pipeline = pipelines.get(name)
        if pipeline is None:
            raise PlanNotFoundError(f"Unknown pipeline: {name}")
        return pipeline

    def list_pipelines(self) -> list[str]:
        """Return the names of all available pipelines."""
        return sorted(self.builtin_pipelines())
