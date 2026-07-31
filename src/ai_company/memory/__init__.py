"""Memory Engine for AI Enterprise OS.

Persistent memory module providing provider-independent memory storage,
retrieval, search, archiving, snapshots, and summarization capabilities.

Supports: namespace-aware persistence, hierarchical organization, retention policies,
semantic search via embeddings, and knowledge base extraction.
"""

from .archive import MemoryArchiver
from .embedding import EmbeddingManager, EmbeddingProvider, TfidfEmbedder
from .engine import MemoryEngine
from .knowledge import KnowledgeBase
from .models import (
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
from .retrieval import MemoryRetrieval
from .search import MemorySearch
from .snapshot import MemorySnapshot
from .store import MemoryStore
from .summary import MemorySummarizer

__all__ = [
    "EmbeddingManager",
    "EmbeddingProvider",
    "KnowledgeBase",
    "KnowledgeEntry",
    "MemoryArchiver",
    "MemoryConfig",
    "MemoryEngine",
    "MemoryEntry",
    "MemoryNamespace",
    "MemoryRetrieval",
    "MemorySearch",
    "MemorySnapshot",
    "MemoryStats",
    "MemoryStore",
    "MemorySummarizer",
    "MemoryType",
    "RetentionPolicy",
    "SearchQuery",
    "SearchResult",
    "SnapshotMetadata",
    "TfidfEmbedder",
]
