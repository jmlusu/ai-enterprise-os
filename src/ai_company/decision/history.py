"""Decision history persistence for AI Enterprise OS Decision Engine."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_company.decision.models import Decision


class DecisionHistory:
    """Manages persistence and retrieval of decision history.

    Stores decisions in memory and optionally persists to disk as JSONL.
    """

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self._decisions: dict[str, Decision] = {}
        self._history: list[dict[str, Any]] = []
        self.logger = logging.getLogger(self.__class__.__name__)
        self.storage_path = Path(storage_path) if storage_path else None

        if self.storage_path:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def record(self, decision: Decision) -> None:
        """Record a decision in history."""
        self._decisions[decision.id] = decision

        entry = decision.to_dict()
        entry["recorded_at"] = datetime.now().isoformat()
        self._history.append(entry)

        if self.storage_path:
            self._append_to_disk(entry)

        self.logger.debug(f"Decision recorded: {decision.id}")

    def get(self, decision_id: str) -> Decision | None:
        """Get a decision by ID."""
        return self._decisions.get(decision_id)

    def query(
        self,
        status: str | None = None,
        category: str | None = None,
        owner: str | None = None,
        requester: str | None = None,
        priority: str | None = None,
        tags: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
    ) -> list[Decision]:
        """Query decisions with filters."""
        results = list(self._decisions.values())

        if status:
            results = [d for d in results if d.status.value == status]
        if category:
            results = [d for d in results if d.category.value == category]
        if owner:
            results = [d for d in results if d.owner == owner]
        if requester:
            results = [d for d in results if d.requester == requester]
        if priority:
            results = [
                d for d in results if d.priority.name.lower() == priority.lower()
            ]
        if tags:
            results = [d for d in results if any(t in d.tags for t in tags)]
        if start_date:
            start = datetime.fromisoformat(start_date)
            results = [d for d in results if d.created_at >= start]
        if end_date:
            end = datetime.fromisoformat(end_date)
            results = [d for d in results if d.created_at <= end]

        results.sort(key=lambda d: d.created_at, reverse=True)
        return results[:limit]

    def get_all(self) -> list[Decision]:
        """Get all recorded decisions."""
        return list(self._decisions.values())

    def get_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get raw history entries."""
        return self._history[-limit:]

    def count(self) -> int:
        """Get total number of decisions."""
        return len(self._decisions)

    def clear(self) -> None:
        """Clear all decision history."""
        self._decisions.clear()
        self._history.clear()

    def export_to_json(self, file_path: str | Path) -> Path:
        """Export decision history to JSON file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "total_decisions": len(self._decisions),
            "exported_at": datetime.now().isoformat(),
            "decisions": [d.to_dict() for d in self._decisions.values()],
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return path

    def _append_to_disk(self, entry: dict[str, Any]) -> None:
        """Append a history entry to disk."""
        if self.storage_path:
            with open(self.storage_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def _load_from_disk(self) -> None:
        """Load decision history from disk."""
        if self.storage_path and self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            entry = json.loads(line)
                            self._history.append(entry)
            except Exception as e:
                self.logger.warning(f"Failed to load history from disk: {e}")
