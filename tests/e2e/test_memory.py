"""Memory engine e2e tests."""

from ai_company.memory.engine import MemoryEngine, MemoryEntry, MemoryType
from ai_company.memory.store import MemoryStore


class TestE2EMemory:
    def test_memory_engine_creates(self) -> None:
        engine = MemoryEngine()
        assert engine is not None

    def test_memory_save_and_retrieve(self) -> None:
        engine = MemoryEngine()
        entry = engine.save({"key": "value"}, memory_type="company", tags=["test"])
        assert entry.id is not None
        retrieved = engine.retrieve(entry.id)
        assert retrieved is not None
        assert retrieved.content["key"] == "value"

    def test_memory_search(self) -> None:
        engine = MemoryEngine()
        engine.save({"name": "test"}, memory_type="company", tags=["search_test"])
        results = engine.search("test", tags=["search_test"])
        assert len(results) >= 1

    def test_memory_update(self) -> None:
        engine = MemoryEngine()
        entry = engine.save({"val": 1}, memory_type="system")
        updated = engine.update(entry.id, content={"val": 2})
        assert updated is not None
        assert updated.content["val"] == 2

    def test_memory_delete(self) -> None:
        engine = MemoryEngine()
        entry = engine.save({"val": 1}, memory_type="system")
        assert engine.delete(entry.id)

    def test_memory_snapshot(self) -> None:
        engine = MemoryEngine()
        snap_id = engine.snapshot("test_snap")
        assert snap_id is not None

    def test_memory_statistics(self) -> None:
        engine = MemoryEngine()
        stats = engine.get_statistics()
        assert "total_memories" in stats
        assert "by_type" in stats

    def test_memory_types(self) -> None:
        for mt in ["company", "executive", "department", "agent", "workflow"]:
            assert mt in [e.value for e in MemoryType]

    def test_memory_store_in_memory(self) -> None:
        store = MemoryStore()
        entry = MemoryEntry(id="test1", memory_type=MemoryType.SYSTEM, content={"a": 1})
        store.save(entry)
        assert store.get("test1") is not None

    def test_memory_archive(self) -> None:
        engine = MemoryEngine()
        entry = engine.save({"x": 1}, memory_type="system")
        assert engine.archive(entry.id)

    def test_memory_retrieve_by_type(self) -> None:
        engine = MemoryEngine()
        engine.save({"x": 1}, memory_type="company", tags=["rtype"])
        results = engine.retrieve_by_type("company")
        assert len(results) >= 1

    def test_memory_clear(self) -> None:
        engine = MemoryEngine()
        engine.save({"x": 1}, memory_type="system")
        engine.clear()
        stats = engine.get_statistics()
        assert stats["total_memories"] == 0
