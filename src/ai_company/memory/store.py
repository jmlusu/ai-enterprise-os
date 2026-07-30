"""Memory store for AI Enterprise OS Memory Engine."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ai_company.memory.engine import MemoryEntry


class MemoryStore:
    """Provider-independent storage for memory entries.

    Stores memories in memory with optional JSONL persistence to disk.
    """

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self._entries: dict[str, MemoryEntry] = {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self.storage_path = Path(storage_path) if storage_path else None

        if self.storage_path:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def save(self, entry: MemoryEntry) -> None:
        """Save a memory entry."""
        self._entries[entry.id] = entry
        if self.storage_path:
            self._append_to_disk(entry)

    def get(self, memory_id: str) -> MemoryEntry | None:
        """Get a memory entry by ID."""
        return self._entries.get(memory_id)

    def get_all(self) -> list[MemoryEntry]:
        """Get all memory entries."""
        return list(self._entries.values())

    def get_by_type(self, memory_type: str) -> list[MemoryEntry]:
        """Get entries by type."""
        return [e for e in self._entries.values() if e.memory_type.value == memory_type]

    def delete(self, memory_id: str) -> bool:
        """Delete a memory entry."""
        if memory_id in self._entries:
            del self._entries[memory_id]
            return True
        return False

    def clear(self) -> None:
        """Clear all entries."""
        self._entries.clear()
        if self.storage_path:
            self.storage_path.unlink(missing_ok=True)

    def count(self) -> int:
        return len(self._entries)

    def _append_to_disk(self, entry: MemoryEntry) -> None:
        if self.storage_path:
            with open(self.storage_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")

    def _load_from_disk(self) -> None:
        if self.storage_path and self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            entry = self._dict_to_entry(data)
                            self._entries[entry.id] = entry
            except Exception as e:
                self.logger.warning(f"Failed to load memories from disk: {e}")

    @staticmethod
    def _dict_to_entry(data: dict[str, Any]) -> MemoryEntry:
        from ai_company.memory.engine import MemoryType
        from datetime import datetime

        return MemoryEntry(
            id=data["id"],
            memory_type=MemoryType(data["memory_type"]),
            content=data.get("content", {}),
            summary=data.get("summary", ""),
            tags=data.get("tags", []),
            source=data.get("source", ""),
            importance=data.get("importance", 0.5),
            version=data.get("version", 1),
            parent_id=data.get("parent_id"),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else None,
            accessed_at=datetime.fromisoformat(data["accessed_at"])
            if data.get("accessed_at")
            else None,
            archived=data.get("archived", False),
            metadata=data.get("metadata", {}),
        )
