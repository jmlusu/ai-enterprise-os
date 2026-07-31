"""Unit tests for memory engine."""

from __future__ import annotations

import tempfile
from datetime import UTC
from pathlib import Path

import yaml

from ai_company.memory.engine import MemoryEngine
from ai_company.memory.models import (
    MemoryConfig,
    MemoryNamespace,
    MemoryType,
)


class TestMemoryEngine:
    def test_create(self) -> None:
        engine = MemoryEngine()
        assert engine.get_statistics()["total_memories"] == 0

    def test_save_returns_entry(self) -> None:
        engine = MemoryEngine()
        entry = engine.save({"key": "value"}, memory_type="company", tags=["test"])
        assert entry.id is not None
        assert entry.memory_type == MemoryType.COMPANY

    def test_save_with_namespace(self) -> None:
        engine = MemoryEngine()
        entry = engine.save({"x": 1}, namespace="project")
        assert entry.namespace == MemoryNamespace.PROJECT

    def test_save_with_importance(self) -> None:
        engine = MemoryEngine()
        entry = engine.save({"x": 1}, importance=0.9)
        assert entry.importance == 0.9

    def test_retrieve(self) -> None:
        engine = MemoryEngine()
        saved = engine.save({"val": 42})
        retrieved = engine.retrieve(saved.id)
        assert retrieved.content["val"] == 42

    def test_retrieve_nonexistent(self) -> None:
        assert MemoryEngine().retrieve("nope") is None

    def test_update_content(self) -> None:
        engine = MemoryEngine()
        entry = engine.save({"val": 1}, memory_type="system")
        assert entry.version == 1
        updated = engine.update(entry.id, content={"val": 2})
        assert updated.content["val"] == 2
        assert updated.version == 2

    def test_update_importance(self) -> None:
        engine = MemoryEngine()
        entry = engine.save({"x": 1})
        updated = engine.update(entry.id, importance=0.9)
        assert updated.importance == 0.9

    def test_update_nonexistent(self) -> None:
        assert MemoryEngine().update("nope", content={}) is None

    def test_delete(self) -> None:
        engine = MemoryEngine()
        entry = engine.save({"x": 1})
        assert engine.delete(entry.id) is True
        assert engine.retrieve(entry.id) is None

    def test_search_by_text(self) -> None:
        engine = MemoryEngine()
        engine.save({"name": "unique_search_target"}, tags=["searchable"])
        results = engine.search("unique_search_target")
        assert len(results) >= 1

    def test_search_with_filters(self) -> None:
        engine = MemoryEngine()
        engine.save({"data": "hello"}, memory_type="company", tags=["ftest"])
        results = engine.search("hello", tags=["ftest"])
        assert len(results) >= 1

    def test_search_limit(self) -> None:
        engine = MemoryEngine()
        for i in range(5):
            engine.save({"idx": i}, tags=["limit_test"])
        results = engine.search("limit_test", limit=3)
        assert len(results) <= 3

    def test_retrieve_by_type(self) -> None:
        engine = MemoryEngine()
        engine.save({"a": 1}, memory_type="company")
        engine.save({"b": 2}, memory_type="system")
        entries = engine.retrieve_by_type("company")
        assert len(entries) >= 1

    def test_retrieve_by_namespace(self) -> None:
        engine = MemoryEngine()
        engine.save({"x": 1}, namespace="project")
        engine.save({"y": 2}, namespace="company")
        entries = engine.retrieve_by_namespace("project")
        assert len(entries) >= 1

    def test_archive_lifecycle(self) -> None:
        engine = MemoryEngine()
        entry = engine.save({"x": 1}, memory_type="system")
        assert engine.archive(entry.id) is True
        assert engine.retrieve(entry.id).archived is True
        assert engine.unarchive(entry.id) is True
        assert engine.retrieve(entry.id).archived is False

    def test_archive_older_than(self) -> None:
        from datetime import datetime, timedelta

        engine = MemoryEngine()
        entry = engine.save({"old": True}, memory_type="system")
        entry.created_at = datetime.now(UTC) - timedelta(days=100)
        engine.store.save(entry)
        assert engine.archive_older_than(days=30) >= 1

    def test_snapshot_and_restore(self) -> None:
        engine = MemoryEngine()
        engine.save({"a": 1})
        engine.save({"b": 2})
        snap_id = engine.snapshot("test_snap")
        assert snap_id is not None

        engine.clear()
        assert engine.get_statistics()["total_memories"] == 0

        count = engine.restore_snapshot(snap_id)
        assert count >= 2

    def test_list_snapshots(self) -> None:
        import time

        engine = MemoryEngine()
        engine.snapshot("snap1")
        time.sleep(1.1)
        engine.snapshot("snap2")
        snaps = engine.list_snapshots()
        assert len(snaps) >= 2

    def test_delete_snapshot(self) -> None:
        engine = MemoryEngine()
        snap_id = engine.snapshot("to_delete")
        assert engine.delete_snapshot(snap_id) is True

    def test_clear(self) -> None:
        engine = MemoryEngine()
        engine.save({"x": 1})
        engine.save({"y": 2})
        engine.clear()
        assert engine.get_statistics()["total_memories"] == 0

    def test_statistics(self) -> None:
        engine = MemoryEngine()
        engine.save({"a": 1}, memory_type="company")
        engine.save({"b": 2}, memory_type="system")
        stats = engine.get_statistics()
        assert stats["total_memories"] >= 2
        assert stats["by_type"].get("company", 0) >= 1
        assert stats["by_type"].get("system", 0) >= 1
        assert "average_importance" in stats

    def test_export_to_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "export.json"
            engine = MemoryEngine()
            engine.save({"x": 1})
            result = engine.export_to_json(str(path))
            assert Path(result).exists()

    def test_summarize(self) -> None:
        engine = MemoryEngine()
        entry = engine.save({"data": "alpha"}, memory_type="company")
        summary = engine.summarize([entry.id])
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_summarize_by_type(self) -> None:
        engine = MemoryEngine()
        engine.save({"x": 1}, memory_type="company")
        result = engine.summarize_by_type(MemoryType.COMPANY)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_add_knowledge(self) -> None:
        engine = MemoryEngine()
        entry = engine.add_knowledge(title="Test", content={"key": "val"})
        assert entry.title == "Test"

    def test_search_knowledge(self) -> None:
        engine = MemoryEngine()
        engine.add_knowledge(
            title="Python KB", content={"topic": "python"}, summary="Python lang"
        )
        results = engine.search_knowledge("Python")
        assert len(results) >= 1

    def test_get_children(self) -> None:
        engine = MemoryEngine()
        parent = engine.save({"p": True})
        child = engine.save({"c": True}, parent_id=parent.id)
        children = engine.get_children(parent.id)
        assert any(e.id == child.id for e in children)

    def test_apply_retention_policy(self) -> None:
        engine = MemoryEngine()
        engine.save({"x": 1})
        result = engine.apply_retention_policy()
        assert "archived" in result
        assert "purged" in result

    def test_config_based_engine(self) -> None:
        config = MemoryConfig(
            storage_path="/tmp/test_mem.jsonl", enable_embeddings=False
        )
        engine = MemoryEngine(config=config)
        entry = engine.save({"test": "config"})
        assert entry is not None

    def test_from_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "memory.yaml"
            with open(config_path, "w") as f:
                yaml.dump(
                    {
                        "version": "1.0",
                        "storage_path": str(Path(tmpdir) / "store.jsonl"),
                        "default_importance": 0.6,
                    },
                    f,
                )
            engine = MemoryEngine.from_config(config_path)
            assert engine is not None
