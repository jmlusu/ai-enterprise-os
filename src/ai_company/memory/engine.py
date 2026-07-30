"""Memory engine for AI Enterprise OS.

Core engine that manages persistent memory operations including save,
retrieve, search, archive, snapshot, summarize, and restore.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from ai_company.memory.archive import MemoryArchiver
from ai_company.memory.retrieval import MemoryRetrieval
from ai_company.memory.search import MemorySearch
from ai_company.memory.snapshot import MemorySnapshot
from ai_company.memory.store import MemoryStore
from ai_company.memory.summary import MemorySummarizer


class MemoryType(Enum):
    """Types of memory entries."""

    COMPANY = "company"
    EXECUTIVE = "executive"
    DEPARTMENT = "department"
    AGENT = "agent"
    WORKFLOW = "workflow"
    DECISION = "decision"
    PROJECT = "project"
    MEETING = "meeting"
    CONVERSATION = "conversation"
    SYSTEM = "system"


@dataclass
class MemoryEntry:
    """A single memory entry with metadata."""

    id: str
    memory_type: MemoryType
    content: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    source: str = ""
    importance: float = 0.5
    version: int = 1
    parent_id: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime | None = None
    accessed_at: datetime | None = None
    archived: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "memory_type": self.memory_type.value,
            "content": self.content,
            "summary": self.summary,
            "tags": self.tags,
            "source": self.source,
            "importance": self.importance,
            "version": self.version,
            "parent_id": self.parent_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "accessed_at": self.accessed_at.isoformat() if self.accessed_at else None,
            "archived": self.archived,
            "metadata": self.metadata,
        }


class MemoryEngine:
    """Core engine for persistent memory management.

    Manages save, retrieve, search, archive, snapshot, summarize, and restore
    operations for all memory types. Provider-independent implementation.

    Args:
        store: Underlying memory store
        searcher: Search implementation
        archiver: Archive implementation
        snapshot_manager: Snapshot manager
        summarizer: Summarizer implementation
        retrieval: Retrieval implementation
        storage_path: Optional disk storage path
    """

    def __init__(
        self,
        store: MemoryStore | None = None,
        searcher: MemorySearch | None = None,
        archiver: MemoryArchiver | None = None,
        snapshot_manager: MemorySnapshot | None = None,
        summarizer: MemorySummarizer | None = None,
        retrieval: MemoryRetrieval | None = None,
        storage_path: str | Path | None = None,
    ) -> None:
        self.store = store or MemoryStore(storage_path=storage_path)
        self.searcher = searcher or MemorySearch(self.store)
        self.archiver = archiver or MemoryArchiver(self.store)
        self.snapshot_manager = snapshot_manager or MemorySnapshot(self.store)
        self.summarizer = summarizer or MemorySummarizer()
        self.retrieval = retrieval or MemoryRetrieval(self.store)
        self.logger = logging.getLogger(self.__class__.__name__)

    def save(
        self,
        content: dict[str, Any],
        memory_type: str | MemoryType = MemoryType.SYSTEM,
        tags: list[str] | None = None,
        source: str = "",
        importance: float = 0.5,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntry:
        """Save a new memory entry.

        Args:
            content: Memory content data
            memory_type: Type of memory
            tags: Tags for categorization
            source: Source of the memory
            importance: Importance level (0.0 to 1.0)
            parent_id: Optional parent memory ID
            metadata: Additional metadata

        Returns:
            Created MemoryEntry
        """
        if isinstance(memory_type, str):
            memory_type = MemoryType(memory_type)

        memory_id = (
            f"mem_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000)}"
        )

        entry = MemoryEntry(
            id=memory_id,
            memory_type=memory_type,
            content=content,
            tags=tags or [],
            source=source,
            importance=importance,
            parent_id=parent_id,
            metadata=metadata or {},
        )

        # Generate summary if possible
        try:
            entry.summary = self.summarizer.summarize(entry)
        except Exception as e:
            self.logger.warning(f"Summary generation failed: {e}")

        self.store.save(entry)
        self.logger.info(f"Memory saved: {memory_id} ({memory_type.value})")

        return entry

    def retrieve(self, memory_id: str) -> MemoryEntry | None:
        """Retrieve a memory by ID.

        Args:
            memory_id: Memory entry identifier

        Returns:
            MemoryEntry if found, None otherwise
        """
        entry = self.retrieval.retrieve(memory_id)
        if entry:
            entry.accessed_at = datetime.now()
            self.store.save(entry)
        return entry

    def retrieve_by_type(self, memory_type: str | MemoryType) -> list[MemoryEntry]:
        """Retrieve memories of a specific type."""
        if isinstance(memory_type, str):
            memory_type = MemoryType(memory_type)
        return self.retrieval.retrieve_by_type(memory_type)

    def search(
        self,
        query: str,
        memory_type: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
        min_importance: float = 0.0,
        include_archived: bool = False,
    ) -> list[MemoryEntry]:
        """Search memories.

        Args:
            query: Search text
            memory_type: Optional type filter
            tags: Optional tag filter
            limit: Maximum results
            min_importance: Minimum importance threshold
            include_archived: Whether to include archived memories

        Returns:
            List of matching MemoryEntries
        """
        return self.searcher.search(
            query=query,
            memory_type=memory_type,
            tags=tags,
            limit=limit,
            min_importance=min_importance,
            include_archived=include_archived,
        )

    def archive(self, memory_id: str) -> bool:
        """Archive a memory entry.

        Args:
            memory_id: Memory entry to archive

        Returns:
            True if archived successfully
        """
        return self.archiver.archive(memory_id)

    def unarchive(self, memory_id: str) -> bool:
        """Restore an archived memory."""
        return self.archiver.unarchive(memory_id)

    def snapshot(self, name: str, memory_ids: list[str] | None = None) -> str:
        """Create a snapshot of current memory state.

        Args:
            name: Name for the snapshot
            memory_ids: Specific memories to include (all if None)

        Returns:
            Snapshot ID
        """
        return self.snapshot_manager.create_snapshot(name, memory_ids)

    def restore_snapshot(self, snapshot_id: str) -> int:
        """Restore memory state from a snapshot.

        Args:
            snapshot_id: Snapshot identifier

        Returns:
            Number of memories restored
        """
        return self.snapshot_manager.restore_snapshot(snapshot_id)

    def list_snapshots(self) -> list[dict[str, Any]]:
        """List available snapshots."""
        return self.snapshot_manager.list_snapshots()

    def summarize(
        self,
        memory_ids: list[str],
        format: str = "paragraph",
    ) -> str:
        """Generate a summary of specified memories.

        Args:
            memory_ids: Memories to summarize
            format: Summary format (paragraph, bullet, json)

        Returns:
            Generated summary text
        """
        entries: list[MemoryEntry] = [
            e for mid in memory_ids if (e := self.retrieve(mid))
        ]
        return self.summarizer.summarize_multiple(entries, format=format)

    def update(
        self,
        memory_id: str,
        content: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        importance: float | None = None,
    ) -> MemoryEntry | None:
        """Update an existing memory entry with new version."""
        entry = self.retrieve(memory_id)
        if not entry:
            return None

        # Create new version
        entry.version += 1
        entry.updated_at = datetime.now()

        if content is not None:
            entry.content = content
        if tags is not None:
            entry.tags = tags
        if importance is not None:
            entry.importance = importance

        self.store.save(entry)
        self.logger.info(f"Memory updated: {memory_id} (v{entry.version})")

        return entry

    def delete(self, memory_id: str) -> bool:
        """Delete a memory entry."""
        return self.store.delete(memory_id)

    def get_statistics(self) -> dict[str, Any]:
        """Get memory statistics."""
        all_entries = self.retrieval.retrieve_all()
        type_counts: dict[str, int] = {}

        for entry in all_entries:
            mt = entry.memory_type.value
            type_counts[mt] = type_counts.get(mt, 0) + 1

        return {
            "total_memories": len(all_entries),
            "by_type": type_counts,
            "total_archived": sum(1 for e in all_entries if e.archived),
            "total_snapshots": len(self.snapshot_manager.list_snapshots()),
            "average_importance": (
                sum(e.importance for e in all_entries) / len(all_entries)
                if all_entries
                else 0
            ),
        }

    def clear(self) -> None:
        """Clear all memories."""
        self.store.clear()
        self.logger.info("All memories cleared")
