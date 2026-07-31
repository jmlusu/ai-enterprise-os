"""Unit tests for memory models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_company.memory.models import (
    MemoryEntry,
    MemoryType,
    MemoryNamespace,
    RetentionPolicy,
    MemoryConfig,
    SearchQuery,
    SearchResult,
    MemoryStats,
    SnapshotMetadata,
    KnowledgeEntry,
    _utcnow,
)


class TestMemoryType:
    def test_valid_values(self) -> None:
        assert MemoryType.COMPANY.value == "company"
        assert MemoryType.EXECUTIVE.value == "executive"
        assert MemoryType.DEPARTMENT.value == "department"
        assert MemoryType.SYSTEM.value == "system"

    def test_from_string(self) -> None:
        assert MemoryType("company") == MemoryType.COMPANY

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            MemoryType("nonexistent")


class TestMemoryNamespace:
    def test_valid_values(self) -> None:
        assert MemoryNamespace.GLOBAL.value == "global"
        assert MemoryNamespace.COMPANY.value == "company"

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            MemoryNamespace("invalid")


class TestRetentionPolicy:
    def test_defaults(self) -> None:
        policy = RetentionPolicy()
        assert policy.max_age_days is None
        assert policy.min_importance == 0.0

    def test_custom_values(self) -> None:
        policy = RetentionPolicy(max_age_days=30, min_importance=0.3, auto_archive=True)
        assert policy.max_age_days == 30
        assert policy.min_importance == 0.3
        assert policy.auto_archive is True

    def test_importance_range(self) -> None:
        with pytest.raises(ValidationError):
            RetentionPolicy(min_importance=-0.1)
        with pytest.raises(ValidationError):
            RetentionPolicy(min_importance=1.5)

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            RetentionPolicy(unknown_field=True)


class TestMemoryConfig:
    def test_defaults(self) -> None:
        config = MemoryConfig()
        assert config.version == "1.0"
        assert config.default_importance == 0.5

    def test_custom_values(self) -> None:
        config = MemoryConfig(storage_path="/tmp/test.jsonl", enable_embeddings=True)
        assert config.storage_path == "/tmp/test.jsonl"
        assert config.enable_embeddings is True

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            MemoryConfig(unknown="value")


class TestMemoryEntry:
    def test_default_creation(self) -> None:
        entry = MemoryEntry()
        assert entry.id.startswith("mem_")
        assert entry.memory_type == MemoryType.SYSTEM
        assert entry.namespace == MemoryNamespace.GLOBAL
        assert entry.content == {}
        assert entry.importance == 0.5
        assert entry.version == 1
        assert entry.archived is False

    def test_custom_creation(self) -> None:
        entry = MemoryEntry(
            memory_type="company",
            namespace="project",
            content={"key": "value"},
            tags=["important"],
            importance=0.9,
        )
        assert entry.memory_type == MemoryType.COMPANY
        assert entry.namespace == MemoryNamespace.PROJECT
        assert entry.content == {"key": "value"}

    def test_touch_sets_accessed_at(self) -> None:
        entry = MemoryEntry()
        assert entry.accessed_at is None
        entry.touch()
        assert entry.accessed_at is not None

    def test_is_expired(self) -> None:
        from datetime import datetime, timezone, timedelta

        entry = MemoryEntry()
        assert not entry.is_expired(max_age_days=30)
        entry.created_at = datetime.now(timezone.utc) - timedelta(days=100)
        assert entry.is_expired(max_age_days=30)
        assert not entry.is_expired(max_age_days=200)

    def test_importance_range(self) -> None:
        with pytest.raises(ValidationError):
            MemoryEntry(importance=-0.1)
        with pytest.raises(ValidationError):
            MemoryEntry(importance=1.5)

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(ValidationError):
            MemoryEntry(memory_type="invalid_type")

    def test_serialization_roundtrip(self) -> None:
        original = MemoryEntry(content={"a": 1}, tags=["t"], importance=0.8)
        data = original.to_dict()
        restored = MemoryEntry.from_dict(data)
        assert restored.id == original.id
        assert restored.content == original.content
        assert restored.importance == original.importance


class TestSearchQuery:
    def test_defaults(self) -> None:
        q = SearchQuery()
        assert q.query == ""
        assert q.tags == []
        assert q.max_results == 20

    def test_custom(self) -> None:
        q = SearchQuery(query="find", tags=["urgent"], memory_type=MemoryType.COMPANY)
        assert q.query == "find"
        assert q.memory_type == MemoryType.COMPANY


class TestSearchResult:
    def test_creation(self) -> None:
        entry = MemoryEntry()
        r = SearchResult(entry=entry, score=0.85, matched_fields=["content"])
        assert r.score == 0.85
        assert r.entry.id == entry.id


class TestMemoryStats:
    def test_creation(self) -> None:
        stats = MemoryStats(
            total_entries=100, by_type={"company": 50}, average_importance=0.65
        )
        assert stats.total_entries == 100
        assert stats.average_importance == 0.65

    def test_defaults(self) -> None:
        stats = MemoryStats()
        assert stats.total_entries == 0
        assert stats.by_type == {}


class TestSnapshotMetadata:
    def test_creation(self) -> None:
        snap = SnapshotMetadata(name="daily")
        assert snap.id.startswith("snap_")
        assert snap.name == "daily"

    def test_serialization(self) -> None:
        snap = SnapshotMetadata(name="test", entry_count=5)
        data = snap.model_dump(mode="json")
        restored = SnapshotMetadata.model_validate(data)
        assert restored.name == "test"
        assert restored.entry_count == 5


class TestKnowledgeEntry:
    def test_creation(self) -> None:
        entry = KnowledgeEntry(
            title="Test", content={"key": "val"}, summary="test knowledge"
        )
        assert entry.title == "Test"
        assert entry.content == {"key": "val"}
        assert entry.confidence == 1.0

    def test_confidence_range(self) -> None:
        with pytest.raises(ValidationError):
            KnowledgeEntry(title="x", content={}, confidence=-0.1)
        with pytest.raises(ValidationError):
            KnowledgeEntry(title="x", content={}, confidence=1.5)

    def test_title_required(self) -> None:
        with pytest.raises(ValidationError):
            KnowledgeEntry(content={})


class TestUtcnow:
    def test_returns_aware_datetime(self) -> None:
        now = _utcnow()
        assert now.tzinfo is not None
