"""Search module for AI Enterprise OS Memory Engine."""

from __future__ import annotations

import logging

from ai_company.memory.engine import MemoryEntry
from ai_company.memory.store import MemoryStore


class MemorySearch:
    """Search memories across the store."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.logger = logging.getLogger(self.__class__.__name__)

    def search(
        self,
        query: str,
        memory_type: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
        min_importance: float = 0.0,
        include_archived: bool = False,
    ) -> list[MemoryEntry]:
        """Search memories by query text and filters."""
        results = []
        query_lower = query.lower() if query else ""

        for entry in self.store.get_all():
            if not include_archived and entry.archived:
                continue
            if memory_type and entry.memory_type.value != memory_type:
                continue
            if tags and not any(t in entry.tags for t in tags):
                continue
            if entry.importance < min_importance:
                continue

            if query_lower:
                if self._matches_query(entry, query_lower):
                    results.append(entry)
            else:
                results.append(entry)

        results.sort(key=lambda e: (e.importance, e.created_at), reverse=True)
        return results[:limit]

    def search_by_tags(self, tags: list[str], limit: int = 50) -> list[MemoryEntry]:
        """Search memories by tags."""
        results = [
            e
            for e in self.store.get_all()
            if any(t in e.tags for t in tags) and not e.archived
        ]
        results.sort(key=lambda e: e.importance, reverse=True)
        return results[:limit]

    def search_by_type(self, memory_type: str, limit: int = 50) -> list[MemoryEntry]:
        """Search memories by type."""
        results = [
            e
            for e in self.store.get_all()
            if e.memory_type.value == memory_type and not e.archived
        ]
        results.sort(key=lambda e: e.created_at, reverse=True)
        return results[:limit]

    def search_recent(self, count: int = 10) -> list[MemoryEntry]:
        """Get most recent memories."""
        results = sorted(self.store.get_all(), key=lambda e: e.created_at, reverse=True)
        return results[:count]

    def search_by_importance(
        self, min_importance: float = 0.5, limit: int = 50
    ) -> list[MemoryEntry]:
        """Search memories by importance threshold."""
        results = [
            e
            for e in self.store.get_all()
            if e.importance >= min_importance and not e.archived
        ]
        results.sort(key=lambda e: e.importance, reverse=True)
        return results[:limit]

    def _matches_query(self, entry: MemoryEntry, query: str) -> bool:
        """Check if a memory entry matches a search query."""
        if query in entry.summary.lower():
            return True
        if query in str(entry.content).lower():
            return True
        for tag in entry.tags:
            if query in tag.lower():
                return True
        if query in entry.source.lower():
            return True
        return False
