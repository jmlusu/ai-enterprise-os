"""Retrieval module for AI Enterprise OS Memory Engine."""

from __future__ import annotations

import logging

from ai_company.memory.engine import MemoryEntry, MemoryType
from ai_company.memory.store import MemoryStore


class MemoryRetrieval:
    """Retrieves memories from the store with various strategies."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.logger = logging.getLogger(self.__class__.__name__)

    def retrieve(self, memory_id: str) -> MemoryEntry | None:
        """Retrieve a memory by ID."""
        return self.store.get(memory_id)

    def retrieve_by_type(self, memory_type: MemoryType) -> list[MemoryEntry]:
        """Retrieve memories of a specific type."""
        return self.store.get_by_type(memory_type.value)

    def retrieve_by_source(self, source: str) -> list[MemoryEntry]:
        """Retrieve memories by source."""
        return [
            e for e in self.store.get_all() if e.source == source and not e.archived
        ]

    def retrieve_by_tag(self, tag: str) -> list[MemoryEntry]:
        """Retrieve memories by tag."""
        return [e for e in self.store.get_all() if tag in e.tags and not e.archived]

    def retrieve_by_importance(
        self, min_importance: float = 0.5, limit: int = 50
    ) -> list[MemoryEntry]:
        """Retrieve memories by minimum importance."""
        results = [
            e
            for e in self.store.get_all()
            if e.importance >= min_importance and not e.archived
        ]
        results.sort(key=lambda e: e.importance, reverse=True)
        return results[:limit]

    def retrieve_hierarchy(self, memory_id: str) -> list[MemoryEntry]:
        """Retrieve a memory and its children (by parent_id)."""
        entry = self.store.get(memory_id)
        if not entry:
            return []
        children = [
            e
            for e in self.store.get_all()
            if e.parent_id == memory_id and not e.archived
        ]
        return [entry] + children

    def retrieve_recent(self, count: int = 10) -> list[MemoryEntry]:
        """Retrieve most recent memories."""
        results = sorted(
            [e for e in self.store.get_all() if not e.archived],
            key=lambda e: e.created_at,
            reverse=True,
        )
        return results[:count]

    def retrieve_all(self) -> list[MemoryEntry]:
        """Retrieve all memories."""
        return self.store.get_all()

    def count_by_type(self) -> dict[str, int]:
        """Count memories by type."""
        counts: dict[str, int] = {}
        for entry in self.store.get_all():
            mt = entry.memory_type.value
            counts[mt] = counts.get(mt, 0) + 1
        return counts
