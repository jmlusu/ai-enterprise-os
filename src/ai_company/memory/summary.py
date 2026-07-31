"""Summary module for AI Enterprise OS Memory Engine."""

from __future__ import annotations

import logging
from typing import Any

from ai_company.memory.models import MemoryEntry

logger = logging.getLogger(__name__)


class MemorySummarizer:
    """Generates summaries for memory entries."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def summarize(self, entry: MemoryEntry) -> str:
        """Generate a summary for a single memory entry."""
        content = entry.content or {}
        summary_parts: list[str] = []

        # Extract key information based on memory type
        if "title" in content:
            summary_parts.append(str(content["title"]))
        if "name" in content:
            summary_parts.append(str(content["name"]))
        if "description" in content:
            desc = str(content["description"])
            summary_parts.append(desc[:200] if len(desc) > 200 else desc)
        if "action" in content:
            summary_parts.append(str(content["action"]))
        if "text" in content:
            text = str(content["text"])
            summary_parts.append(text[:300] if len(text) > 300 else text)
        if "decision" in content:
            summary_parts.append(f"Decision: {content['decision']!s}")
        if "result" in content:
            result = str(content["result"])
            summary_parts.append(result[:200] if len(result) > 200 else result)

        if not summary_parts:
            summary_parts.append(str(content)[:200])

        summary = " | ".join(summary_parts)

        # Add type and tags context
        namespace_tag = f"[{entry.namespace.value}]" if entry.namespace else ""
        type_tag = f"[{entry.memory_type.value}]"
        tags_context = f"#{' #'.join(entry.tags)}" if entry.tags else ""

        prefix = f"{namespace_tag} {type_tag}" if namespace_tag else type_tag
        if tags_context:
            summary = f"{prefix} {summary} ({tags_context})"
        else:
            summary = f"{prefix} {summary}"

        return summary

    def summarize_multiple(
        self,
        entries: list[MemoryEntry],
        format: str = "paragraph",
        max_entries: int = 10,
    ) -> str:
        """Generate a combined summary of multiple entries.

        Args:
            entries: Memory entries to summarize
            format: Summary format (paragraph, bullet, json, compact)
            max_entries: Maximum entries to include in summary

        Returns:
            Generated summary text
        """
        if not entries:
            return "No entries to summarize."

        # Sort by importance descending
        sorted_entries = sorted(entries, key=lambda e: e.importance, reverse=True)[
            :max_entries
        ]

        if format == "paragraph":
            parts = []
            for i, entry in enumerate(sorted_entries, 1):
                summary = self.summarize(entry)
                parts.append(f"{i}. {summary}")
            return "\n".join(parts)

        elif format == "bullet":
            parts = []
            for entry in sorted_entries:
                summary = self.summarize(entry)
                parts.append(f"- {summary}")
            return "\n".join(parts)

        elif format == "json":
            return str([e.to_dict() for e in sorted_entries])

        elif format == "compact":
            # One-line summary per entry
            parts = []
            for entry in sorted_entries:
                title = (
                    entry.content.get("title")
                    or entry.content.get("name")
                    or entry.summary[:60]
                )
                type_str = entry.memory_type.value
                importance_str = f"[{entry.importance:.1f}]"
                parts.append(f"{type_str}: {title} {importance_str}")
            return " | ".join(parts)

        elif format == "count_only":
            return f"Total: {len(entries)} entries"

        return self.summarize_multiple(sorted_entries, "paragraph")

    def generate_title_summary(
        self,
        entries: list[MemoryEntry],
        max_type_count: int = 3,
    ) -> str:
        """Generate a one-line title summarizing a set of entries."""
        if not entries:
            return "Empty memory set"

        types = set(e.memory_type.value for e in entries)
        namespaces = set(e.namespace.value for e in entries if e.namespace)

        type_str = ", ".join(sorted(types)[:max_type_count])
        ns_str = (
            f" in {', '.join(sorted(namespaces)[:max_type_count])}"
            if namespaces
            else ""
        )

        if len(types) > max_type_count:
            type_str += f" + {len(types) - max_type_count} more"

        return f"{len(entries)} memories ({type_str}){ns_str}"

    def generate_category_summary(
        self,
        entries: list[MemoryEntry],
    ) -> dict[str, Any]:
        """Generate a structured category summary."""
        if not entries:
            return {"total": 0, "categories": {}}

        categories: dict[str, dict[str, Any]] = {}
        for entry in entries:
            cat = entry.memory_type.value
            if cat not in categories:
                categories[cat] = {
                    "count": 0,
                    "total_importance": 0.0,
                    "avg_importance": 0.0,
                    "entries": [],
                }
            categories[cat]["count"] += 1
            categories[cat]["total_importance"] += entry.importance
            categories[cat]["entries"].append(
                entry.summary[:100] if entry.summary else str(entry.id)
            )

        for cat_data in categories.values():
            cat_data["avg_importance"] = (
                cat_data["total_importance"] / cat_data["count"]
                if cat_data["count"] > 0
                else 0.0
            )

        return {
            "total": len(entries),
            "categories": categories,
        }
