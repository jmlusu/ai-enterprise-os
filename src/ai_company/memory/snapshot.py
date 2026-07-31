"""Snapshot module for AI Enterprise OS Memory Engine."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_company.memory.models import MemoryEntry, SnapshotMetadata
from ai_company.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class MemorySnapshot:
    """Manages snapshots of memory state for backup and restore."""

    def __init__(
        self,
        store: MemoryStore,
        snapshot_path: str | Path | None = None,
    ) -> None:
        self.store = store
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.snapshot_path = Path(snapshot_path) if snapshot_path else None
        self.logger = logging.getLogger(self.__class__.__name__)

        if self.snapshot_path:
            self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_snapshots()

    def create_snapshot(
        self,
        name: str,
        memory_ids: list[str] | None = None,
        description: str = "",
        tags: list[str] | None = None,
    ) -> str:
        """Create a snapshot of current memory state."""
        timestamp = datetime.now()
        snapshot_id = f"snap_{timestamp.strftime('%Y%m%d_%H%M%S')}"

        if memory_ids:
            entries = [e for mid in memory_ids if (e := self.store.get(mid))]
        else:
            entries = self.store.get_all()

        entries_data = [e.to_dict() for e in entries]
        total_size = len(json.dumps(entries_data))

        metadata = SnapshotMetadata(
            id=snapshot_id,
            name=name,
            description=description,
            created_at=timestamp,
            entry_count=len(entries),
            total_size_bytes=total_size,
            tags=tags or [],
        )

        snapshot_data = {
            "metadata": metadata.model_dump(mode="json"),
            "entries": entries_data,
        }

        self.snapshots[snapshot_id] = snapshot_data

        # Save to disk if configured
        if self.snapshot_path:
            self._save_snapshot_to_disk(snapshot_id, snapshot_data)

        self.logger.info(f"Snapshot created: {snapshot_id} ({len(entries)} entries)")
        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> int:
        """Restore memory state from a snapshot."""
        snapshot_data = self._get_snapshot_data(snapshot_id)
        if not snapshot_data:
            self.logger.warning(f"Snapshot not found: {snapshot_id}")
            return 0

        count = 0
        for entry_data in snapshot_data.get("entries", []):
            entry = MemoryEntry.from_dict(entry_data)
            self.store.save(entry)
            count += 1

        self.logger.info(f"Restored {count} entries from snapshot {snapshot_id}")
        return count

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        if snapshot_id in self.snapshots:
            del self.snapshots[snapshot_id]
            if self.snapshot_path:
                self._rebuild_snapshot_index()
            return True
        return False

    def list_snapshots(self) -> list[dict[str, Any]]:
        """List available snapshots."""
        return [
            {
                "id": sid,
                **s["metadata"],
            }
            for sid, s in self.snapshots.items()
        ]

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        """Get a specific snapshot with all entries."""
        return self._get_snapshot_data(snapshot_id)

    def get_snapshot_metadata(self, snapshot_id: str) -> SnapshotMetadata | None:
        """Get snapshot metadata only."""
        data = self._get_snapshot_data(snapshot_id)
        if data and "metadata" in data:
            return SnapshotMetadata(**data["metadata"])
        return None

    def export_snapshot(self, snapshot_id: str, output_path: str | Path) -> Path:
        """Export a snapshot to a JSON file."""
        snapshot_data = self._get_snapshot_data(snapshot_id)
        if not snapshot_data:
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, indent=2)

        return path

    def import_snapshot(self, file_path: str | Path) -> str:
        """Import a snapshot from a JSON file."""
        path = Path(file_path)
        with open(path, "r", encoding="utf-8") as f:
            snapshot_data = json.load(f)

        metadata = snapshot_data.get("metadata", {})
        snapshot_id: str = metadata.get(
            "id", f"snap_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )

        self.snapshots[snapshot_id] = snapshot_data

        if self.snapshot_path:
            self._save_snapshot_to_disk(snapshot_id, snapshot_data)

        return snapshot_id

    def _get_snapshot_data(self, snapshot_id: str) -> dict[str, Any] | None:
        """Get snapshot data from memory or disk."""
        if snapshot_id in self.snapshots:
            return self.snapshots[snapshot_id]

        # Try loading from disk
        if self.snapshot_path:
            return self._load_snapshot_from_disk(snapshot_id)

        return None

    def _save_snapshot_to_disk(
        self,
        snapshot_id: str,
        snapshot_data: dict[str, Any],
    ) -> None:
        """Persist snapshot to disk."""
        if not self.snapshot_path:
            return
        snapshot_dir = self.snapshot_path / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata
        meta_file = snapshot_dir / "metadata.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(snapshot_data["metadata"], f, indent=2)

        # Save entries
        entries_file = snapshot_dir / "entries.json"
        with open(entries_file, "w", encoding="utf-8") as f:
            json.dump(snapshot_data["entries"], f, indent=2)

        # Update index
        self._update_snapshot_index(snapshot_id)

    def _load_snapshot_from_disk(self, snapshot_id: str) -> dict[str, Any] | None:
        """Load snapshot from disk."""
        if not self.snapshot_path:
            return None
        snapshot_dir = self.snapshot_path / snapshot_id
        if not snapshot_dir.exists():
            return None

        try:
            meta_file = snapshot_dir / "metadata.json"
            entries_file = snapshot_dir / "entries.json"

            if not meta_file.exists() or not entries_file.exists():
                return None

            with open(meta_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            with open(entries_file, "r", encoding="utf-8") as f:
                entries = json.load(f)

            snapshot_data = {"metadata": metadata, "entries": entries}
            self.snapshots[snapshot_id] = snapshot_data
            return snapshot_data
        except Exception as e:
            self.logger.warning(f"Failed to load snapshot from disk: {e}")
            return None

    def _load_snapshots(self) -> None:
        """Load all snapshots from disk."""
        if not self.snapshot_path or not self.snapshot_path.exists():
            return
        for snapshot_dir in self.snapshot_path.iterdir():
            if snapshot_dir.is_dir():
                try:
                    meta_file = snapshot_dir / "metadata.json"
                    if meta_file.exists():
                        with open(meta_file, "r", encoding="utf-8") as f:
                            metadata = json.load(f)
                        snapshot_id = metadata.get("id", snapshot_dir.name)
                        entries_file = snapshot_dir / "entries.json"
                        entries = []
                        if entries_file.exists():
                            with open(entries_file, "r", encoding="utf-8") as f:
                                entries = json.load(f)
                        self.snapshots[snapshot_id] = {
                            "metadata": metadata,
                            "entries": entries,
                        }
                except Exception as e:
                    self.logger.warning(
                        f"Failed to load snapshot {snapshot_dir.name}: {e}"
                    )

    def _save_snapshot_index(self) -> None:
        """Save snapshot index file."""
        if not self.snapshot_path:
            return
        self.snapshot_path.mkdir(parents=True, exist_ok=True)
        index_path = self.snapshot_path / "index.json"
        index_data = [
            {
                "id": sid,
                "metadata": s["metadata"],
            }
            for sid, s in self.snapshots.items()
        ]
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2)

    def _update_snapshot_index(self, snapshot_id: str) -> None:
        """Update index for a single snapshot."""
        self._save_snapshot_index()

    def _rebuild_snapshot_index(self) -> None:
        """Rebuild the snapshot index from scratch."""
        self._save_snapshot_index()
