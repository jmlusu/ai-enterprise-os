"""Unit tests for memory archiver."""

from __future__ import annotations

import tempfile
from datetime import UTC
from pathlib import Path

import pytest

from ai_company.memory.archive import MemoryArchiver
from ai_company.memory.models import MemoryEntry, MemoryNamespace, MemoryType
from ai_company.memory.store import MemoryStore


@pytest.fixture
def store() -> None:
    s = MemoryStore()
    s.save(MemoryEntry(id="a1", content={"x": 1}, memory_type=MemoryType.SYSTEM))
    s.save(MemoryEntry(id="a2", content={"y": 2}, memory_type=MemoryType.COMPANY))
    s.save(MemoryEntry(id="a3", content={"z": 3}, memory_type=MemoryType.KNOWLEDGE))
    return s


@pytest.fixture
def archiver(store) -> None:
    return MemoryArchiver(store)


class TestMemoryArchiver:
    def test_archive_entry(self, archiver, store) -> None:
        assert archiver.archive("a1") is True
        assert store.get("a1").archived is True

    def test_archive_nonexistent(self, archiver) -> None:
        assert archiver.archive("nope") is False

    def test_unarchive_entry(self, archiver, store) -> None:
        archiver.archive("a1")
        assert archiver.unarchive("a1") is True
        assert store.get("a1").archived is False

    def test_unarchive_nonexistent(self, archiver) -> None:
        assert archiver.unarchive("nope") is False

    def test_archive_by_type(self, archiver, store) -> None:
        count = archiver.archive_by_type(MemoryType.SYSTEM)
        assert count == 1
        assert store.get("a1").archived is True

    def test_archive_by_namespace(self, archiver, store) -> None:
        # Add a global entry (default)
        store.save(MemoryEntry(id="ns1", namespace=MemoryNamespace.GLOBAL, content={}))
        count = archiver.archive_by_namespace("global")
        assert count >= 1

    def test_archive_older_than(self, archiver, store) -> None:
        from datetime import datetime, timedelta

        old = store.get("a3")
        old.created_at = datetime.now(UTC) - timedelta(days=100)
        store.save(old)
        assert archiver.archive_older_than(days=30) >= 1

    def test_archive_by_importance(self, archiver, store) -> None:
        low = MemoryEntry(id="low1", content={}, importance=0.1)
        store.save(low)
        assert archiver.archive_by_importance(max_importance=0.5) >= 1
        assert store.get("low1").archived is True

    def test_purge_archived(self, archiver, store) -> None:
        archiver.archive("a1")
        assert archiver.purge_archived() >= 1
        assert store.get("a1") is None

    def test_list_archived(self, archiver, store) -> None:
        archiver.archive("a1")
        archived = archiver.list_archived()
        assert any(e.id == "a1" for e in archived)

    def test_apply_retention_policy(self, archiver, store) -> None:
        result = archiver.apply_retention_policy(max_age_days=365, min_importance=0.1)
        assert "archived" in result
        assert "purged" in result

    def test_export_archive(self, archiver, store) -> None:
        archiver.archive("a1")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "archive.json"
            result = archiver.export_archive(str(path))
            assert Path(result).exists()
