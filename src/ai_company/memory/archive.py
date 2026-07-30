"""Archive module for AI Enterprise OS Memory Engine."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ai_company.memory.store import MemoryStore


class MemoryArchiver:
    """Manages archiving and unarchiving of memory entries."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.logger = logging.getLogger(self.__class__.__name__)

    def archive(self, memory_id: str) -> bool:
        """Archive a memory entry."""
        entry = self.store.get(memory_id)
        if not entry:
            self.logger.warning(f"Memory not found for archiving: {memory_id}")
            return False
        entry.archived = True
        entry.updated_at = datetime.now()
        self.store.save(entry)
        self.logger.info(f"Memory archived: {memory_id}")
        return True

    def unarchive(self, memory_id: str) -> bool:
        """Restore an archived memory."""
        entry = self.store.get(memory_id)
        if not entry:
            self.logger.warning(f"Memory not found for unarchiving: {memory_id}")
            return False
        entry.archived = False
        entry.updated_at = datetime.now()
        self.store.save(entry)
        self.logger.info(f"Memory unarchived: {memory_id}")
        return True

    def archive_by_type(self, memory_type: str) -> int:
        """Archive all memories of a given type."""
        count = 0
        for entry in self.store.get_all():
            if entry.memory_type.value == memory_type and not entry.archived:
                entry.archived = True
                entry.updated_at = datetime.now()
                self.store.save(entry)
                count += 1
        self.logger.info(f"Archived {count} memories of type {memory_type}")
        return count

    def archive_older_than(self, days: int) -> int:
        """Archive memories older than specified days."""
        count = 0
        cutoff = datetime.now()
        for entry in self.store.get_all():
            if not entry.archived and (cutoff - entry.created_at).days > days:
                entry.archived = True
                entry.updated_at = cutoff
                self.store.save(entry)
                count += 1
        self.logger.info(f"Archived {count} memories older than {days} days")
        return count

    def list_archived(self, limit: int = 100) -> list[Any]:
        """List archived memories."""
        archived = [e for e in self.store.get_all() if e.archived]
        archived.sort(key=lambda e: e.updated_at or e.created_at, reverse=True)
        return archived[:limit]

    def purge_archived(self) -> int:
        """Permanently delete all archived memories."""
        to_delete = [e.id for e in self.store.get_all() if e.archived]
        for memory_id in to_delete:
            self.store.delete(memory_id)
        self.logger.info(f"Purged {len(to_delete)} archived memories")
        return len(to_delete)
