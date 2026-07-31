"""Unit tests for memory embedding."""

from __future__ import annotations


from ai_company.memory.embedding import TfidfEmbedder, EmbeddingManager
from ai_company.memory.models import MemoryEntry


class TestTfidfEmbedder:
    def test_init(self) -> None:
        embedder = TfidfEmbedder()
        assert embedder.max_features == 384

    def test_embed_returns_list(self) -> None:
        embedder = TfidfEmbedder()
        vec = embedder.embed("hello world")
        assert isinstance(vec, list)
        assert len(vec) == 384

    def test_embed_empty_text(self) -> None:
        embedder = TfidfEmbedder()
        vec = embedder.embed("")
        assert isinstance(vec, list)
        assert len(vec) == 384

    def test_similarity(self) -> None:
        embedder = TfidfEmbedder()
        # Fit vocabulary by embedding baseline text first
        embedder.embed("python programming language")  # fit vocabulary
        v1 = embedder.embed("python programming")
        v2 = embedder.embed("python coding")
        v3 = embedder.embed("quantum physics")
        sim_12 = embedder.similarity(v1, v2)
        sim_13 = embedder.similarity(v1, v3)
        assert sim_12 >= sim_13

    def test_similarity_identity(self) -> None:
        embedder = TfidfEmbedder()
        embedder.embed("test text for fitting")  # fit vocabulary
        v = embedder.embed("test text for fitting")
        sim = embedder.similarity(v, v)
        assert abs(sim - 1.0) < 0.001

    def test_similarity_orthogonal(self) -> None:
        embedder = TfidfEmbedder()
        embedder.embed("some fitting text")
        zero = [0.0] * 384
        v = embedder.embed("some text")
        sim = embedder.similarity(v, zero)
        assert sim == 0.0

    def test_batch_embed(self) -> None:
        embedder = TfidfEmbedder()
        texts = ["hello", "world", "foo", "bar"]
        vectors = embedder.batch_embed(texts)
        assert len(vectors) == len(texts)
        assert all(len(v) == 384 for v in vectors)

    def test_max_features_configurable(self) -> None:
        embedder = TfidfEmbedder(max_features=128)
        vec = embedder.embed("test")
        assert len(vec) == 128


class TestEmbeddingManager:
    def test_create_without_provider(self) -> None:
        manager = EmbeddingManager()
        assert isinstance(manager.provider, TfidfEmbedder)

    def test_create_with_provider(self) -> None:
        embedder = TfidfEmbedder()
        manager = EmbeddingManager(embedder)
        assert manager.provider is embedder

    def test_generate_embedding(self) -> None:
        embedder = TfidfEmbedder()
        manager = EmbeddingManager(embedder)
        entry = MemoryEntry(content={"text": "hello world"})
        vec = manager.generate_embedding(entry)
        assert vec is not None
        assert len(vec) == 384

    def test_generate_embedding_no_provider(self) -> None:
        manager = EmbeddingManager()
        entry = MemoryEntry()
        assert manager.generate_embedding(entry) is None

    def test_search_by_similarity(self) -> None:
        embedder = TfidfEmbedder()
        manager = EmbeddingManager(embedder)
        e1 = MemoryEntry(id="e1", content={"text": "python programming"})
        e2 = MemoryEntry(id="e2", content={"text": "quantum physics"})
        # generate_embedding returns the vector; we must set it on the entry
        e1.embedding = manager.generate_embedding(e1)
        e2.embedding = manager.generate_embedding(e2)
        results = manager.search_by_similarity(
            "python coding", entries=[e1, e2], top_k=2
        )
        assert len(results) >= 1
