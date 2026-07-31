"""Unit tests for memory knowledge base."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from ai_company.memory.knowledge import KnowledgeBase
from ai_company.memory.models import MemoryEntry


@pytest.fixture
def kb() -> None:
    return KnowledgeBase()


class TestKnowledgeBase:
    def test_create(self, kb) -> None:
        assert kb.count() == 0

    def test_add_knowledge(self, kb) -> None:
        entry = kb.add_knowledge(
            title="Python",
            content={"topic": "Python"},
            summary="Python is a programming language",
            domain="engineering",
            tags=["python"],
        )
        assert entry.id is not None
        assert entry.title == "Python"
        assert kb.count() == 1

    def test_get_entry(self, kb) -> None:
        added = kb.add_knowledge(title="Test", content={"x": 1})
        retrieved = kb.get(added.id)
        assert retrieved is not None
        assert retrieved.title == "Test"

    def test_get_nonexistent(self, kb) -> None:
        assert kb.get("nope") is None

    def test_update(self, kb) -> None:
        added = kb.add_knowledge(title="Original", content={"x": 1})
        updated = kb.update(added.id, title="Updated", content={"x": 2})
        assert updated.title == "Updated"
        assert updated.content["x"] == 2

    def test_update_nonexistent(self, kb) -> None:
        assert kb.update("nope", title="x") is None

    def test_delete(self, kb) -> None:
        added = kb.add_knowledge(title="ToDelete", content={})
        assert kb.delete(added.id) is True
        assert kb.count() == 0

    def test_delete_nonexistent(self, kb) -> None:
        assert kb.delete("nope") is False

    def test_search(self, kb) -> None:
        kb.add_knowledge(
            title="Alice",
            content={},
            summary="Alice is an engineer",
            domain="engineering",
        )
        kb.add_knowledge(
            title="Bob", content={}, summary="Bob is a designer", domain="design"
        )
        results = kb.search("engineer")
        assert any("Alice" in r.title for r in results)

    def test_search_by_tag(self, kb) -> None:
        kb.add_knowledge(title="Urgent", content={}, tags=["urgent", "critical"])
        kb.add_knowledge(title="Normal", content={}, tags=["normal"])
        results = kb.search("", tags=["urgent"])
        assert any(r.title == "Urgent" for r in results)

    def test_get_by_domain(self, kb) -> None:
        kb.add_knowledge(title="E1", content={}, domain="engineering")
        kb.add_knowledge(title="E2", content={}, domain="engineering")
        kb.add_knowledge(title="D1", content={}, domain="design")
        results = kb.get_by_domain("engineering")
        assert len(results) == 2

    def test_get_by_tag(self, kb) -> None:
        kb.add_knowledge(title="A", content={}, tags=["python"])
        kb.add_knowledge(title="B", content={}, tags=["python"])
        results = kb.get_by_tag("python")
        assert len(results) == 2

    def test_add_relationship(self, kb) -> None:
        e1 = kb.add_knowledge(title="Entry1", content={})
        e2 = kb.add_knowledge(title="Entry2", content={})
        assert kb.add_relationship(e1.id, e2.id) is True
        related = kb.get_related(e1.id)
        assert any(r.id == e2.id for r in related)

    def test_clear(self, kb) -> None:
        kb.add_knowledge(title="A", content={})
        kb.add_knowledge(title="B", content={})
        kb.clear()
        assert kb.count() == 0

    def test_export_json(self, kb) -> None:
        kb.add_knowledge(title="ExportTest", content={"key": "val"}, domain="test")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "kb.json"
            result = kb.export_json(str(path))
            assert Path(result).exists()

    def test_get_statistics(self, kb) -> None:
        kb.add_knowledge(title="A", content={}, domain="eng")
        kb.add_knowledge(title="B", content={}, domain="eng")
        stats = kb.get_statistics()
        assert stats["total_entries"] == 2
        assert stats["domains"]["eng"] == 2

    def test_extract_from_memory(self, kb) -> None:
        from ai_company.memory.models import MemoryType

        memory = MemoryEntry(
            content={"name": "MyTitle"},
            summary="test entry",
            tags=["test"],
            memory_type=MemoryType.COMPANY,
        )
        entry = kb.extract_from_memory(memory, domain="test")
        assert entry is not None
        assert entry.title == "MyTitle"

    def test_disk_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "knowledge.json"
            kb1 = KnowledgeBase(storage_path=str(path))
            kb1.add_knowledge(title="Persist", content={}, domain="test")
            kb2 = KnowledgeBase(storage_path=str(path))
            results = kb2.search("Persist")
            assert len(results) >= 1
