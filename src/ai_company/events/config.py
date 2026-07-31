"""Event Bus configuration loader — reads YAML config files.

Provides two loaders matching the two config files:

- ``load_event_registry(path)`` — loads ``config/events/event_registry.yaml``
  to pre-configure the ``EventTypeRegistry`` with custom metadata, defaults,
  and owner mappings.

- ``load_event_pipeline_config(path)`` — loads ``config/events/event_pipeline.yaml``
  and returns a dictionary that can be passed to ``EventBus`` initializer.

Usage::

    from ai_company.events.config import load_event_pipeline_config, load_event_registry

    # Apply registry metadata to an EventTypeRegistry
    registry_config = load_event_registry("config/events/event_registry.yaml")
    registry_config.apply_to(registry)

    # Build EventBus from pipeline config
    config = load_event_pipeline_config("config/events/event_pipeline.yaml")
    bus = EventBus(**config["core"])
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from ai_company.events.models import EventPriority, EventType
from ai_company.events.registry import EventTypeRegistry

logger = logging.getLogger(__name__)

# ── Priority string → enum mapping ──────────────────────────────
_PRIORITY_MAP: dict[str, EventPriority] = {
    "critical": EventPriority.CRITICAL,
    "high": EventPriority.HIGH,
    "normal": EventPriority.NORMAL,
    "low": EventPriority.LOW,
    "background": EventPriority.BACKGROUND,
}


class EventRegistryConfig:
    """Loaded event registry configuration that can be applied to a registry.

    Wraps the parsed YAML from ``event_registry.yaml`` and provides
    methods to apply metadata, defaults, and owner mappings to an
    ``EventTypeRegistry`` instance.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self.version: str = data.get("version", "1.0")
        self.description: str = data.get("description", "")
        self.defaults: dict[str, Any] = data.get("defaults", {})
        self.event_types: dict[str, dict[str, Any]] = data.get("event_types", {})
        self.domains: dict[str, dict[str, Any]] = data.get("domains", {})
        self.owners: dict[str, dict[str, Any]] = data.get("owners", {})

    def apply_to(self, registry: EventTypeRegistry) -> None:
        """Apply registry YAML metadata onto an existing EventTypeRegistry.

        This enriches every registered ``EventType`` with:
        - description
        - default_priority
        - ttl_seconds
        - max_retries
        - owner
        - delivery_mode
        - tags
        """
        defaults = self.defaults
        for et in EventType:
            et_value = et.value
            entry = self.event_types.get(et_value, {})
            metadata = registry.get_metadata(et_value) or {}

            merged = {
                "description": entry.get(
                    "description", metadata.get("description", "")
                ),
                "default_priority": _resolve_priority(
                    entry.get("default_priority", defaults.get("priority", "normal"))
                ),
                "ttl_seconds": entry.get("ttl_seconds", defaults.get("ttl_seconds")),
                "max_retries": entry.get("max_retries", defaults.get("max_retries", 3)),
                "owner": entry.get("owner", ""),
                "delivery_mode": entry.get(
                    "delivery_mode", defaults.get("delivery_mode", "AT_LEAST_ONCE")
                ),
                "tags": entry.get("tags", []),
                "persistent": entry.get("persistent", True),
            }
            metadata.update(merged)

            # Update domain label from domains section
            domain = et_value.split(".")[0]
            domain_info = self.domains.get(domain, {})
            metadata["domain_label"] = domain_info.get(
                "label", metadata.get("domain_label", "Unknown")
            )

    def get_event_config(self, event_type: str) -> dict[str, Any]:
        """Get configuration for a specific event type."""
        entry = self.event_types.get(event_type, {})
        defaults = self.defaults
        return {
            "description": entry.get("description", ""),
            "default_priority": _resolve_priority(
                entry.get("default_priority", defaults.get("priority", "normal"))
            ),
            "ttl_seconds": entry.get("ttl_seconds", defaults.get("ttl_seconds")),
            "max_retries": entry.get("max_retries", defaults.get("max_retries", 3)),
            "owner": entry.get("owner", ""),
            "delivery_mode": entry.get(
                "delivery_mode", defaults.get("delivery_mode", "AT_LEAST_ONCE")
            ),
            "tags": entry.get("tags", []),
            "persistent": entry.get("persistent", True),
        }

    def get_owner_engine(self, owner_name: str) -> str | None:
        """Get the engine class name for a logical owner."""
        owner_info = self.owners.get(owner_name)
        if owner_info:
            return owner_info.get("engine")
        return None

    def get_owner_publisher(self, owner_name: str) -> str | None:
        """Get the publisher source name for a logical owner."""
        owner_info = self.owners.get(owner_name)
        if owner_info:
            return owner_info.get("publisher")
        return None

    def list_domains(self) -> dict[str, str]:
        """Return domain → label mapping, ordered by the YAML ``order``."""
        sorted_domains = sorted(
            self.domains.items(), key=lambda item: item[1].get("order", 99)
        )
        return {k: v["label"] for k, v in sorted_domains}

    def list_owners(self) -> list[str]:
        """Return list of all registered logical owner names."""
        return list(self.owners.keys())


def load_event_registry(
    path: str | Path = "config/events/event_registry.yaml",
) -> EventRegistryConfig:
    """Load event registry YAML and return an ``EventRegistryConfig``.

    Args:
        path: Path to the ``event_registry.yaml`` file.

    Returns:
        An ``EventRegistryConfig`` wrapping the parsed data.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Event registry config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError(f"Empty event registry config: {config_path}")

    logger.info("Loaded event registry from %s", config_path)
    return EventRegistryConfig(data)


def load_event_pipeline_config(
    path: str | Path = "config/events/event_pipeline.yaml",
) -> dict[str, Any]:
    """Load event pipeline YAML config and return a flattened dict.

    The returned dict has top-level keys matching ``EventBus.__init__``
    parameters and additional sections for middleware, retry, TTL, etc.

    Args:
        path: Path to the ``event_pipeline.yaml`` file.

    Returns:
        A dictionary with pipeline configuration sections.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Event pipeline config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError(f"Empty event pipeline config: {config_path}")

    logger.info("Loaded event pipeline config from %s", config_path)

    # Merge into a flat-enough structure for consumption
    core = data.get("core", {})
    storage = data.get("storage", {})
    result: dict[str, Any] = {
        "core": core,
        "storage": storage,
        "middleware": data.get("middleware", []),
        "retry": data.get("retry", {}),
        "dead_letter": data.get("dead_letter", {}),
        "delivery": data.get("delivery", {}),
        "ttl": data.get("ttl", {}),
        "replay": data.get("replay", {}),
        "priority": data.get("priority", {}),
        "observability": data.get("observability", {}),
        "features": data.get("features", {}),
    }

    # Promote commonly-used core+storage fields to top-level
    result["storage_path"] = storage.get("store_path", "events/store.jsonl")
    result["dead_letter_path"] = storage.get(
        "dead_letter_path", "events/dead_letter.jsonl"
    )
    result["max_history"] = core.get("max_history", 10000)
    result["max_workers"] = core.get("max_workers", 4)
    result["enable_persistence"] = core.get("enable_persistence", True)
    result["auto_start"] = core.get("auto_start", False)

    return result


def _resolve_priority(value: str | EventPriority | None) -> EventPriority:
    """Convert a string or enum to EventPriority."""
    if isinstance(value, EventPriority):
        return value
    if isinstance(value, str):
        return _PRIORITY_MAP.get(value.lower(), EventPriority.NORMAL)
    return EventPriority.NORMAL
