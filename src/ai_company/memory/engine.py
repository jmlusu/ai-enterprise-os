"""Memory engine for AI Enterprise OS.

Core engine that manages persistent memory operations including save,
retrieve, search, archive, snapshot, summarize, restore, and policy enforcement.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ai_company.memory.archive import MemoryArchiver
from ai_company.memory.embedding import EmbeddingManager, TfidfEmbedder
from ai_company.memory.knowledge import KnowledgeBase
from ai_company.memory.models import (  # noqa: F401 — re-exported for public API
    KnowledgeEntry,
    MemoryConfig,
    MemoryEntry,
    MemoryNamespace,
    MemoryStats,
    MemoryType,
    RetentionPolicy,
    SearchQuery,
    SearchResult,
    SnapshotMetadata,
)
from ai_company.memory.retrieval import MemoryRetrieval
from ai_company.memory.search import MemorySearch
from ai_company.memory.snapshot import MemorySnapshot
from ai_company.memory.store import MemoryStore
from ai_company.memory.summary import MemorySummarizer

logger = logging.getLogger(__name__)


class MemoryEngine:
    """Core engine for persistent memory management.

    Manages save, retrieve, search, archive, snapshot, summarize, and restore
    operations for all memory types. Support namespace-aware persistence,
    hierarchical organization, and retention policies.

    Args:
        store: Underlying memory store
        searcher: Search implementation
        archiver: Archive implementation
        snapshot_manager: Snapshot manager
        summarizer: Summarizer implementation
        retrieval: Retrieval implementation
        embedding_manager: Embedding manager for semantic search
        knowledge_base: Knowledge base for derived knowledge
        config: Memory engine configuration
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
        embedding_manager: EmbeddingManager | None = None,
        knowledge_base: KnowledgeBase | None = None,
        config: MemoryConfig | None = None,
        storage_path: str | Path | None = None,
    ) -> None:
        self.config = config or MemoryConfig()
        self.store = store or MemoryStore(storage_path=storage_path)
        self.embedding_manager = embedding_manager or EmbeddingManager(
            TfidfEmbedder() if self.config.enable_embeddings else None
        )
        self.searcher = searcher or MemorySearch(self.store, self.embedding_manager)
        self.archiver = archiver or MemoryArchiver(
            self.store,
            archive_path=self.config.archive_path
            if hasattr(self.config, "archive_path")
            else None,
        )
        self.snapshot_manager = snapshot_manager or MemorySnapshot(self.store)
        self.summarizer = summarizer or MemorySummarizer()
        self.retrieval = retrieval or MemoryRetrieval(self.store)
        self.knowledge_base = knowledge_base or KnowledgeBase(
            storage_path=str(Path(self.config.storage_path).parent / "knowledge.json")
            if hasattr(self.config, "storage_path")
            else None
        )
        self._counter = 0
        self.logger = logging.getLogger(self.__class__.__name__)

    # ──────────────────────────────────────────────
    # CRUD Operations
    # ──────────────────────────────────────────────

    def save(
        self,
        content: dict[str, Any],
        memory_type: str | MemoryType = MemoryType.SYSTEM,
        namespace: str | MemoryNamespace = MemoryNamespace.GLOBAL,
        tags: list[str] | None = None,
        source: str = "",
        importance: float | None = None,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntry:
        """Save a new memory entry.

        Args:
            content: Memory content data
            memory_type: Type of memory
            namespace: Memory namespace
            tags: Tags for categorization
            source: Source of the memory
            importance: Importance level (0.0 to 1.0). Uses config default if None.
            parent_id: Optional parent memory ID for hierarchy
            metadata: Additional metadata

        Returns:
            Created MemoryEntry
        """
        if isinstance(memory_type, str):
            memory_type = MemoryType(memory_type)
        if isinstance(namespace, str):
            namespace = MemoryNamespace(namespace)

        self._counter += 1
        memory_id = f"mem_{int(time.time() * 1000000)}_{self._counter:04d}"

        if importance is None:
            importance = self.config.default_importance

        entry = MemoryEntry(
            id=memory_id,
            memory_type=memory_type,
            namespace=namespace,
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

        # Generate embedding if enabled
        if self.config.enable_embeddings:
            try:
                entry.embedding = self.embedding_manager.generate_embedding(entry)
            except Exception as e:
                self.logger.warning(f"Embedding generation failed: {e}")

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
            entry.touch()
            self.store.save(entry)
        return entry

    def retrieve_all(self) -> list[MemoryEntry]:
        """Retrieve all memory entries.

        Returns:
            List of all MemoryEntries
        """
        return self.store.get_all()

    def retrieve_by_type(
        self,
        memory_type: str | MemoryType,
    ) -> list[MemoryEntry]:
        """Retrieve memories of a specific type."""
        if isinstance(memory_type, str):
            memory_type = MemoryType(memory_type)
        return self.retrieval.retrieve_by_type(memory_type)

    def retrieve_by_namespace(
        self,
        namespace: str | MemoryNamespace,
    ) -> list[MemoryEntry]:
        """Retrieve memories by namespace."""
        if isinstance(namespace, str):
            namespace = MemoryNamespace(namespace)
        return self.store.get_by_namespace(namespace)

    def update(
        self,
        memory_id: str,
        content: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        importance: float | None = None,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntry | None:
        """Update an existing memory entry with new version."""
        entry = self.retrieve(memory_id)
        if not entry:
            return None

        entry.version += 1
        entry.updated_at = datetime.now(timezone.utc)

        if content is not None:
            entry.content = content
        if tags is not None:
            entry.tags = tags
        if importance is not None:
            entry.importance = importance
        if summary is not None:
            entry.summary = summary
        if metadata is not None:
            entry.metadata.update(metadata)

        # Regenerate summary if content changed
        if content is not None:
            try:
                entry.summary = self.summarizer.summarize(entry)
            except Exception as e:
                self.logger.warning(f"Summary regeneration failed: {e}")

        self.store.save(entry)
        self.logger.info(f"Memory updated: {memory_id} (v{entry.version})")
        return entry

    def delete(self, memory_id: str) -> bool:
        """Delete a memory entry."""
        return self.store.delete(memory_id)

    # ──────────────────────────────────────────────
    # Search Operations
    # ──────────────────────────────────────────────

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
        """Search memories.

        Args:
            query: Search text
            memory_type: Optional type filter
            namespace: Optional namespace filter
            tags: Optional tag filter
            limit: Maximum results
            min_importance: Minimum importance threshold
            include_archived: Whether to include archived memories
            parent_id: Filter by parent memory ID
            metadata_filter: Filter by metadata fields

        Returns:
            List of matching MemoryEntries
        """
        return self.searcher.search(
            query=query,
            memory_type=memory_type,
            namespace=namespace,
            tags=tags,
            limit=limit,
            min_importance=min_importance,
            include_archived=include_archived,
            parent_id=parent_id,
            metadata_filter=metadata_filter,
        )

    def search_structured(self, search_query: SearchQuery) -> list[SearchResult]:
        """Search using a structured search query."""
        return self.searcher.search_structured(search_query)

    def semantic_search(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.0,
    ) -> list[tuple[MemoryEntry, float]]:
        """Search by semantic similarity using embeddings."""
        return self.searcher.semantic_search(query, limit, threshold)

    # ──────────────────────────────────────────────
    # Archive Operations
    # ──────────────────────────────────────────────

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

    def archive_older_than(self, days: int) -> int:
        """Archive memories older than specified days."""
        return self.archiver.archive_older_than(days)

    def archive_by_type(self, memory_type: str | MemoryType) -> int:
        """Archive all memories of a given type."""
        return self.archiver.archive_by_type(memory_type)

    def archive_by_namespace(self, namespace: str | MemoryNamespace) -> int:
        """Archive all memories in a namespace."""
        if isinstance(namespace, MemoryNamespace):
            namespace = namespace.value
        return self.archiver.archive_by_namespace(namespace)

    def purge_archived(self) -> int:
        """Permanently delete all archived memories."""
        return self.archiver.purge_archived()

    # ──────────────────────────────────────────────
    # Snapshot Operations
    # ──────────────────────────────────────────────

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

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        return self.snapshot_manager.delete_snapshot(snapshot_id)

    # ──────────────────────────────────────────────
    # Summarization
    # ──────────────────────────────────────────────

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

    def summarize_by_type(
        self,
        memory_type: str | MemoryType,
        format: str = "paragraph",
    ) -> str:
        """Generate summary of all memories of a given type."""
        entries = self.retrieve_by_type(memory_type)
        return self.summarizer.summarize_multiple(entries, format)

    def summarize_by_namespace(
        self,
        namespace: str | MemoryNamespace,
        format: str = "paragraph",
    ) -> str:
        """Generate summary of all memories in a namespace."""
        entries = self.retrieve_by_namespace(namespace)
        return self.summarizer.summarize_multiple(entries, format)

    # ──────────────────────────────────────────────
    # Knowledge Base Operations
    # ──────────────────────────────────────────────

    def extract_knowledge(
        self,
        memory_id: str,
        domain: str = "general",
    ) -> KnowledgeEntry | None:
        """Extract knowledge entry from a memory entry."""
        entry = self.retrieve(memory_id)
        if not entry:
            return None
        return self.knowledge_base.extract_from_memory(entry, domain)

    def add_knowledge(
        self,
        title: str,
        content: dict[str, Any],
        summary: str = "",
        domain: str = "general",
        tags: list[str] | None = None,
        source_memory_ids: list[str] | None = None,
        confidence: float = 1.0,
    ) -> KnowledgeEntry:
        """Add a knowledge entry."""
        return self.knowledge_base.add_knowledge(
            title=title,
            content=content,
            summary=summary,
            domain=domain,
            tags=tags,
            source_memory_ids=source_memory_ids,
            confidence=confidence,
        )

    def search_knowledge(
        self,
        query: str = "",
        domain: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[KnowledgeEntry]:
        """Search knowledge base."""
        return self.knowledge_base.search(
            query=query,
            domain=domain,
            tags=tags,
            limit=limit,
        )

    # ──────────────────────────────────────────────
    # Hierarchy Operations
    # ──────────────────────────────────────────────

    def get_children(self, memory_id: str) -> list[MemoryEntry]:
        """Get child entries of a parent memory."""
        return self.store.get_children(memory_id)

    def get_lineage(self, memory_id: str) -> list[MemoryEntry]:
        """Get the ancestor chain of a memory entry."""
        return self.store.get_lineage(memory_id)

    def get_subtree(self, memory_id: str) -> list[MemoryEntry]:
        """Get all descendants of a memory entry."""
        return self.store.get_subtree(memory_id)

    def link_memories(
        self,
        parent_id: str,
        child_id: str,
    ) -> bool:
        """Link a child memory to a parent."""
        parent = self.retrieve(parent_id)
        child = self.retrieve(child_id)
        if not parent or not child:
            return False

        child.parent_id = parent_id
        if child_id not in parent.children_ids:
            parent.children_ids.append(child_id)

        self.store.save(parent)
        self.store.save(child)
        return True

    # ──────────────────────────────────────────────
    # Retention Policy
    # ──────────────────────────────────────────────

    def apply_retention_policy(self) -> dict[str, int]:
        """Apply retention policy to all entries.

        Returns:
            Dict with 'archived' and 'purged' counts
        """
        return self.archiver.apply_retention_policy(
            max_age_days=self.config.retention.max_age_days
            if self.config.retention.max_age_days
            else 365,
            max_versions=self.config.retention.max_versions
            if self.config.retention.max_versions
            else 5,
            min_importance=self.config.retention.min_importance,
            auto_purge=self.config.retention.auto_purge,
        )

    # ──────────────────────────────────────────────
    # Statistics & Utility
    # ──────────────────────────────────────────────

    def get_statistics(self) -> dict[str, Any]:
        """Get memory statistics."""
        all_entries = self.retrieval.retrieve_all()

        type_counts: dict[str, int] = {}
        ns_counts: dict[str, int] = {}
        embedding_count = 0
        oldest = None
        newest = None
        total_size = 0

        for entry in all_entries:
            mt = entry.memory_type.value
            type_counts[mt] = type_counts.get(mt, 0) + 1

            ns = entry.namespace.value
            ns_counts[ns] = ns_counts.get(ns, 0) + 1

            if entry.embedding:
                embedding_count += 1

            if oldest is None or entry.created_at < oldest:
                oldest = entry.created_at
            if newest is None or entry.created_at > newest:
                newest = entry.created_at

            total_size += len(json.dumps(entry.to_dict()))

        return {
            "total_memories": len(all_entries),
            "by_type": type_counts,
            "by_namespace": ns_counts,
            "total_archived": sum(1 for e in all_entries if e.archived),
            "total_snapshots": len(self.snapshot_manager.list_snapshots()),
            "average_importance": (
                sum(e.importance for e in all_entries) / len(all_entries)
                if all_entries
                else 0
            ),
            "total_size_bytes": total_size,
            "oldest_entry": oldest.isoformat() if oldest else None,
            "newest_entry": newest.isoformat() if newest else None,
            "embedding_count": embedding_count,
            "knowledge_count": self.knowledge_base.count(),
        }

    def get_memory_stats(self) -> MemoryStats:
        """Get structured memory statistics."""
        stats = self.get_statistics()
        return MemoryStats(
            total_entries=stats["total_memories"],
            by_type=stats["by_type"],
            by_namespace=stats.get("by_namespace", {}),
            total_archived=stats["total_archived"],
            total_snapshots=stats["total_snapshots"],
            average_importance=stats["average_importance"],
            total_size_bytes=stats.get("total_size_bytes", 0),
            oldest_entry=(
                datetime.fromisoformat(stats["oldest_entry"])
                if stats.get("oldest_entry")
                else None
            ),
            newest_entry=(
                datetime.fromisoformat(stats["newest_entry"])
                if stats.get("newest_entry")
                else None
            ),
            embedding_count=stats.get("embedding_count", 0),
        )

    def clear(self) -> None:
        """Clear all memories."""
        self.store.clear()
        self.logger.info("All memories cleared")

    def export_to_json(self, file_path: str | Path) -> Path:
        """Export all memories to JSON file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "config": self.config.model_dump(mode="json") if self.config else None,
            "total_entries": self.store.count(),
            "entries": [e.to_dict() for e in self.store.get_all()],
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        self.logger.info(f"Memory exported to {path}")
        return path

    @classmethod
    def from_config(cls, config_path: str | Path) -> "MemoryEngine":
        """Create MemoryEngine from YAML configuration file."""
        config_path = Path(config_path)
        if not config_path.exists():
            logger.warning(f"Config not found: {config_path}, using defaults")
            return cls()

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Extract relevant config
        storage = data.get("storage", {})
        storage_path = storage.get("store_path", "memory/store.jsonl")
        snapshot_path = storage.get("snapshot_path", "memory/snapshots")
        archive_path = storage.get("archive_path", "memory/archive")

        retention_config = data.get("retention", {})
        retention = RetentionPolicy(
            max_age_days=retention_config.get("default_max_age_days", 365),
            max_versions=retention_config.get("default_max_versions", 5),
            min_importance=retention_config.get("min_importance_threshold", 0.1),
            auto_archive=retention_config.get("auto_archive", True),
            auto_purge=retention_config.get("auto_purge_archived", False),
        )

        embed_config = data.get("embeddings", {})
        config = MemoryConfig(
            storage_path=storage_path,
            snapshot_path=snapshot_path,
            archive_path=archive_path,
            enable_embeddings=embed_config.get("enabled", False),
            retention=retention,
        )

        store = MemoryStore(storage_path=storage_path)
        archiver = MemoryArchiver(store, archive_path=archive_path)
        knowledge_base = KnowledgeBase(
            storage_path=str(Path(storage_path).parent / "knowledge.json")
        )

        return cls(
            store=store,
            archiver=archiver,
            knowledge_base=knowledge_base,
            config=config,
        )
