"""Memory store for AI Enterprise OS Memory Engine.

Provides namespace-aware, hierarchical memory persistence with JSONL storage.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_company.memory.models import (
    MemoryEntry,
    MemoryNamespace,
    MemoryType,
    RetentionPolicy,
)

logger = logging.getLogger(__name__)


class MemoryStore:
    """Provider-independent, namespace-aware memory storage.

    Stores memories in memory with optional JSONL persistence to disk.
    Supports namespace isolation and hierarchical organization.
    """

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self._entries: dict[str, MemoryEntry] = {}
        self._namespace_index: dict[str, set[str]] = {}
        self._type_index: dict[str, set[str]] = {}
        self._tag_index: dict[str, set[str]] = {}
        self._parent_index: dict[str, set[str]] = {}  # parent_id -> children_ids
        self.logger = logging.getLogger(self.__class__.__name__)
        self.storage_path = Path(storage_path) if storage_path else None

        if self.storage_path:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def save(self, entry: MemoryEntry) -> None:
        """Save a memory entry with indexing."""
        old_entry = self._entries.get(entry.id)

        # Remove old indices if updating
        if old_entry:
            self._remove_from_indices(old_entry)

        self._entries[entry.id] = entry
        self._add_to_indices(entry)

        if self.storage_path:
            self._append_to_disk(entry)

    def get(self, memory_id: str) -> MemoryEntry | None:
        """Get a memory entry by ID."""
        return self._entries.get(memory_id)

    def get_all(self) -> list[MemoryEntry]:
        """Get all memory entries."""
        return list(self._entries.values())

    def get_by_type(self, memory_type: str | MemoryType) -> list[MemoryEntry]:
        """Get entries by type."""
        if isinstance(memory_type, MemoryType):
            type_str = memory_type.value
        else:
            type_str = memory_type
        ids = self._type_index.get(type_str, set())
        return [self._entries[eid] for eid in ids if eid in self._entries]

    def get_by_namespace(self, namespace: str | MemoryNamespace) -> list[MemoryEntry]:
        """Get entries by namespace."""
        if isinstance(namespace, MemoryNamespace):
            ns_str = namespace.value
        else:
            ns_str = namespace
        ids = self._namespace_index.get(ns_str, set())
        return [self._entries[eid] for eid in ids if eid in self._entries]

    def get_by_tag(self, tag: str) -> list[MemoryEntry]:
        """Get entries by tag."""
        ids = self._tag_index.get(tag, set())
        return [self._entries[eid] for eid in ids if eid in self._entries]

    def get_children(self, parent_id: str) -> list[MemoryEntry]:
        """Get child entries of a parent."""
        ids = self._parent_index.get(parent_id, set())
        return [self._entries[eid] for eid in ids if eid in self._entries]

    def get_lineage(self, memory_id: str) -> list[MemoryEntry]:
        """Get the full ancestor chain of a memory entry."""
        lineage = []
        current = self._entries.get(memory_id)
        while current and current.parent_id:
            parent = self._entries.get(current.parent_id)
            if parent:
                lineage.append(parent)
                current = parent
            else:
                break
        return lineage

    def get_subtree(self, memory_id: str) -> list[MemoryEntry]:
        """Get all descendants of a memory entry."""
        result = []
        stack = [memory_id]
        while stack:
            current_id = stack.pop()
            children = self._parent_index.get(current_id, set())
            for child_id in children:
                child = self._entries.get(child_id)
                if child:
                    result.append(child)
                    stack.append(child_id)
        return result

    def delete(self, memory_id: str) -> bool:
        """Delete a memory entry and its indices."""
        entry = self._entries.get(memory_id)
        if not entry:
            return False

        self._remove_from_indices(entry)
        del self._entries[memory_id]

        # Rebuild JSONL file from remaining entries
        if self.storage_path:
            self._rebuild_disk()
        return True

    def clear(self) -> None:
        """Clear all entries."""
        self._entries.clear()
        self._namespace_index.clear()
        self._type_index.clear()
        self._tag_index.clear()
        self._parent_index.clear()
        if self.storage_path:
            self.storage_path.unlink(missing_ok=True)

    def count(self) -> int:
        return len(self._entries)

    def count_by_type(self) -> dict[str, int]:
        """Count entries by type."""
        return {t: len(ids) for t, ids in self._type_index.items()}

    def count_by_namespace(self) -> dict[str, int]:
        """Count entries by namespace."""
        return {ns: len(ids) for ns, ids in self._namespace_index.items()}

    def search(
        self,
        query: str = "",
        namespace: str | None = None,
        memory_type: str | None = None,
        tags: list[str] | None = None,
        min_importance: float = 0.0,
        include_archived: bool = False,
        parent_id: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[MemoryEntry]:
        """Search entries with filters."""
        results = list(self._entries.values())

        # Filter archived
        if not include_archived:
            results = [e for e in results if not e.archived]

        # Filter by namespace
        if namespace:
            ns_ids = self._namespace_index.get(namespace, set())
            results = [e for e in results if e.id in ns_ids]

        # Filter by type
        if memory_type:
            type_ids = self._type_index.get(memory_type, set())
            results = [e for e in results if e.id in type_ids]

        # Filter by tags
        if tags:
            matching_ids: set[str] | None = None
            for tag in tags:
                tag_ids = self._tag_index.get(tag, set())
                if matching_ids is None:
                    matching_ids = set(tag_ids)
                else:
                    matching_ids &= tag_ids
            if matching_ids is not None:
                results = [e for e in results if e.id in matching_ids]

        # Filter by importance
        if min_importance > 0:
            results = [e for e in results if e.importance >= min_importance]

        # Filter by parent
        if parent_id:
            child_ids = self._parent_index.get(parent_id, set())
            results = [e for e in results if e.id in child_ids]

        # Filter by metadata
        if metadata_filter:
            for key, value in metadata_filter.items():
                results = [
                    e
                    for e in results
                    if e.metadata.get(key) == value or e.content.get(key) == value
                ]

        # Text search
        if query:
            query_lower = query.lower()
            scored = []
            for entry in results:
                score = self._compute_relevance(entry, query_lower)
                if score > 0:
                    scored.append((entry, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            results = [e for e, _ in scored[:limit]]
        else:
            results.sort(key=lambda e: (e.importance, e.created_at), reverse=True)
            results = results[:limit]

        return results

    def _compute_relevance(self, entry: MemoryEntry, query: str) -> float:
        """Compute text relevance score for an entry."""
        score = 0.0

        # Check summary
        if query in entry.summary.lower():
            score += 1.0
            if entry.summary.lower().startswith(query):
                score += 0.5

        # Check tags
        for tag in entry.tags:
            if query in tag.lower():
                score += 0.8

        # Check content fields
        for field_name in ("title", "name", "description", "text"):
            value = entry.content.get(field_name, "")
            if isinstance(value, str) and query in value.lower():
                score += 0.6
                if value.lower().startswith(query):
                    score += 0.3

        # Check source
        if query in entry.source.lower():
            score += 0.4

        # Check content (broad search)
        content_str = str(entry.content).lower()
        if query in content_str:
            score += 0.3

        return score

    def enforce_retention(self, policy: RetentionPolicy) -> int:
        """Enforce retention policy, return number of entries affected."""
        affected = 0
        now = datetime.now(UTC)

        for entry in list(self._entries.values()):
            entry_policy = entry.retention_policy or policy
            should_archive = False
            should_purge = False

            # Check max age
            if entry_policy.max_age_days:
                age_days = (now - entry.created_at).days
                if age_days > entry_policy.max_age_days:
                    if entry_policy.auto_archive and not entry.archived:
                        should_archive = True
                    elif entry_policy.auto_purge and entry.archived:
                        should_purge = True

            # Check importance
            if entry.importance < entry_policy.min_importance:
                if entry_policy.auto_archive and not entry.archived:
                    should_archive = True

            # Check max versions (keep only the most recent versions)
            if entry_policy.max_versions and entry.version > entry_policy.max_versions:
                if entry_policy.auto_archive and not entry.archived:
                    should_archive = True

            if should_purge:
                self.delete(entry.id)
                affected += 1
                logger.info(f"Purged expired entry: {entry.id}")
            elif should_archive:
                entry.archived = True
                entry.archived_at = now
                self.save(entry)
                affected += 1
                logger.info(f"Archived expired entry: {entry.id}")

        return affected

    def _add_to_indices(self, entry: MemoryEntry) -> None:
        """Add entry to all indices."""
        # Namespace index
        ns = entry.namespace.value
        if ns not in self._namespace_index:
            self._namespace_index[ns] = set()
        self._namespace_index[ns].add(entry.id)

        # Type index
        mt = entry.memory_type.value
        if mt not in self._type_index:
            self._type_index[mt] = set()
        self._type_index[mt].add(entry.id)

        # Tag index
        for tag in entry.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(entry.id)

        # Parent index
        if entry.parent_id:
            if entry.parent_id not in self._parent_index:
                self._parent_index[entry.parent_id] = set()
            self._parent_index[entry.parent_id].add(entry.id)

    def _remove_from_indices(self, entry: MemoryEntry) -> None:
        """Remove entry from all indices."""
        ns = entry.namespace.value
        if ns in self._namespace_index:
            self._namespace_index[ns].discard(entry.id)

        mt = entry.memory_type.value
        if mt in self._type_index:
            self._type_index[mt].discard(entry.id)

        for tag in entry.tags:
            if tag in self._tag_index:
                self._tag_index[tag].discard(entry.id)

        if entry.parent_id and entry.parent_id in self._parent_index:
            self._parent_index[entry.parent_id].discard(entry.id)

    def _append_to_disk(self, entry: MemoryEntry) -> None:
        """Append entry to JSONL file."""
        if self.storage_path:
            with open(self.storage_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")

    def _rebuild_disk(self) -> None:
        """Rebuild the entire JSONL file from memory."""
        if self.storage_path:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                f.writelines(
                    json.dumps(entry.to_dict()) + "\n"
                    for entry in self._entries.values()
                )

    def _load_from_disk(self) -> None:
        """Load entries from JSONL disk storage."""
        if self.storage_path and self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            entry = MemoryEntry.from_dict(data)
                            self._entries[entry.id] = entry
                            self._add_to_indices(entry)
                self.logger.info(f"Loaded {len(self._entries)} entries from disk")
            except Exception as e:
                self.logger.warning(f"Failed to load memories from disk: {e}")

    @staticmethod
    def _dict_to_entry(data: dict[str, Any]) -> MemoryEntry:
        """Convert dict to MemoryEntry (backward compatibility)."""
        return MemoryEntry.from_dict(data)
