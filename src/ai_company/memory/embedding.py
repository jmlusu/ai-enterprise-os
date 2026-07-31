"""Embedding provider for semantic memory search."""

from __future__ import annotations

import logging
import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import Dict, List, Optional, Tuple

from ai_company.memory.models import MemoryEntry

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Generate embedding vector for text."""
        ...

    @abstractmethod
    def similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute similarity between two vectors."""
        ...

    @abstractmethod
    def batch_embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        ...


class TfidfEmbedder(EmbeddingProvider):
    """TF-IDF based embedding provider (no external dependencies)."""

    def __init__(self, max_features: int = 384):
        self.max_features = max_features
        self._vocabulary: Dict[str, int] = {}
        self._idf: Dict[str, float] = {}
        self._fitted = False
        self.logger = logging.getLogger(self.__class__.__name__)

    def embed(self, text: str) -> List[float]:
        """Generate TF-IDF embedding for text."""
        if not self._fitted:
            self._fit_basic(text)

        tokens = self._tokenize(text)
        tf = Counter(tokens)

        vector = [0.0] * self.max_features
        for token, count in tf.items():
            if token in self._vocabulary:
                idx = self._vocabulary[token]
                idf = self._idf.get(token, 1.0)
                vector[idx] = count * idf

        # Normalize
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector[: self.max_features]

    def batch_embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        return [self.embed(t) for t in texts]

    def similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec1 or not vec2:
            return 0.0

        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot / (norm1 * norm2)

    def _fit_basic(self, text: str) -> None:
        """Build vocabulary from initial text."""
        tokens = self._tokenize(text)
        doc_count = max(1, len(tokens))

        # Build vocabulary from most common tokens
        token_counts = Counter(tokens)
        common = token_counts.most_common(self.max_features)

        for idx, (token, _) in enumerate(common):
            self._vocabulary[token] = idx
            self._idf[token] = math.log(doc_count / (1 + token_counts[token]))

        self._fitted = True

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into tokens."""
        text = text.lower()
        tokens = re.findall(r"\b[a-z0-9]{2,}\b", text)
        return tokens


class EmbeddingManager:
    """Manages embeddings for memory entries."""

    def __init__(self, provider: Optional[EmbeddingProvider] = None):
        self.provider = provider or TfidfEmbedder()
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate_embedding(self, entry: MemoryEntry) -> Optional[List[float]]:
        """Generate embedding for a memory entry."""
        text = self._entry_to_text(entry)
        if not text:
            return None
        return self.provider.embed(text)

    def search_by_similarity(
        self,
        query: str,
        entries: List[MemoryEntry],
        top_k: int = 10,
        threshold: float = 0.0,
    ) -> List[Tuple[MemoryEntry, float]]:
        """Search entries by semantic similarity to query."""
        query_vec = self.provider.embed(query)
        if not query_vec:
            return []

        scored: List[Tuple[MemoryEntry, float]] = []
        for entry in entries:
            if entry.embedding:
                sim = self.provider.similarity(query_vec, entry.embedding)
                if sim >= threshold:
                    scored.append((entry, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def _entry_to_text(self, entry: MemoryEntry) -> str:
        """Convert memory entry to searchable text."""
        parts = [
            entry.summary,
            str(entry.content.get("title", "")),
            str(entry.content.get("name", "")),
            str(entry.content.get("description", "")),
            str(entry.content.get("text", "")),
            " ".join(entry.tags),
            entry.source,
        ]
        return " ".join(p for p in parts if p)
