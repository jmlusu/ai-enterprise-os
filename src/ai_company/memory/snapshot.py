"""Snapshot module for AI Enterprise OS Memory Engine."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ai_company.memory.store import MemoryStore


class MemorySnapshot:
    """Manages snapshots of memory state for backup and restore."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.logger = logging.getLogger(self.__class__.__name__)

    def create_snapshot(self, name: str, memory_ids: list[str] | None = None) -> str:
        """Create a snapshot of current memory state."""
        snapshot_id = f"snap_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        if memory_ids:
            entries = [e for mid in memory_ids if (e := self.store.get(mid))]
        else:
            entries = self.store.get_all()

        snapshot_data = {
            "id": snapshot_id,
            "name": name,
            "created_at": datetime.now().isoformat(),
            "entry_count": len(entries),
            "entries": [e.to_dict() for e in entries],
        }

        self.snapshots[snapshot_id] = snapshot_data
        self.logger.info(f"Snapshot created: {snapshot_id} ({len(entries)} entries)")

        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> int:
        """Restore memory state from a snapshot."""
        snapshot = self.snapshots.get(snapshot_id)
        if not snapshot:
            self.logger.warning(f"Snapshot not found: {snapshot_id}")
            return 0

        count = 0
        for entry_data in snapshot["entries"]:
            entry = self.store._dict_to_entry(entry_data)
            self.store.save(entry)
            count += 1

        self.logger.info(f"Restored {count} entries from snapshot {snapshot_id}")
        return count

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        if snapshot_id in self.snapshots:
            del self.snapshots[snapshot_id]
            return True
        return False

    def list_snapshots(self) -> list[dict[str, Any]]:
        """List available snapshots."""
        return [
            {
                "id": s["id"],
                "name": s["name"],
                "created_at": s["created_at"],
                "entry_count": s["entry_count"],
            }
            for s in self.snapshots.values()
        ]

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        """Get a specific snapshot."""
        return self.snapshots.get(snapshot_id)
