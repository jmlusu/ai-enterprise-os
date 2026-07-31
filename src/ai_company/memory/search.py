"""Search module for AI Enterprise OS Memory Engine."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ai_company.memory.embedding import EmbeddingManager
from ai_company.memory.models import (
    MemoryEntry,
    MemoryNamespace,
    MemoryType,
    SearchQuery,
    SearchResult,
)
from ai_company.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class MemorySearch:
    """Search memories across the store."""

    def __init__(
        self,
        store: MemoryStore,
        embedding_manager: Optional[EmbeddingManager] = None,
    ) -> None:
        self.store = store
        self.embedding_manager = embedding_manager or EmbeddingManager()
        self.logger = logging.getLogger(self.__class__.__name__)

    def search(
        self,
        query: str = "",
        memory_type: str | None = None,
        namespace: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
        min_importance: float = 0.0,
        include_archived: bool = False,
        parent_id: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[MemoryEntry]:
        """Search memories by query text and filters."""
        return self.store.search(
            query=query,
            namespace=namespace,
            memory_type=memory_type,
            tags=tags,
            min_importance=min_importance,
            include_archived=include_archived,
            parent_id=parent_id,
            metadata_filter=metadata_filter,
            limit=limit,
        )

    def search_structured(self, search_query: SearchQuery) -> list[SearchResult]:
        """Search using structured search query with scoring."""
        entries = self.store.search(
            query=search_query.query,
            namespace=search_query.namespace.value if search_query.namespace else None,
            memory_type=search_query.memory_type.value
            if search_query.memory_type
            else None,
            tags=search_query.tags,
            min_importance=search_query.min_importance,
            include_archived=search_query.include_archived,
            parent_id=search_query.parent_id,
            limit=search_query.max_results,
        )

        results = []
        for entry in entries:
            score = self._compute_score(entry, search_query)
            matched_fields = self._get_matched_fields(entry, search_query.query)
            snippet = self._generate_snippet(entry, search_query.query)

            results.append(
                SearchResult(
                    entry=entry,
                    score=score,
                    matched_fields=matched_fields,
                    snippet=snippet,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def search_by_tags(
        self,
        tags: list[str],
        limit: int = 50,
        include_archived: bool = False,
    ) -> list[MemoryEntry]:
        """Search memories by tags."""
        return self.store.search(
            tags=tags, include_archived=include_archived, limit=limit
        )

    def search_by_type(
        self,
        memory_type: str | MemoryType,
        limit: int = 50,
        include_archived: bool = False,
    ) -> list[MemoryEntry]:
        """Search memories by type."""
        if isinstance(memory_type, MemoryType):
            type_str = memory_type.value
        else:
            type_str = memory_type
        return self.store.search(
            memory_type=type_str, include_archived=include_archived, limit=limit
        )

    def search_by_namespace(
        self,
        namespace: str | MemoryNamespace,
        limit: int = 50,
        include_archived: bool = False,
    ) -> list[MemoryEntry]:
        """Search memories by namespace."""
        if isinstance(namespace, MemoryNamespace):
            ns_str = namespace.value
        else:
            ns_str = namespace
        return self.store.search(
            namespace=ns_str, include_archived=include_archived, limit=limit
        )

    def search_recent(
        self, count: int = 10, include_archived: bool = False
    ) -> list[MemoryEntry]:
        """Get most recent memories."""
        results = self.store.get_all()
        if not include_archived:
            results = [e for e in results if not e.archived]
        results.sort(key=lambda e: e.created_at, reverse=True)
        return results[:count]

    def search_by_importance(
        self,
        min_importance: float = 0.5,
        limit: int = 50,
        include_archived: bool = False,
    ) -> list[MemoryEntry]:
        """Search memories by importance threshold."""
        return self.store.search(
            min_importance=min_importance,
            include_archived=include_archived,
            limit=limit,
        )

    def search_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 50,
        include_archived: bool = False,
    ) -> list[MemoryEntry]:
        """Search memories by creation date range."""
        results = []
        for entry in self.store.get_all():
            if not include_archived and entry.archived:
                continue
            if start_date <= entry.created_at <= end_date:
                results.append(entry)
        results.sort(key=lambda e: e.created_at, reverse=True)
        return results[:limit]

    def semantic_search(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.0,
    ) -> list[tuple[MemoryEntry, float]]:
        """Search by semantic similarity using embeddings."""
        entries = self.store.get_all()
        return self.embedding_manager.search_by_similarity(
            query=query,
            entries=entries,
            top_k=limit,
            threshold=threshold,
        )

    def search_hierarchy(
        self,
        parent_id: str,
        include_archived: bool = False,
    ) -> list[MemoryEntry]:
        """Search children of a parent memory."""
        return self.store.search(parent_id=parent_id, include_archived=include_archived)

    def _compute_score(self, entry: MemoryEntry, query: SearchQuery) -> float:
        """Compute relevance score for an entry against query."""
        score = 0.0

        # Base importance factor
        score += entry.importance * 0.3

        if query.query:
            query_lower = query.query.lower()

            # Summary match
            if query_lower in entry.summary.lower():
                score += 0.4
                if entry.summary.lower().startswith(query_lower):
                    score += 0.2

            # Tag match
            for tag in entry.tags:
                if query_lower in tag.lower():
                    score += 0.3

            # Content field matches
            for field in ("title", "name", "description", "text"):
                value = entry.content.get(field, "")
                if isinstance(value, str):
                    if query_lower in value.lower():
                        score += 0.25
                    if value.lower().startswith(query_lower):
                        score += 0.15

            # Source match
            if query_lower in entry.source.lower():
                score += 0.2

            # Broad content match
            if query_lower in str(entry.content).lower():
                score += 0.1

        # Recency boost
        age_days = (datetime.now(timezone.utc) - entry.created_at).days
        if age_days < 7:
            score += 0.1
        elif age_days < 30:
            score += 0.05

        # Version boost (newer versions are more relevant)
        score += min(entry.version * 0.01, 0.05)

        return min(score, 1.0)

    def _get_matched_fields(self, entry: MemoryEntry, query: str) -> list[str]:
        """Get list of fields that matched the query."""
        if not query:
            return []
        matched = []
        query_lower = query.lower()

        if query_lower in entry.summary.lower():
            matched.append("summary")
        for tag in entry.tags:
            if query_lower in tag.lower():
                matched.append("tags")
                break
        for field in ("title", "name", "description", "text"):
            value = entry.content.get(field, "")
            if isinstance(value, str) and query_lower in value.lower():
                matched.append(field)
        if query_lower in entry.source.lower():
            matched.append("source")

        return matched

    def _generate_snippet(self, entry: MemoryEntry, query: str) -> str:
        """Generate a context snippet highlighting matches."""
        if not query:
            return entry.summary[:200] if entry.summary else str(entry.content)[:200]

        query_lower = query.lower()

        # Try to find context in summary
        if entry.summary:
            idx = entry.summary.lower().find(query_lower)
            if idx >= 0:
                start = max(0, idx - 50)
                end = min(len(entry.summary), idx + len(query) + 50)
                snippet = entry.summary[start:end]
                if start > 0:
                    snippet = "..." + snippet
                if end < len(entry.summary):
                    snippet = snippet + "..."
                return snippet
            return entry.summary[:200]

        # Try content
        content_str = str(entry.content)
        idx = content_str.lower().find(query_lower)
        if idx >= 0:
            start = max(0, idx - 50)
            end = min(len(content_str), idx + len(query) + 50)
            snippet = content_str[start:end]
            if start > 0:
                snippet = "..." + snippet
            if end < len(content_str):
                snippet = snippet + "..."
            return snippet

        return str(entry.content)[:200]
