"""Runtime configuration loading — reads the ``config/runtime/`` directory.

Sections:

- ``runtime`` — core settings (identity, state dir, concurrency, loop)
- ``startup`` — ordered startup sequence steps
- ``heartbeat`` — heartbeat cadence and failure thresholds
- ``scheduler`` — worker settings + declarative job catalog
- ``monitoring`` — metrics/events/audit/memory observability
- ``health`` — health check thresholds
- ``recovery`` — recovery policies for engines/processes
- ``diagnostics`` — diagnostic report collection settings

Each ``load_*_config(path)`` parses one file and merges it over built-in
defaults (missing files fall back to defaults with a warning), matching
the convention of ``ai_company.orchestration.config``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from ai_company.runtime.models import RuntimeConfig, RuntimeConfigError

logger = logging.getLogger(__name__)

RUNTIME_CONFIG_DIR = "config/runtime"

# ── Built-in defaults (mirror config/runtime/*.yaml) ───────────────

DEFAULT_RUNTIME_CONFIG: dict[str, Any] = {
    "runtime": {
        "name": "AI Enterprise Runtime",
        "version": "1.0",
        "environment": "development",
        "state_dir": "runtime",
        "persist_state": True,
        "max_workers": 4,
        "loop_interval_seconds": 1.0,
        "default_engine_timeout_seconds": 30.0,
        "audit_events": True,
    }
}

DEFAULT_STARTUP_CONFIG: dict[str, Any] = {
    "startup": {
        "required": True,
        "timeout_seconds": 60,
        "continue_on_error": False,
        "recover_persisted_state": True,
        "steps": [],
    }
}

DEFAULT_HEARTBEAT_CONFIG: dict[str, Any] = {
    "heartbeat": {
        "enabled": True,
        "interval_seconds": 5.0,
        "timeout_seconds": 15.0,
        "missed_beats_before_failure": 3,
        "check_interval_seconds": 1.0,
        "components": [],
    }
}

DEFAULT_SCHEDULER_CONFIG: dict[str, Any] = {
    "scheduler": {
        "enabled": True,
        "worker_interval_seconds": 1.0,
        "timezone": "UTC",
        "max_jobs": 1000,
        "jobs": {},
    }
}

DEFAULT_MONITORING_CONFIG: dict[str, Any] = {
    "monitoring": {
        "enabled": True,
        "metrics_interval_seconds": 5.0,
        "publish_events": True,
        "audit_events": True,
        "memory_records": True,
        "namespace": "runtime",
        "history_max_records": 1000,
    }
}

DEFAULT_HEALTH_CONFIG: dict[str, Any] = {
    "health": {
        "enabled": True,
        "check_interval_seconds": 5.0,
        "engine_timeout_seconds": 5.0,
        "cpu_percent_high": 80.0,
        "memory_percent_high": 80.0,
        "queue_size_warn": 100,
        "error_rate_high": 0.2,
    }
}

DEFAULT_RECOVERY_CONFIG: dict[str, Any] = {
    "recovery": {
        "enabled": True,
        "default_max_attempts": 3,
        "backoff_base_seconds": 1.0,
        "backoff_multiplier": 2.0,
        "max_backoff_seconds": 60.0,
        "restart_engines": True,
        "restart_processes": True,
        "reload_state": True,
        "policies": {
            "engine": {
                "max_attempts": 3,
                "actions": ["restart", "reload_state", "isolate"],
            },
            "process": {"max_attempts": 2, "actions": ["restart", "isolate"]},
        },
    }
}

DEFAULT_DIAGNOSTICS_CONFIG: dict[str, Any] = {
    "diagnostics": {
        "enabled": True,
        "collect_metrics": True,
        "collect_health": True,
        "collect_config": True,
        "max_report_items": 100,
    }
}

_CONFIG_SECTIONS: dict[str, tuple[str, dict[str, Any]]] = {
    "runtime": ("runtime.yaml", DEFAULT_RUNTIME_CONFIG),
    "startup": ("startup.yaml", DEFAULT_STARTUP_CONFIG),
    "heartbeat": ("heartbeat.yaml", DEFAULT_HEARTBEAT_CONFIG),
    "scheduler": ("scheduler.yaml", DEFAULT_SCHEDULER_CONFIG),
    "monitoring": ("monitoring.yaml", DEFAULT_MONITORING_CONFIG),
    "health": ("health.yaml", DEFAULT_HEALTH_CONFIG),
    "recovery": ("recovery.yaml", DEFAULT_RECOVERY_CONFIG),
    "diagnostics": ("diagnostics.yaml", DEFAULT_DIAGNOSTICS_CONFIG),
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
    config_dir: str | Path = RUNTIME_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load one config section, merging file data over defaults."""
    filename, default = _CONFIG_SECTIONS[section]
    path = Path(config_dir) / filename
    data = _read_yaml(path)
    if data is None:
        if required:
            raise RuntimeConfigError(
                f"Runtime config not found: {path} (section: {section})"
            )
        logger.warning("Runtime config not found: %s — using defaults", path)
        return default
    logger.info("Loaded runtime config from %s", path)
    return _deep_merge(default, data)


