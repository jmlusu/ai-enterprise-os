"""Shared data models for the Memory Engine.

All models use Pydantic BaseModel for validation, serialization, and schema generation.
Supported formats: YAML, JSON, dict.

Memory Hierarchy:
  Company Memory → Department Memory → Project Memory → Task Memory
                                                        → Meeting Memory
                                           → Decision Memory
  Executive Memory (parallel to Department)
  Conversation Memory (cross-cutting)
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_serializer


def _utcnow() -> datetime:
    """Return current UTC datetime (timezone-aware).

    Replacement for deprecated datetime.utcnow().
    """
    return datetime.now(UTC)


class MemoryType(str, Enum):
    """Types of memory entries in the memory hierarchy."""

    COMPANY = "company"
    EXECUTIVE = "executive"
    DEPARTMENT = "department"
    AGENT = "agent"
    WORKFLOW = "workflow"
    DECISION = "decision"
    PROJECT = "project"
    TASK = "task"
    MEETING = "meeting"
    CONVERSATION = "conversation"
    KNOWLEDGE = "knowledge"
    SYSTEM = "system"


class MemoryNamespace(str, Enum):
    """Namespaces for memory isolation and organization."""

    GLOBAL = "global"
    COMPANY = "company"
    EXECUTIVE = "executive"
    DEPARTMENT = "department"
    PROJECT = "project"
    AGENT = "agent"
    WORKFLOW = "workflow"
    USER = "user"
    ORCHESTRATION = "orchestration"


class RetentionPolicy(BaseModel):
    """Retention policy for memory entries."""

    max_age_days: int | None = Field(
        default=None, description="Maximum age in days before archival"
    )
    max_versions: int | None = Field(
        default=None, description="Maximum versions to keep"
    )
    min_importance: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum importance to retain"
    )
    auto_archive: bool = Field(
        default=False, description="Auto-archive when conditions met"
    )
    auto_purge: bool = Field(default=False, description="Auto-purge archived entries")
    notify_before_purge: bool = Field(default=False, description="Notify before purge")

    model_config = {"extra": "forbid"}


class MemoryConfig(BaseModel):
    """Memory engine configuration loaded from YAML."""

    version: str = Field(default="1.0")
    storage_path: str = Field(default="memory/store.jsonl")
    snapshot_path: str = Field(default="memory/snapshots")
    archive_path: str = Field(default="memory/archive")
    enable_embeddings: bool = Field(default=False)
    embedder_type: str = Field(default="tfidf")
    embedder_model: str | None = Field(default=None)
    max_memory_per_namespace: int = Field(default=10000)
    default_importance: float = Field(default=0.5, ge=0.0, le=1.0)
    retention: RetentionPolicy = Field(default_factory=lambda: RetentionPolicy())

    # Per-type retention policies (overrides global)
    type_retention: dict[str, RetentionPolicy] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class MemoryEntry(BaseModel):
    """A single memory entry with metadata and full audit trail."""

    id: str = Field(
        default_factory=lambda: f"mem_{uuid4().hex[:12]}",
        description="Unique memory ID",
    )
    memory_type: MemoryType = Field(
        default=MemoryType.SYSTEM, description="Memory type"
    )
    namespace: MemoryNamespace = Field(
        default=MemoryNamespace.GLOBAL, description="Memory namespace"
    )
    content: dict[str, Any] = Field(
        default_factory=dict, description="Memory content data"
    )
    summary: str = Field(default="", description="Text summary of memory")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    source: str = Field(
        default="", description="Source of the memory (e.g. system, user, workflow)"
    )
    importance: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Importance score 0.0-1.0"
    )
    base_importance: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Initial importance (before decay)"
    )
    recall_count: int = Field(default=0, description="Number of times accessed")
    version: int = Field(default=1, ge=1, description="Version number for updates")
    tier: str = Field(
        default="working",
        description="Storage tier: working, short_term, long_term, archived",
    )
    encrypted: bool = Field(
        default=False, description="True if payload is AES-256-GCM encrypted"
    )
    parent_id: str | None = Field(
        default=None, description="Parent memory ID for hierarchy"
    )
    agent_id: str | None = Field(default=None, description="Originating agent ID")
    session_id: str | None = Field(default=None, description="Originating session ID")
    created_at: datetime = Field(
        default_factory=_utcnow, description="Creation timestamp"
    )
    updated_at: datetime | None = Field(
        default=None, description="Last update timestamp"
    )
    accessed_at: datetime | None = Field(
        default=None, description="Last access timestamp"
    )
    expires_at: datetime | None = Field(
        default=None, description="Auto-archival deadline"
    )
    archived: bool = Field(default=False, description="Whether entry is archived")
    archived_at: datetime | None = Field(
        default=None, description="When entry was archived"
    )
    retention_policy: RetentionPolicy | None = Field(
        default=None, description="Per-entry retention override"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    embedding: list[float] | None = Field(
        default=None, description="Vector embedding for semantic search"
    )

    model_config = {"extra": "forbid"}

    @field_serializer("created_at", "updated_at", "accessed_at", "archived_at")
    def serialize_dt(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSONL storage."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        """Create entry from dict (for JSONL loading)."""
        if "memory_type" in data and isinstance(data["memory_type"], str):
            data["memory_type"] = MemoryType(data["memory_type"])
        if "namespace" in data and isinstance(data["namespace"], str):
            data["namespace"] = MemoryNamespace(data["namespace"])
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        if "accessed_at" in data and isinstance(data["accessed_at"], str):
            data["accessed_at"] = datetime.fromisoformat(data["accessed_at"])
        if "archived_at" in data and isinstance(data["archived_at"], str):
            data["archived_at"] = datetime.fromisoformat(data["archived_at"])
        return cls(**data)

    def touch(self) -> None:
        """Update access timestamp."""
        self.accessed_at = datetime.now(UTC)

    def is_expired(self, max_age_days: int) -> bool:
        """Check if entry is older than max_age_days."""
        return (datetime.now(UTC) - self.created_at).days > max_age_days


class MemoryHierarchyNode(BaseModel):
    """Node in the memory hierarchy tree."""

    entry: MemoryEntry
    children: list[MemoryHierarchyNode] = Field(default_factory=list)
    level: int = Field(default=0, ge=0)
    path: str = Field(default="")

    model_config = {"extra": "forbid"}


class SnapshotMetadata(BaseModel):
    """Metadata for a memory snapshot."""

    id: str = Field(default_factory=lambda: f"snap_{uuid4().hex[:12]}")
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    entry_count: int = 0
    total_size_bytes: int = 0
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class SearchQuery(BaseModel):
    """Structured search query for the memory engine."""

    query: str = Field(default="", description="Search text")
    memory_type: MemoryType | None = Field(default=None, description="Filter by type")
    namespace: MemoryNamespace | None = Field(
        default=None, description="Filter by namespace"
    )
    tags: list[str] = Field(default_factory=list, description="Filter by tags")
    source: str | None = Field(default=None, description="Filter by source")
    min_importance: float = Field(default=0.0, ge=0.0, le=1.0)
    max_results: int = Field(default=20, ge=1, le=1000)
    include_archived: bool = Field(default=False)
    include_embeddings: bool = Field(default=False)
    start_date: datetime | None = Field(default=None)
    end_date: datetime | None = Field(default=None)
    sort_by: str = Field(
        default="importance",
        description="Sort field: importance, created_at, accessed_at",
    )
    sort_descending: bool = Field(default=True)
    parent_id: str | None = Field(default=None, description="Filter by parent ID")
    metadata_filter: dict[str, Any] = Field(
        default_factory=dict, description="Filter by metadata fields"
    )

    model_config = {"extra": "forbid"}


class SearchResult(BaseModel):
    """A single search result with relevance score."""

    entry: MemoryEntry
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Relevance score")
    matched_fields: list[str] = Field(
        default_factory=list, description="Fields that matched"
    )
    snippet: str = Field(default="", description="Context snippet")

    model_config = {"extra": "forbid"}


class MemoryStats(BaseModel):
    """Memory engine statistics."""

    total_entries: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    by_namespace: dict[str, int] = Field(default_factory=dict)
    total_archived: int = 0
    total_snapshots: int = 0
    average_importance: float = 0.0
    total_size_bytes: int = 0
    oldest_entry: datetime | None = None
    newest_entry: datetime | None = None
    retention_policies_applied: int = 0
    embedding_count: int = 0

    model_config = {"extra": "forbid"}


class KnowledgeEntry(BaseModel):
    """A knowledge entry with relationships and references."""

    id: str = Field(default_factory=lambda: f"know_{uuid4().hex[:12]}")
    title: str
    content: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    domain: str = "general"
    tags: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(
        default_factory=list, description="Related knowledge entry IDs"
    )
    source_memory_ids: list[str] = Field(
        default_factory=list, description="Source memory entry IDs"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    version: int = 1
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


# Rebuild forward references
MemoryHierarchyNode.model_rebuild()
