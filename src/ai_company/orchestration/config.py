"""Orchestration configuration loaders — read YAML config files.

Reads the ``config/orchestration/`` directory:

- ``engine.yaml`` — core engine settings + declarative pipeline catalog
- ``scheduler.yaml`` — schedule modes and worker settings
- ``dependencies.yaml`` — dependency resolution settings
- ``retries.yaml`` — default retry policy
- ``checkpoints.yaml`` — checkpoint behavior
- ``monitoring.yaml`` — metrics/events/history observability
- ``notifications.yaml`` — delivery channels for lifecycle events
- ``recovery.yaml`` — recovery strategy and action sequence

Loaders follow the same convention as ``ai_company.events.config``: each
``load_*_config(path)`` parses one file and returns a plain dictionary.
Missing files fall back to built-in defaults (with a warning) unless
``required=True`` is passed, matching ``MemoryEngine.from_config``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

ORCHESTRATION_CONFIG_DIR = "config/orchestration"

# ── Built-in defaults (mirror config/orchestration/*.yaml) ───────

DEFAULT_ENGINE_CONFIG: dict[str, Any] = {
    "engine": {
        "name": "Enterprise Orchestration Engine",
        "version": "1.0",
        "max_workers": 4,
        "default_timeout_seconds": 3600,
        "dry_run": False,
        "persist_history": True,
        "history_memory_type": "system",
        "history_namespace": "orchestration",
    },
    "pipelines": {},
}

DEFAULT_SCHEDULER_CONFIG: dict[str, Any] = {
    "scheduler": {
        "default_mode": "immediate",
        "worker_interval_seconds": 5.0,
        "max_scheduled_plans": 1000,
        "max_workers": 4,
        "timezone": "UTC",
        "default_delay_seconds": 0,
        "recurring": {
            "default_interval_seconds": 3600,
            "default_max_runs": 10,
        },
        "dependency": {
            "default_timeout_seconds": 300,
            "fail_on_missing_dependency": True,
        },
    }
}

DEFAULT_DEPENDENCIES_CONFIG: dict[str, Any] = {
    "dependencies": {
        "resolver": "topological",
        "allow_parallel": True,
        "max_parallel_tasks": 4,
        "detect_cycles": True,
        "missing_dependency_policy": "raise",
        "self_dependency_policy": "raise",
        "condition_engine": "simple",
        "simple_conditions": True,
    }
}

DEFAULT_RETRIES_CONFIG: dict[str, Any] = {
    "retries": {
        "default_max_retries": 3,
        "backoff_base_seconds": 1.0,
        "backoff_multiplier": 2.0,
        "max_backoff_seconds": 60.0,
        "jitter": 0.1,
        "timeout_seconds": 3600,
        "retryable_errors": ["TimeoutError", "ConnectionError", "TaskExecutionError"],
    }
}

DEFAULT_CHECKPOINTS_CONFIG: dict[str, Any] = {
    "checkpoints": {
        "enabled": True,
        "auto_checkpoint_on_task_completed": True,
        "auto_checkpoint_on_stage_completed": True,
        "interval_tasks": 1,
        "persist_to_memory": True,
        "persist_to_disk": False,
        "disk_path": "checkpoints",
        "max_checkpoints_per_pipeline": 10,
        "include_task_results": True,
        "include_context": True,
        "version": "1",
    }
}

DEFAULT_MONITORING_CONFIG: dict[str, Any] = {
    "monitoring": {
        "enabled": True,
        "metrics_interval_seconds": 10.0,
        "publish_events": True,
        "record_history": True,
        "track_durations": True,
        "track_retries": True,
        "track_rollbacks": True,
        "track_checkpoints": True,
        "history_max_records": 1000,
        "history_memory_type": "system",
        "history_namespace": "orchestration",
    }
}

DEFAULT_NOTIFICATIONS_CONFIG: dict[str, Any] = {
    "notifications": {
        "enabled": True,
        "channels": {"event_bus": True, "memory": True, "audit": True},
        "source": "orchestrator",
        "correlation_enabled": True,
        "pipeline_events": [
            "pipeline.started",
            "pipeline.completed",
            "pipeline.failed",
            "pipeline.cancelled",
            "pipeline.recovered",
        ],
        "task_events": [
            "task.started",
            "task.completed",
            "task.failed",
            "task.skipped",
        ],
    }
}

DEFAULT_RECOVERY_CONFIG: dict[str, Any] = {
    "recovery": {
        "enabled": True,
        "auto_recover": False,
        "strategy": "checkpoint_first",
        "max_recovery_attempts": 3,
        "restore_latest_checkpoint": True,
        "rollback_on_unrecoverable": True,
        "retry_failed_tasks": True,
        "keep_recovered_tasks": True,
        "action_sequence": ["checkpoint_restore", "rollback", "retry"],
    }
}

_CONFIG_SECTIONS: dict[str, tuple[str, dict[str, Any]]] = {
    "engine": ("engine.yaml", DEFAULT_ENGINE_CONFIG),
    "scheduler": ("scheduler.yaml", DEFAULT_SCHEDULER_CONFIG),
    "dependencies": ("dependencies.yaml", DEFAULT_DEPENDENCIES_CONFIG),
    "retries": ("retries.yaml", DEFAULT_RETRIES_CONFIG),
    "checkpoints": ("checkpoints.yaml", DEFAULT_CHECKPOINTS_CONFIG),
    "monitoring": ("monitoring.yaml", DEFAULT_MONITORING_CONFIG),
    "notifications": ("notifications.yaml", DEFAULT_NOTIFICATIONS_CONFIG),
    "recovery": ("recovery.yaml", DEFAULT_RECOVERY_CONFIG),
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` onto ``base`` (override wins)."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_yaml(path: str | Path) -> dict[str, Any] | None:
    """Read a YAML file; return None if missing or empty."""
    config_path = Path(path)
    if not config_path.exists():
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return None
    return data


def _load_section(
    section: str,
    config_dir: str | Path = ORCHESTRATION_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load one config section, merging file data over defaults."""
    filename, default = _CONFIG_SECTIONS[section]
    path = Path(config_dir) / filename
    data = _read_yaml(path)
    if data is None:
        if required:
            raise FileNotFoundError(
                f"Orchestration config not found: {path} (section: {section})"
            )
        logger.warning("Orchestration config not found: %s — using defaults", path)
        return default
    logger.info("Loaded orchestration config from %s", path)
    return _deep_merge(default, data)


