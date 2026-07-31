"""Unit tests for memory store."""

from __future__ import annotations

import tempfile
from pathlib import Path


from ai_company.memory.models import MemoryEntry, MemoryType, MemoryNamespace
from ai_company.memory.store import MemoryStore


class TestMemoryStore:
    def test_create(self) -> None:
        assert MemoryStore() is not None

    def test_save_and_get(self) -> None:
        store = MemoryStore()
        entry = MemoryEntry(id="t1", content={"a": 1})
        store.save(entry)
        assert store.get("t1").content["a"] == 1

    def test_get_nonexistent(self) -> None:
        assert MemoryStore().get("nope") is None

    def test_delete(self) -> None:
        store = MemoryStore()
        store.save(MemoryEntry(id="d1", content={}))
        assert store.delete("d1") is True
        assert store.get("d1") is None

    def test_delete_nonexistent(self) -> None:
        assert MemoryStore().delete("nope") is False

    def test_update(self) -> None:
        store = MemoryStore()
        entry = MemoryEntry(id="u1", content={"val": 1})
        store.save(entry)
        entry.content["val"] = 2
        store.save(entry)
        assert store.get("u1").content["val"] == 2

    def test_get_all(self) -> None:
        store = MemoryStore()
        store.save(MemoryEntry(id="a", content={}))
        store.save(MemoryEntry(id="b", content={}))
        assert len(store.get_all()) == 2

    def test_get_by_type(self) -> None:
        store = MemoryStore()
        store.save(MemoryEntry(id="c1", memory_type=MemoryType.COMPANY, content={}))
        store.save(MemoryEntry(id="c2", memory_type=MemoryType.COMPANY, content={}))
        store.save(MemoryEntry(id="s1", memory_type=MemoryType.SYSTEM, content={}))
        assert len(store.get_by_type(MemoryType.COMPANY)) == 2

    def test_get_by_namespace(self) -> None:
        store = MemoryStore()
        store.save(MemoryEntry(id="ns1", namespace=MemoryNamespace.COMPANY, content={}))
        store.save(MemoryEntry(id="ns2", namespace=MemoryNamespace.COMPANY, content={}))
        assert len(store.get_by_namespace(MemoryNamespace.COMPANY)) == 2

    def test_get_by_tag(self) -> None:
        store = MemoryStore()
        store.save(MemoryEntry(id="tag1", tags=["urgent"], content={}))
        store.save(MemoryEntry(id="tag2", tags=["urgent"], content={}))
        assert len(store.get_by_tag("urgent")) == 2

    def test_get_children(self) -> None:
        store = MemoryStore()
        store.save(MemoryEntry(id="parent", content={}))
        store.save(MemoryEntry(id="child", parent_id="parent", content={}))
        children = store.get_children("parent")
        assert any(c.id == "child" for c in children)

    def test_count(self) -> None:
        store = MemoryStore()
        assert store.count() == 0
        store.save(MemoryEntry(content={}))
        assert store.count() == 1

    def test_clear(self) -> None:
        store = MemoryStore()
        store.save(MemoryEntry(id="c1", content={}))
        store.clear()
        assert store.count() == 0

    def test_search_by_text(self) -> None:
        store = MemoryStore()
        store.save(MemoryEntry(id="s1", content={"name": "unique_target"}, tags=["t"]))
        results = store.search("unique_target")
        assert any(r.id == "s1" for r in results)

    def test_search_by_tag_filter(self) -> None:
        store = MemoryStore()
        store.save(MemoryEntry(id="f1", content={"x": 1}, tags=["important"]))
        store.save(MemoryEntry(id="f2", content={"x": 2}, tags=["normal"]))
        results = store.search("x", tags=["important"])
        assert any(r.id == "f1" for r in results)
        assert not any(r.id == "f2" for r in results)

    def test_search_scoring(self) -> None:
        store = MemoryStore()
        store.save(MemoryEntry(id="m1", content={"title": "exact match"}, tags=["a"]))
        results = store.search("exact")
        assert any(r.id == "m1" for r in results)

    def test_type_index(self) -> None:
        store = MemoryStore()
        store.save(MemoryEntry(id="ix1", memory_type=MemoryType.DECISION, content={}))
        store.save(MemoryEntry(id="ix2", memory_type=MemoryType.COMPANY, content={}))
        assert "ix1" in store._type_index.get(MemoryType.DECISION, set())
        assert "ix2" not in store._type_index.get(MemoryType.DECISION, set())

    def test_disk_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "store.jsonl"
            store1 = MemoryStore(storage_path=str(path))
            store1.save(MemoryEntry(id="disk1", content={"k": "v"}, tags=["t"]))
            store1._append_to_disk(store1.get("disk1"))
            # Re-read from disk
            store2 = MemoryStore(storage_path=str(path))
            assert store2.get("disk1") is not None
            assert store2.get("disk1").content["k"] == "v"