# ── Individual section loaders ─────────────────────────────────────


def load_runtime_config(
    config_dir: str | Path = RUNTIME_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load core runtime settings."""
    return _load_section("runtime", config_dir, required=required)


def load_startup_config(
    config_dir: str | Path = RUNTIME_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load the startup sequence."""
    return _load_section("startup", config_dir, required=required)


def load_heartbeat_config(
    config_dir: str | Path = RUNTIME_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load heartbeat settings."""
    return _load_section("heartbeat", config_dir, required=required)


def load_scheduler_config(
    config_dir: str | Path = RUNTIME_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load scheduler settings and the job catalog."""
    return _load_section("scheduler", config_dir, required=required)


def load_monitoring_config(
    config_dir: str | Path = RUNTIME_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load monitoring settings."""
    return _load_section("monitoring", config_dir, required=required)


def load_health_config(
    config_dir: str | Path = RUNTIME_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load health monitoring settings."""
    return _load_section("health", config_dir, required=required)


def load_recovery_config(
    config_dir: str | Path = RUNTIME_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load recovery settings."""
    return _load_section("recovery", config_dir, required=required)


def load_diagnostics_config(
    config_dir: str | Path = RUNTIME_CONFIG_DIR,
    required: bool = False,
) -> dict[str, Any]:
    """Load diagnostics settings."""
    return _load_section("diagnostics", config_dir, required=required)


# ── Combined loader ────────────────────────────────────────────────


def load_all_runtime_configs(
    config_dir: str | Path = RUNTIME_CONFIG_DIR,
    required: bool = False,
) -> dict[str, dict[str, Any]]:
    """Load every runtime config section.

    Returns a dict keyed by section name (``runtime``, ``startup``,
    ``heartbeat``, ``scheduler``, ``monitoring``, ``health``,
    ``recovery``, ``diagnostics``).
    """
    return {
        section: _load_section(section, config_dir, required=required)
        for section in _CONFIG_SECTIONS
    }


def build_runtime_config(
    config: dict[str, dict[str, Any]],
) -> RuntimeConfig:
    """Validate the ``runtime`` section into a :class:`RuntimeConfig`.

    Raises:
        RuntimeConfigError: If the runtime section is missing or invalid.
    """
    section = config.get("runtime", {})
    runtime_data = section.get("runtime", {}) if isinstance(section, dict) else {}
    if not isinstance(runtime_data, dict) or not runtime_data:
        raise RuntimeConfigError("Missing or empty 'runtime' config section")
    try:
        return RuntimeConfig(**runtime_data)
    except Exception as exc:
        raise RuntimeConfigError(f"Invalid runtime config: {exc}") from exc


class RuntimeConfiguration:
    """Holds the loaded runtime configuration sections.

    Supports hot reload: :meth:`reload` re-reads the YAML files from
    ``config_dir`` and replaces the section dicts (and the validated
    :class:`RuntimeConfig`).
    """

    def __init__(
        self,
        config: dict[str, dict[str, Any]] | None = None,
        config_dir: str | Path = RUNTIME_CONFIG_DIR,
        required: bool = False,
    ) -> None:
        self.config_dir = str(config_dir)
        self.required = required
        self.sections: dict[str, dict[str, Any]] = config or load_all_runtime_configs(
            self.config_dir, required=required
        )
        self.config = build_runtime_config(self.sections)
        self._reload_count = 0

    @property
    def reload_count(self) -> int:
        """Number of times the configuration has been reloaded."""
        return self._reload_count

    def reload(self) -> list[str]:
        """Re-read all sections from disk.

        Returns:
            The list of section names whose content changed.
        """
        fresh = load_all_runtime_configs(self.config_dir, required=self.required)
        changed: list[str] = []
        for section, data in fresh.items():
            if data != self.sections.get(section):
                changed.append(section)
        self.sections = fresh
        self.config = build_runtime_config(self.sections)
        self._reload_count += 1
        logger.info(
            "Runtime configuration reloaded (%d sections changed: %s)",
            len(changed),
            ", ".join(changed) or "none",
        )
        return changed

    def section(self, name: str) -> dict[str, Any]:
        """Return one section's inner dict (e.g. ``sections['scheduler']['scheduler']``)."""
        data = self.sections.get(name, {})
        return data.get(name, {}) if isinstance(data, dict) else {}

    def to_dict(self) -> dict[str, Any]:
        """Return the full configuration as plain dicts."""
        return {name: dict(data) for name, data in self.sections.items()}