# ── Individual section loaders ────────────────────────────────────


def load_engine_config(
    config_dir: str | Path = ORCHESTRATION_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load engine config (engine settings + pipeline catalog)."""
    return _load_section("engine", config_dir, required=required)


def load_scheduler_config(
    config_dir: str | Path = ORCHESTRATION_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load scheduler config."""
    return _load_section("scheduler", config_dir, required=required)


def load_dependencies_config(
    config_dir: str | Path = ORCHESTRATION_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load dependency resolution config."""
    return _load_section("dependencies", config_dir, required=required)


def load_retries_config(
    config_dir: str | Path = ORCHESTRATION_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load default retry policy config."""
    return _load_section("retries", config_dir, required=required)


def load_checkpoints_config(
    config_dir: str | Path = ORCHESTRATION_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load checkpoint config."""
    return _load_section("checkpoints", config_dir, required=required)


def load_monitoring_config(
    config_dir: str | Path = ORCHESTRATION_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load monitoring config."""
    return _load_section("monitoring", config_dir, required=required)


def load_notifications_config(
    config_dir: str | Path = ORCHESTRATION_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load notification config."""
    return _load_section("notifications", config_dir, required=required)


def load_recovery_config(
    config_dir: str | Path = ORCHESTRATION_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load recovery config."""
    return _load_section("recovery", config_dir, required=required)


# ── Combined loader ───────────────────────────────────────────────


def load_all_orchestration_configs(
    config_dir: str | Path = ORCHESTRATION_CONFIG_DIR,
    required: bool = False,
) -> dict[str, dict[str, Any]]:
    """Load every orchestration config section.

    Returns a dict keyed by section name (``engine``, ``scheduler``,
    ``dependencies``, ``retries``, ``checkpoints``, ``monitoring``,
    ``notifications``, ``recovery``) suitable for constructing an
    ``OrchestrationEngine``.
    """
    return {
        section: _load_section(section, config_dir, required=required)
        for section in _CONFIG_SECTIONS
    }


def default_retry_policy(retries_cfg: dict[str, Any]) -> dict[str, Any]:
    """Extract the default retry policy dict from retries config."""
    retries = retries_cfg.get("retries", {})
    return {
        "max_retries": retries.get("default_max_retries", 3),
        "backoff_base_seconds": retries.get("backoff_base_seconds", 1.0),
        "backoff_multiplier": retries.get("backoff_multiplier", 2.0),
        "max_backoff_seconds": retries.get("max_backoff_seconds", 60.0),
        "timeout_seconds": retries.get("timeout_seconds", 3600),
        "retryable_errors": list(retries.get("retryable_errors", [])),
    }
