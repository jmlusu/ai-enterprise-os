"""Unit tests for Event Bus configuration loader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ai_company.events.config import load_event_pipeline_config, load_event_registry
from ai_company.events.models import EventPriority
from ai_company.events.registry import EventTypeRegistry

# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def sample_registry_yaml(tmp_path: Path) -> Path:
    """Create a minimal event_registry.yaml for testing."""
    data = {
        "version": "1.0",
        "description": "Test registry",
        "defaults": {
            "priority": "normal",
            "ttl_seconds": 3600,
            "max_retries": 3,
        },
        "event_types": {
            "company.created": {
                "description": "Test company created",
                "default_priority": "high",
                "ttl_seconds": 7200,
                "owner": "bootstrap",
                "tags": ["test"],
            },
            "workflow.started": {
                "description": "Test workflow started",
                "default_priority": "normal",
                "owner": "workflow",
                "tags": ["test"],
            },
        },
        "domains": {
            "company": {"label": "Test Company", "order": 1},
            "workflow": {"label": "Test Workflow", "order": 2},
        },
        "owners": {
            "bootstrap": {"engine": "BootstrapEngine", "publisher": "bootstrap"},
            "workflow": {"engine": "WorkflowEngine", "publisher": "workflow"},
        },
    }
    path = tmp_path / "event_registry.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return path


@pytest.fixture
def sample_pipeline_yaml(tmp_path: Path) -> Path:
    """Create a minimal event_pipeline.yaml for testing."""
    data = {
        "version": "1.0",
        "description": "Test pipeline",
        "core": {
            "max_history": 5000,
            "max_workers": 2,
            "enable_persistence": False,
            "auto_start": True,
        },
        "storage": {
            "store_path": "test_store.jsonl",
            "dead_letter_path": "test_dlq.jsonl",
        },
        "middleware": [
            {"name": "logging", "enabled": True, "config": {"log_level": "DEBUG"}},
            {"name": "metrics", "enabled": True, "config": {}},
        ],
        "retry": {"default_max_retries": 5, "backoff_base_seconds": 2.0},
        "features": {"persistence": False, "replay": True},
    }
    path = tmp_path / "event_pipeline.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return path


# ── EventRegistryConfig ──────────────────────────────────────────


def test_load_event_registry(sample_registry_yaml: Path) -> None:
    """Test loading registry YAML returns correct structure."""
    cfg = load_event_registry(sample_registry_yaml)
    assert cfg.version == "1.0"
    assert len(cfg.event_types) == 2
    assert len(cfg.domains) == 2
    assert len(cfg.owners) == 2


def test_get_event_config(sample_registry_yaml: Path) -> None:
    """Test retrieving config for a specific event type."""
    cfg = load_event_registry(sample_registry_yaml)

    cc = cfg.get_event_config("company.created")
    assert cc["description"] == "Test company created"
    assert cc["default_priority"] == EventPriority.HIGH
    assert cc["ttl_seconds"] == 7200
    assert cc["owner"] == "bootstrap"
    assert cc["tags"] == ["test"]
    assert cc["persistent"] is True

    ws = cfg.get_event_config("workflow.started")
    assert ws["default_priority"] == EventPriority.NORMAL
    assert ws["owner"] == "workflow"


def test_get_event_config_uses_defaults(sample_registry_yaml: Path) -> None:
    """Test that missing fields fall back to defaults."""
    cfg = load_event_registry(sample_registry_yaml)
    ws = cfg.get_event_config("workflow.started")
    assert ws["ttl_seconds"] == 3600  # from defaults
    assert ws["max_retries"] == 3  # from defaults


def test_apply_to_registry(sample_registry_yaml: Path) -> None:
    """Test applying registry config to an EventTypeRegistry."""
    cfg = load_event_registry(sample_registry_yaml)
    reg = EventTypeRegistry()
    cfg.apply_to(reg)

    meta = reg.get_metadata("company.created")
    assert meta is not None
    assert meta["description"] == "Test company created"
    assert meta["default_priority"] == EventPriority.HIGH
    assert meta["owner"] == "bootstrap"
    assert meta["tags"] == ["test"]

    # Domain label should be updated
    assert meta["domain_label"] == "Test Company"


def test_get_owner_engine(sample_registry_yaml: Path) -> None:
    """Test retrieving engine name for an owner."""
    cfg = load_event_registry(sample_registry_yaml)
    assert cfg.get_owner_engine("bootstrap") == "BootstrapEngine"
    assert cfg.get_owner_engine("workflow") == "WorkflowEngine"
    assert cfg.get_owner_engine("nonexistent") is None


def test_get_owner_publisher(sample_registry_yaml: Path) -> None:
    """Test retrieving publisher source for an owner."""
    cfg = load_event_registry(sample_registry_yaml)
    assert cfg.get_owner_publisher("bootstrap") == "bootstrap"
    assert cfg.get_owner_publisher("nonexistent") is None


def test_list_domains(sample_registry_yaml: Path) -> None:
    """Test listing domains in order."""
    cfg = load_event_registry(sample_registry_yaml)
    domains = cfg.list_domains()
    assert domains["company"] == "Test Company"
    assert domains["workflow"] == "Test Workflow"
    # Should be in order
    assert list(domains.keys()) == ["company", "workflow"]


def test_list_owners(sample_registry_yaml: Path) -> None:
    """Test listing owners."""
    cfg = load_event_registry(sample_registry_yaml)
    owners = cfg.list_owners()
    assert "bootstrap" in owners
    assert "workflow" in owners


def test_load_registry_file_not_found() -> None:
    """Test error on missing file."""
    with pytest.raises(FileNotFoundError):
        load_event_registry("nonexistent.yaml")


# ── Event Pipeline Config ────────────────────────────────────────


def test_load_pipeline_config(sample_pipeline_yaml: Path) -> None:
    """Test loading pipeline YAML returns correct structure."""
    cfg = load_event_pipeline_config(sample_pipeline_yaml)
    assert cfg["max_history"] == 5000
    assert cfg["max_workers"] == 2
    assert cfg["enable_persistence"] is False
    assert cfg["auto_start"] is True
    assert cfg["storage_path"] == "test_store.jsonl"
    assert cfg["dead_letter_path"] == "test_dlq.jsonl"


def test_pipeline_middleware(sample_pipeline_yaml: Path) -> None:
    """Test middleware entries are parsed."""
    cfg = load_event_pipeline_config(sample_pipeline_yaml)
    middleware = cfg["middleware"]
    assert len(middleware) == 2
    assert middleware[0]["name"] == "logging"
    assert middleware[1]["name"] == "metrics"


def test_pipeline_retry(sample_pipeline_yaml: Path) -> None:
    """Test retry config is parsed."""
    cfg = load_event_pipeline_config(sample_pipeline_yaml)
    assert cfg["retry"]["default_max_retries"] == 5
    assert cfg["retry"]["backoff_base_seconds"] == 2.0


def test_pipeline_features(sample_pipeline_yaml: Path) -> None:
    """Test feature toggles are parsed."""
    cfg = load_event_pipeline_config(sample_pipeline_yaml)
    assert cfg["features"]["persistence"] is False
    assert cfg["features"]["replay"] is True


def test_pipeline_file_not_found() -> None:
    """Test error on missing file."""
    with pytest.raises(FileNotFoundError):
        load_event_pipeline_config("nonexistent.yaml")


# ── Real config files ────────────────────────────────────────────


def test_real_registry_file() -> None:
    """Test loading the actual event_registry.yaml from config/."""
    cfg = load_event_registry("config/events/event_registry.yaml")
    assert len(cfg.event_types) == 45  # All EventType enum values
    assert (
        cfg.get_event_config("system.startup")["default_priority"]
        == EventPriority.CRITICAL
    )
    assert (
        cfg.get_event_config("decision.escalated")["default_priority"]
        == EventPriority.CRITICAL
    )
    assert cfg.get_event_config("system.error")["ttl_seconds"] is None  # Never expires
    assert cfg.get_event_config("audit.recorded")["persistent"] is True

    # All 16 domains present, in order
    domains = cfg.list_domains()
    assert len(domains) == 16
    assert list(domains.keys())[0] == "company"


def test_real_pipeline_file() -> None:
    """Test loading the actual event_pipeline.yaml from config/."""
    cfg = load_event_pipeline_config("config/events/event_pipeline.yaml")
    assert cfg["max_history"] == 10000
    assert cfg["max_workers"] == 4
    assert cfg["enable_persistence"] is True

    # 5 middleware entries, 3 enabled
    middleware = cfg["middleware"]
    enabled = [m for m in middleware if m["enabled"]]
    assert len(enabled) == 3  # logging, validation, metrics
    assert len([m for m in middleware if not m["enabled"]]) == 2  # rate_limiter, auth

    assert cfg["retry"]["default_max_retries"] == 3
    assert cfg["features"]["persistence"] is True
    assert cfg["features"]["middleware"] is True
