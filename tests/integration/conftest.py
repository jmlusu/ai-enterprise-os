"""Shared fixtures for orchestration integration tests.

Builds a fully wired orchestration engine against the real engine
implementations (Registry, Generator, Validator, Workflow, Decision,
Memory, Audit, Event Bus) with all file output redirected into the
per-test temporary directory.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from ai_company.audit.engine import AuditEngine
from ai_company.company.generator import CompanyGenerator
from ai_company.decision.engine import DecisionEngine
from ai_company.events.bus import EventBus
from ai_company.events.models import Event
from ai_company.memory.engine import MemoryEngine
from ai_company.orchestration import Coordinator, OrchestrationEngine
from ai_company.orchestrator.workflow import WorkflowManager
from ai_company.registry.registry import RegistryEngine
from ai_company.validator.engine import ValidatorEngine


@pytest.fixture
def event_bus() -> Iterator[EventBus]:
    bus = EventBus()
    bus.start()
    yield bus
    bus.stop()


@pytest.fixture
def orchestration(tmp_path, event_bus: EventBus) -> Iterator[OrchestrationEngine]:
    memory = MemoryEngine(storage_path=str(tmp_path / "memory" / "store.jsonl"))
    audit = AuditEngine(log_path=str(tmp_path / "audit" / "audit.jsonl"))
    coordinator = Coordinator(
        {
            "registry": RegistryEngine(),
            "generator": CompanyGenerator(output_dir=tmp_path / "generated"),
            "validator": ValidatorEngine(),
            "workflow": WorkflowManager(),
            "memory": memory,
            "decision": DecisionEngine(),
            "audit": audit,
            "event_bus": event_bus,
        }
    )
    engine = OrchestrationEngine(
        coordinator=coordinator,
        event_bus=event_bus,
        memory_engine=memory,
    )
    yield engine
    engine.close()


@pytest.fixture
def collected_events(event_bus: EventBus) -> list[Event]:
    captured: list[Event] = []

    def handler(event: Event) -> None:
        captured.append(event)

    event_bus.subscribe(
        name="test-capture",
        handler=handler,
        description="Capture orchestration events for assertions",
    )
    return captured
