"""Retrieval module for AI Enterprise OS Memory Engine."""

from __future__ import annotations

import logging

from ai_company.memory.models import MemoryEntry, MemoryType, MemoryNamespace
from ai_company.memory.store import MemoryStore

logger = logging.getLogger(__name__)


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

    def retrieve_by_namespace(self, namespace: MemoryNamespace) -> list[MemoryEntry]:
        """Retrieve memories by namespace."""
        return self.store.get_by_namespace(namespace.value)

    def retrieve_by_source(self, source: str) -> list[MemoryEntry]:
        """Retrieve memories by source."""
        return [
            e for e in self.store.get_all() if e.source == source and not e.archived
        ]

    def retrieve_by_tag(self, tag: str) -> list[MemoryEntry]:
        """Retrieve memories by tag."""
        return self.store.get_by_tag(tag)

    def retrieve_by_importance(
        self,
        min_importance: float = 0.5,
        limit: int = 50,
        include_archived: bool = False,
    ) -> list[MemoryEntry]:
        """Retrieve memories by minimum importance."""
        results = [
            e
            for e in self.store.get_all()
            if e.importance >= min_importance and (include_archived or not e.archived)
        ]
        results.sort(key=lambda e: e.importance, reverse=True)
        return results[:limit]

    def retrieve_hierarchy(self, memory_id: str) -> list[MemoryEntry]:
        """Retrieve a memory and its children (by parent_id)."""
        entry = self.store.get(memory_id)
        if not entry:
            return []
        children = self.store.get_children(memory_id)
        return [entry] + children

    def retrieve_recent(
        self,
        count: int = 10,
        include_archived: bool = False,
    ) -> list[MemoryEntry]:
        """Retrieve most recent memories."""
        results = sorted(
            [e for e in self.store.get_all() if (include_archived or not e.archived)],
            key=lambda e: e.created_at,
            reverse=True,
        )
        return results[:count]

    def retrieve_all(self) -> list[MemoryEntry]:
        """Retrieve all memories."""
        return self.store.get_all()

    def count_by_type(self) -> dict[str, int]:
        """Count memories by type."""
        return self.store.count_by_type()

    def count_by_namespace(self) -> dict[str, int]:
        """Count memories by namespace."""
        return self.store.count_by_namespace()
