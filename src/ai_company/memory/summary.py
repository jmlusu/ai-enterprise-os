"""Summary module for AI Enterprise OS Memory Engine."""

from __future__ import annotations

import logging

from ai_company.memory.engine import MemoryEntry


class MemorySummarizer:
    """Generates summaries for memory entries."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def summarize(self, entry: MemoryEntry) -> str:
        """Generate a summary for a single memory entry."""
        content = entry.content or {}
        summary_parts = []

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

        if not summary_parts:
            summary_parts.append(str(content)[:200])

        summary = " | ".join(summary_parts)

        # Add type and tags context
        type_context = f"[{entry.memory_type.value}]"
        tags_context = f"#{' #'.join(entry.tags)}" if entry.tags else ""
        if tags_context:
            summary = f"{type_context} {summary} ({tags_context})"
        else:
            summary = f"{type_context} {summary}"

        return summary

    def summarize_multiple(
        self, entries: list[MemoryEntry], format: str = "paragraph"
    ) -> str:
        """Generate a combined summary of multiple entries."""
        if not entries:
            return "No entries to summarize."

        if format == "paragraph":
            parts = []
            for i, entry in enumerate(entries[:10], 1):
                summary = self.summarize(entry)
                parts.append(f"{i}. {summary}")
            return "\n".join(parts)

        elif format == "bullet":
            parts = []
            for entry in entries[:10]:
                summary = self.summarize(entry)
                parts.append(f"- {summary}")
            return "\n".join(parts)

        elif format == "json":
            return str([e.to_dict() for e in entries[:10]])

        return self.summarize_multiple(entries, "paragraph")

    def generate_title_summary(self, entries: list[MemoryEntry]) -> str:
        """Generate a one-line title summarizing a set of entries."""
        if not entries:
            return "Empty memory set"
        types = set(e.memory_type.value for e in entries)
        type_str = ", ".join(sorted(types))
        return f"{len(entries)} memories ({type_str})"
