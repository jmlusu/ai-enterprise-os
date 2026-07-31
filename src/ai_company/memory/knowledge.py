"""Knowledge base module for managing structured knowledge derived from memory."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_company.memory.models import KnowledgeEntry, MemoryEntry, MemoryType

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """Knowledge base for extracting, storing, and retrieving structured knowledge."""

    def __init__(self, storage_path: str | Path | None = None):
        self.storage_path = Path(storage_path) if storage_path else None
        self._entries: dict[str, KnowledgeEntry] = {}
        self._domain_index: dict[str, set[str]] = {}
        self._tag_index: dict[str, set[str]] = {}
        self.logger = logging.getLogger(self.__class__.__name__)

        if self.storage_path:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

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
        entry = KnowledgeEntry(
            title=title,
            content=content,
            summary=summary,
            domain=domain,
            tags=tags or [],
            source_memory_ids=source_memory_ids or [],
            confidence=confidence,
        )
        self._entries[entry.id] = entry
        self._index_entry(entry)
        self._save()
        logger.info(f"Knowledge added: {entry.id} - {title}")
        return entry

    def get(self, knowledge_id: str) -> KnowledgeEntry | None:
        """Get knowledge entry by ID."""
        return self._entries.get(knowledge_id)

    def update(
        self,
        knowledge_id: str,
        title: str | None = None,
        content: dict[str, Any] | None = None,
        summary: str | None = None,
        tags: list[str] | None = None,
        confidence: float | None = None,
    ) -> KnowledgeEntry | None:
        """Update a knowledge entry."""
        entry = self._entries.get(knowledge_id)
        if not entry:
            return None

        if title is not None:
            entry.title = title
        if content is not None:
            entry.content = content
        if summary is not None:
            entry.summary = summary
        if tags is not None:
            # Remove old tag indexing
            for tag in entry.tags:
                if tag in self._tag_index:
                    self._tag_index[tag].discard(knowledge_id)
            entry.tags = tags
            # Re-index
            for tag in tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = set()
                self._tag_index[tag].add(knowledge_id)
        if confidence is not None:
            entry.confidence = confidence

        entry.version += 1
        entry.updated_at = datetime.now(UTC)
        self._save()
        return entry

    def delete(self, knowledge_id: str) -> bool:
        """Delete a knowledge entry."""
        if knowledge_id not in self._entries:
            return False

        entry = self._entries[knowledge_id]
        # Remove from indices
        if entry.domain in self._domain_index:
            self._domain_index[entry.domain].discard(knowledge_id)
        for tag in entry.tags:
            if tag in self._tag_index:
                self._tag_index[tag].discard(knowledge_id)

        del self._entries[knowledge_id]
        self._save()
        return True

    def search(
        self,
        query: str = "",
        domain: str | None = None,
        tags: list[str] | None = None,
        min_confidence: float = 0.0,
        limit: int = 20,
    ) -> list[KnowledgeEntry]:
        """Search knowledge entries."""
        results = list(self._entries.values())

        # Filter by domain
        if domain:
            ids = self._domain_index.get(domain, set())
            results = [e for e in results if e.id in ids]

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

        # Filter by confidence
        if min_confidence > 0:
            results = [e for e in results if e.confidence >= min_confidence]

        # Text search
        if query:
            query_lower = query.lower()
            results = [
                e
                for e in results
                if query_lower in e.title.lower()
                or query_lower in e.summary.lower()
                or query_lower in str(e.content).lower()
            ]

        results.sort(key=lambda e: (e.confidence, e.created_at), reverse=True)
        return results[:limit]

    def get_by_domain(self, domain: str) -> list[KnowledgeEntry]:
        """Get all knowledge entries in a domain."""
        ids = self._domain_index.get(domain, set())
        return [self._entries[eid] for eid in ids if eid in self._entries]

    def get_by_tag(self, tag: str) -> list[KnowledgeEntry]:
        """Get all knowledge entries with a tag."""
        ids = self._tag_index.get(tag, set())
        return [self._entries[eid] for eid in ids if eid in self._entries]

    def extract_from_memory(
        self,
        entry: MemoryEntry,
        domain: str = "general",
    ) -> KnowledgeEntry | None:
        """Extract a knowledge entry from a memory entry."""
        # Only extract from certain memory types
        if entry.memory_type not in (
            MemoryType.COMPANY,
            MemoryType.EXECUTIVE,
            MemoryType.DECISION,
            MemoryType.KNOWLEDGE,
            MemoryType.MEETING,
        ):
            return None

        title = (
            entry.content.get("title")
            or entry.content.get("name")
            or entry.summary[:100]
        )
        if not title:
            return None

        return self.add_knowledge(
            title=title,
            content=entry.content,
            summary=entry.summary,
            domain=domain,
            tags=entry.tags,
            source_memory_ids=[entry.id],
            confidence=0.7,
        )

    def add_relationship(
        self,
        source_id: str,
        target_id: str,
    ) -> bool:
        """Add a relationship between two knowledge entries."""
        source = self._entries.get(source_id)
        target = self._entries.get(target_id)
        if not source or not target:
            return False

        if target_id not in source.relationships:
            source.relationships.append(target_id)
        if source_id not in target.relationships:
            target.relationships.append(source_id)

        self._save()
        return True

    def get_related(self, knowledge_id: str) -> list[KnowledgeEntry]:
        """Get knowledge entries related to a given entry."""
        entry = self._entries.get(knowledge_id)
        if not entry:
            return []
        return [
            self._entries[rid] for rid in entry.relationships if rid in self._entries
        ]

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
        self._domain_index.clear()
        self._tag_index.clear()
        if self.storage_path and self.storage_path.exists():
            self.storage_path.unlink()
        logger.info("Knowledge base cleared")

    def export_json(self, file_path: str | Path) -> Path:
        """Export knowledge base to JSON."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "count": len(self._entries),
            "entries": [e.model_dump(mode="json") for e in self._entries.values()],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return path

    def get_statistics(self) -> dict[str, Any]:
        """Get knowledge base statistics."""
        return {
            "total_entries": len(self._entries),
            "domains": {d: len(ids) for d, ids in self._domain_index.items()},
            "total_tags": len(self._tag_index),
            "average_confidence": (
                sum(e.confidence for e in self._entries.values()) / len(self._entries)
                if self._entries
                else 0.0
            ),
            "total_relationships": sum(
                len(e.relationships) for e in self._entries.values()
            ),
        }

    def _index_entry(self, entry: KnowledgeEntry) -> None:
        """Index a knowledge entry."""
        # Domain index
        if entry.domain not in self._domain_index:
            self._domain_index[entry.domain] = set()
        self._domain_index[entry.domain].add(entry.id)

        # Tag index
        for tag in entry.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(entry.id)

    def _save(self) -> None:
        """Persist knowledge base to disk."""
        if not self.storage_path:
            return
        data = {
            "entries": {k: v.model_dump(mode="json") for k, v in self._entries.items()},
        }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load(self) -> None:
        """Load knowledge base from disk."""
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for entry_id, entry_data in data.get("entries", {}).items():
                entry = KnowledgeEntry(**entry_data)
                self._entries[entry_id] = entry
                self._index_entry(entry)
        except Exception as e:
            logger.warning(f"Failed to load knowledge base: {e}")
