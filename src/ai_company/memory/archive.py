"""Archive module for AI Enterprise OS Memory Engine."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from ai_company.memory.models import MemoryEntry, MemoryType
from ai_company.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class MemoryArchiver:
    """Manages archiving and unarchiving of memory entries with retention policies."""

    def __init__(
        self,
        store: MemoryStore,
        archive_path: str | Path | None = None,
    ) -> None:
        self.store = store
        self.archive_path = Path(archive_path) if archive_path else None
        self.logger = logging.getLogger(self.__class__.__name__)

        if self.archive_path:
            self.archive_path.parent.mkdir(parents=True, exist_ok=True)

    def archive(self, memory_id: str) -> bool:
        """Archive a memory entry."""
        entry = self.store.get(memory_id)
        if not entry:
            self.logger.warning(f"Memory not found for archiving: {memory_id}")
            return False

        entry.archived = True
        entry.archived_at = datetime.now(timezone.utc)
        entry.updated_at = datetime.now(timezone.utc)
        self.store.save(entry)

        # Write to archive file if configured
        if self.archive_path:
            self._write_archive_entry(entry)

        self.logger.info(f"Memory archived: {memory_id}")
        return True

    def unarchive(self, memory_id: str) -> bool:
        """Restore an archived memory."""
        entry = self.store.get(memory_id)
        if not entry:
            self.logger.warning(f"Memory not found for unarchiving: {memory_id}")
            return False

        entry.archived = False
        entry.archived_at = None
        entry.updated_at = datetime.now(timezone.utc)
        self.store.save(entry)
        self.logger.info(f"Memory unarchived: {memory_id}")
        return True

    def archive_by_type(self, memory_type: str | MemoryType) -> int:
        """Archive all memories of a given type."""
        if isinstance(memory_type, MemoryType):
            type_str = memory_type.value
        else:
            type_str = memory_type

        count = 0
        for entry in self.store.get_by_type(type_str):
            if not entry.archived:
                entry.archived = True
                entry.archived_at = datetime.now(timezone.utc)
                entry.updated_at = datetime.now(timezone.utc)
                self.store.save(entry)
                count += 1

        self.logger.info(f"Archived {count} memories of type {type_str}")
        return count

    def archive_by_namespace(self, namespace: str) -> int:
        """Archive all memories in a namespace."""
        count = 0
        for entry in self.store.get_by_namespace(namespace):
            if not entry.archived:
                entry.archived = True
                entry.archived_at = datetime.now(timezone.utc)
                entry.updated_at = datetime.now(timezone.utc)
                self.store.save(entry)
                count += 1
        self.logger.info(f"Archived {count} memories in namespace {namespace}")
        return count

    def archive_older_than(self, days: int) -> int:
        """Archive memories older than specified days."""
        count = 0
        cutoff = datetime.now(timezone.utc)
        for entry in self.store.get_all():
            if not entry.archived and (cutoff - entry.created_at).days > days:
                entry.archived = True
                entry.archived_at = cutoff
                entry.updated_at = cutoff
                self.store.save(entry)
                count += 1
        self.logger.info(f"Archived {count} memories older than {days} days")
        return count

    def archive_by_importance(self, max_importance: float = 0.2) -> int:
        """Archive memories below importance threshold."""
        count = 0
        for entry in self.store.get_all():
            if not entry.archived and entry.importance <= max_importance:
                entry.archived = True
                entry.archived_at = datetime.now(timezone.utc)
                entry.updated_at = datetime.now(timezone.utc)
                self.store.save(entry)
                count += 1
        self.logger.info(
            f"Archived {count} memories with importance <= {max_importance}"
        )
        return count

    def list_archived(self, limit: int = 100) -> list[MemoryEntry]:
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

    def apply_retention_policy(
        self,
        max_age_days: int = 365,
        max_versions: int = 5,
        min_importance: float = 0.1,
        auto_purge: bool = False,
    ) -> dict[str, int]:
        """Apply retention policy, returning counts of actions taken."""
        result = {"archived": 0, "purged": 0}
        now = datetime.now(timezone.utc)

        for entry in list(self.store.get_all()):
            reason = None

            # Check age
            if max_age_days and (now - entry.created_at).days > max_age_days:
                reason = f"age > {max_age_days} days"

            # Check importance
            if not reason and entry.importance < min_importance:
                reason = f"importance {entry.importance} < {min_importance}"

            # Check versions
            if not reason and max_versions and entry.version > max_versions:
                reason = f"version {entry.version} > {max_versions}"

            if reason:
                if auto_purge and entry.archived:
                    self.store.delete(entry.id)
                    result["purged"] += 1
                    self.logger.info(f"Purged entry {entry.id}: {reason}")
                elif not entry.archived:
                    self.archive(entry.id)
                    result["archived"] += 1
                    self.logger.info(f"Archived entry {entry.id}: {reason}")

        return result

    def export_archive(self, output_path: str | Path) -> Path:
        """Export archived memories to JSON file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        archived = self.list_archived(limit=100000)
        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "count": len(archived),
            "entries": [e.to_dict() for e in archived],
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        self.logger.info(f"Archive exported to {path} ({len(archived)} entries)")
        return path

    def _write_archive_entry(self, entry: MemoryEntry) -> None:
        """Write entry to archive file."""
        if self.archive_path:
            archive_entry = entry.to_dict()
            archive_entry["archived_at"] = datetime.now(timezone.utc).isoformat()
            with open(self.archive_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(archive_entry) + "\n")
