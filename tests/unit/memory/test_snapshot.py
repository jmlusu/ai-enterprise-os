"""Unit tests for memory snapshot."""

from __future__ import annotations

import tempfile

import pytest

from ai_company.memory.models import MemoryEntry, MemoryType
from ai_company.memory.snapshot import MemorySnapshot
from ai_company.memory.store import MemoryStore


@pytest.fixture
def store() -> None:
    s = MemoryStore()
    s.save(MemoryEntry(id="s1", content={"a": 1}, memory_type=MemoryType.COMPANY))
    s.save(MemoryEntry(id="s2", content={"b": 2}, memory_type=MemoryType.SYSTEM))
    return s


@pytest.fixture
def snap(store) -> None:
    return MemorySnapshot(store)


class TestMemorySnapshot:
    def test_create_snapshot(self, snap) -> None:
        snap_id = snap.create_snapshot("test_snap")
        assert snap_id is not None
        assert snap_id.startswith("snap_")

    def test_create_snapshot_with_description(self, snap) -> None:
        snap_id = snap.create_snapshot("backup", description="Daily backup")
        assert snap_id is not None

    def test_list_snapshots(self, snap) -> None:
        import time

        snap.create_snapshot("snap1")
        time.sleep(1.1)
        snap.create_snapshot("snap2")
        snaps = snap.list_snapshots()
        assert len(snaps) >= 2

    def test_restore_snapshot(self, snap, store) -> None:
        snap_id = snap.create_snapshot("baseline")
        store.delete("s1")
        assert store.get("s1") is None
        count = snap.restore_snapshot(snap_id)
        assert count >= 2
        assert store.get("s1") is not None

    def test_restore_invalid(self, snap) -> None:
        assert snap.restore_snapshot("nope") == 0

    def test_get_snapshot_metadata(self, snap) -> None:
        snap_id = snap.create_snapshot("meta_test")
        meta = snap.get_snapshot_metadata(snap_id)
        assert meta is not None
        assert meta.name == "meta_test"

    def test_get_snapshot_metadata_nonexistent(self, snap) -> None:
        assert snap.get_snapshot_metadata("nope") is None

    def test_delete_snapshot(self, snap) -> None:
        snap_id = snap.create_snapshot("to_delete")
        assert snap.delete_snapshot(snap_id) is True
        assert snap.get_snapshot_metadata(snap_id) is None

    def test_delete_nonexistent(self, snap) -> None:
        assert snap.delete_snapshot("nope") is False

    def test_get_snapshot(self, snap) -> None:
        snap_id = snap.create_snapshot("get_test")
        data = snap.get_snapshot(snap_id)
        assert data is not None
        assert "entries" in data

    def test_disk_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore()
            store.save(MemoryEntry(id="d1", content={}))
            snap1 = MemorySnapshot(store, snapshot_path=tmpdir)
            snap_id = snap1.create_snapshot("disk_test")
            snap2 = MemorySnapshot(store, snapshot_path=tmpdir)
            assert snap2.get_snapshot_metadata(snap_id) is not None

    def test_snapshot_count_in_metadata(self, snap) -> None:
        snap_id = snap.create_snapshot("count_test")
        meta = snap.get_snapshot_metadata(snap_id)
        assert meta.entry_count >= 2
