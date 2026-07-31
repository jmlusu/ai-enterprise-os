"""Unit tests for memory search."""

from __future__ import annotations

import pytest

from ai_company.memory.models import (
    MemoryEntry,
    MemoryType,
    MemoryNamespace,
    SearchQuery,
    SearchResult,
)
from ai_company.memory.store import MemoryStore
from ai_company.memory.search import MemorySearch


@pytest.fixture
def store() -> None:
    s = MemoryStore()
    s.save(
        MemoryEntry(
            id="e1",
            memory_type=MemoryType.COMPANY,
            content={"name": "Alice"},
            tags=["user"],
        )
    )
    s.save(
        MemoryEntry(
            id="e2",
            memory_type=MemoryType.SYSTEM,
            content={"name": "Bob"},
            tags=["admin"],
        )
    )
    s.save(
        MemoryEntry(
            id="e3",
            memory_type=MemoryType.DECISION,
            content={"decision": "approve"},
            tags=["urgent"],
            namespace=MemoryNamespace.COMPANY,
        )
    )
    s.save(
        MemoryEntry(
            id="e4",
            memory_type=MemoryType.COMPANY,
            content={"name": "Charlie"},
            tags=["user"],
            namespace=MemoryNamespace.PROJECT,
        )
    )
    return s


@pytest.fixture
def searcher(store) -> None:
    return MemorySearch(store)


class TestMemorySearch:
    def test_search_structured_by_text(self, searcher) -> None:
        results = searcher.search_structured(SearchQuery(query="Alice"))
        assert any(r.entry.id == "e1" for r in results)

    def test_search_structured_by_tag(self, searcher) -> None:
        results = searcher.search_structured(SearchQuery(tags=["admin"]))
        assert any(r.entry.id == "e2" for r in results)

    def test_search_structured_by_type(self, searcher) -> None:
        results = searcher.search_structured(
            SearchQuery(memory_type=MemoryType.DECISION)
        )
        assert all(r.entry.memory_type == MemoryType.DECISION for r in results)

    def test_search_structured_by_namespace(self, searcher) -> None:
        results = searcher.search_structured(
            SearchQuery(namespace=MemoryNamespace.PROJECT)
        )
        assert any(r.entry.namespace == MemoryNamespace.PROJECT for r in results)

    def test_search_structured_combined(self, searcher) -> None:
        results = searcher.search_structured(
            SearchQuery(tags=["user"], memory_type=MemoryType.COMPANY)
        )
        assert all(r.entry.memory_type == MemoryType.COMPANY for r in results)

    def test_search_structured_limit(self, searcher) -> None:
        results = searcher.search_structured(SearchQuery(max_results=2))
        assert len(results) <= 2

    def test_search_structured_scored(self, searcher) -> None:
        results = searcher.search_structured(SearchQuery(query="approve"))
        assert all(isinstance(r, SearchResult) for r in results)
        assert all(0.0 <= r.score <= 1.0 for r in results)

    def test_search_by_tags(self, searcher) -> None:
        results = searcher.search_by_tags(["user"])
        assert any(e.id == "e1" for e in results)

    def test_search_by_type(self, searcher) -> None:
        results = searcher.search_by_type(MemoryType.SYSTEM)
        assert any(e.id == "e2" for e in results)

    def test_search_by_namespace(self, searcher) -> None:
        results = searcher.search_by_namespace(MemoryNamespace.COMPANY)
        assert any(e.id == "e3" for e in results)

    def test_search_recent(self, searcher) -> None:
        results = searcher.search_recent(count=2)
        assert len(results) <= 2

    def test_search_by_importance(self, searcher) -> None:
        results = searcher.search_by_importance(min_importance=0.4)
        assert all(e.importance >= 0.4 for e in results)

    def test_search_by_date_range(self, searcher) -> None:
        from datetime import datetime, timezone, timedelta

        start = datetime.now(timezone.utc) - timedelta(days=1)
        end = datetime.now(timezone.utc) + timedelta(days=1)
        results = searcher.search_by_date_range(start, end)
        assert len(results) >= 1

    def test_search_hierarchy(self, searcher) -> None:
        store = searcher.store
        parent = MemoryEntry(id="parent1", content={})
        child = MemoryEntry(id="child1", parent_id="parent1", content={})
        store.save(parent)
        store.save(child)
        results = searcher.search_hierarchy("parent1")
        assert len(results) >= 1

    def test_semantic_search(self, searcher) -> None:
        results = searcher.semantic_search("Alice")
        assert isinstance(results, list)

    def test_empty_query_returns_all(self, searcher) -> None:
        results = searcher.search_structured(SearchQuery())
        assert len(results) >= 1
