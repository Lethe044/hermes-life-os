"""Tests for demo/semantic_search.py. Uses a deterministic fake
embedding client throughout - no live Ollama or OpenAI call."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

KEYWORDS = ["stress", "happy", "sad", "sleep", "work", "gratitude", "run"]


class FakeEmbeddingClient:
    """Deterministic bag-of-keywords 'embedding' - good enough to test
    ranking/caching logic without any real model."""

    def __init__(self):
        self.call_count = 0
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, model, input):
        self.call_count += 1
        text = input.lower()
        vector = [1.0 if kw in text else 0.0 for kw in KEYWORDS]
        return SimpleNamespace(data=[SimpleNamespace(embedding=vector)])


@pytest.fixture()
def semantic_search(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for mod in ("storage", "semantic_search"):
        if mod in sys.modules:
            del sys.modules[mod]
    import semantic_search as ss
    importlib.reload(ss)
    return ss


class TestCosineSimilarity:
    def test_identical_vectors(self, semantic_search):
        assert semantic_search.cosine_similarity([1, 0, 1], [1, 0, 1]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self, semantic_search):
        assert semantic_search.cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_opposite_vectors(self, semantic_search):
        assert semantic_search.cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_empty_vector_returns_zero(self, semantic_search):
        assert semantic_search.cosine_similarity([], []) == 0.0

    def test_mismatched_length_returns_zero(self, semantic_search):
        assert semantic_search.cosine_similarity([1, 0], [1, 0, 0]) == 0.0

    def test_zero_vector_returns_zero(self, semantic_search):
        assert semantic_search.cosine_similarity([0, 0], [1, 1]) == 0.0


class TestEntryText:
    def test_uses_content_field(self, semantic_search):
        assert semantic_search.entry_text({"type": "mood", "content": "feeling great"}) == "mood feeling great"

    def test_falls_back_through_text_fields(self, semantic_search):
        assert semantic_search.entry_text({"type": "goal", "last_note": "made progress"}) == "goal made progress"

    def test_empty_for_pure_numeric_entry(self, semantic_search):
        assert semantic_search.entry_text({"type": "hydration", "glasses": 6}) == ""

    def test_empty_string_for_entry_with_no_type_or_text(self, semantic_search):
        assert semantic_search.entry_text({"glasses": 6}) == ""


class TestResolveEmbeddingProvider:
    def test_explicit_choice(self, semantic_search):
        assert semantic_search.resolve_embedding_provider("openai") == "openai"

    def test_explicit_invalid_raises(self, semantic_search):
        with pytest.raises(semantic_search.EmbeddingProviderError):
            semantic_search.resolve_embedding_provider("anthropic")

    def test_env_var_override(self, semantic_search, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
        assert semantic_search.resolve_embedding_provider(None) == "openai"

    def test_defaults_to_ollama_without_openai_key(self, semantic_search, monkeypatch):
        monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert semantic_search.resolve_embedding_provider(None) == "ollama"

    def test_defaults_to_openai_when_key_present(self, semantic_search, monkeypatch):
        monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert semantic_search.resolve_embedding_provider(None) == "openai"


class TestGetEmbeddingClient:
    def test_unsupported_provider_raises(self, semantic_search):
        with pytest.raises(semantic_search.EmbeddingProviderError):
            semantic_search.get_embedding_client("anthropic")


class TestEnsureEmbeddings:
    def test_computes_and_caches(self, semantic_search):
        client = FakeEmbeddingClient()
        entries = [
            {"id": "a", "type": "mood", "content": "feeling stressed today"},
            {"id": "b", "type": "gratitude", "content": "grateful for a good run"},
        ]
        vectors = semantic_search.ensure_embeddings(client, "fake-model", entries)
        assert set(vectors.keys()) == {"a", "b"}
        assert client.call_count == 2

    def test_second_call_uses_cache_not_recomputed(self, semantic_search):
        client = FakeEmbeddingClient()
        entries = [{"id": "a", "type": "mood", "content": "feeling stressed"}]
        semantic_search.ensure_embeddings(client, "fake-model", entries)
        assert client.call_count == 1
        semantic_search.ensure_embeddings(client, "fake-model", entries)
        assert client.call_count == 1  # unchanged - no recompute

    def test_edited_entry_text_triggers_recompute(self, semantic_search):
        client = FakeEmbeddingClient()
        entries = [{"id": "a", "type": "mood", "content": "feeling stressed"}]
        semantic_search.ensure_embeddings(client, "fake-model", entries)
        assert client.call_count == 1

        entries[0]["content"] = "feeling happy now"  # simulates correct_entry
        semantic_search.ensure_embeddings(client, "fake-model", entries)
        assert client.call_count == 2

    def test_skips_entries_with_no_text(self, semantic_search):
        client = FakeEmbeddingClient()
        entries = [{"id": "a", "type": "hydration", "glasses": 6}]
        vectors = semantic_search.ensure_embeddings(client, "fake-model", entries)
        assert vectors == {}
        assert client.call_count == 0

    def test_skips_entries_with_no_id(self, semantic_search):
        client = FakeEmbeddingClient()
        entries = [{"type": "mood", "content": "no id here"}]
        vectors = semantic_search.ensure_embeddings(client, "fake-model", entries)
        assert vectors == {}


class TestSemanticSearch:
    def test_ranks_by_similarity(self, semantic_search):
        client = FakeEmbeddingClient()
        entries = [
            {"id": "a", "type": "mood", "content": "feeling very stressed about work"},
            {"id": "b", "type": "gratitude", "content": "grateful and happy today"},
            {"id": "c", "type": "fitness", "content": "went for a run"},
        ]
        results = semantic_search.semantic_search(client, "fake-model", "stress at work", entries, top_k=3)
        assert results[0][0]["id"] == "a"  # most similar to the query
        assert results[0][1] > results[1][1]

    def test_top_k_limits_results(self, semantic_search):
        client = FakeEmbeddingClient()
        entries = [
            {"id": str(i), "type": "mood", "content": f"entry number {i} about stress"}
            for i in range(10)
        ]
        results = semantic_search.semantic_search(client, "fake-model", "stress", entries, top_k=3)
        assert len(results) == 3

    def test_empty_entries_returns_empty(self, semantic_search):
        client = FakeEmbeddingClient()
        assert semantic_search.semantic_search(client, "fake-model", "anything", []) == []

    def test_entries_without_text_excluded_from_results(self, semantic_search):
        client = FakeEmbeddingClient()
        entries = [
            {"id": "a", "type": "mood", "content": "feeling stressed"},
            {"id": "b", "type": "hydration", "glasses": 6},  # no embeddable text
        ]
        results = semantic_search.semantic_search(client, "fake-model", "stress", entries)
        ids = [e["id"] for e, _ in results]
        assert "b" not in ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
