"""
Hermes Life OS - Semantic Memory Search
===========================================
recall() in tools.py does substring matching - "stressed" won't find an
entry that says "overwhelmed" but never uses that exact word. This adds
meaning-based search using text embeddings, entirely local and free via
Ollama (or OpenAI, if you'd rather use that).

    EMBEDDING_PROVIDER   ollama | openai   (default: openai if
                         OPENAI_API_KEY is set, else ollama)
    EMBEDDING_MODEL      overrides the provider's default model

Ollama default model: nomic-embed-text (pull it first: `ollama pull
nomic-embed-text`). OpenAI default: text-embedding-3-small.

Embeddings are cached per entry (keyed by a hash of the entry's text,
so an edited entry is automatically re-embedded) in
~/.hermes/life-os/embeddings_cache.json - re-running search doesn't
recompute embeddings for entries that haven't changed.

Anthropic and OpenRouter aren't supported here (no reliable embeddings
endpoint through the same client shape) - this is independent of
whichever provider your chat conversation is using.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import storage

EMBEDDING_DEFAULT_MODELS = {
    "ollama": "nomic-embed-text",
    "openai": "text-embedding-3-small",
}


class EmbeddingProviderError(RuntimeError):
    pass


def resolve_embedding_provider(explicit: Optional[str] = None) -> str:
    if explicit:
        if explicit not in EMBEDDING_DEFAULT_MODELS:
            raise EmbeddingProviderError(
                f"Unknown embedding provider '{explicit}'. Choose from: "
                f"{', '.join(EMBEDDING_DEFAULT_MODELS)}"
            )
        return explicit

    env_choice = os.environ.get("EMBEDDING_PROVIDER")
    if env_choice:
        if env_choice not in EMBEDDING_DEFAULT_MODELS:
            raise EmbeddingProviderError(
                f"Unknown EMBEDDING_PROVIDER '{env_choice}'. Choose from: "
                f"{', '.join(EMBEDDING_DEFAULT_MODELS)}"
            )
        return env_choice

    return "openai" if os.environ.get("OPENAI_API_KEY") else "ollama"


def default_embedding_model(provider: str) -> str:
    return EMBEDDING_DEFAULT_MODELS[provider]


def get_embedding_client(provider: str):
    """Reuses llm_providers.get_client() - ollama/openai both expose an
    OpenAI-compatible client, which is all embeddings.create() needs."""
    if provider not in EMBEDDING_DEFAULT_MODELS:
        raise EmbeddingProviderError(
            f"'{provider}' doesn't support embeddings here. Choose from: "
            f"{', '.join(EMBEDDING_DEFAULT_MODELS)}"
        )
    from llm_providers import get_client
    return get_client(provider)


def get_embedding(client, model: str, text: str) -> List[float]:
    resp = client.embeddings.create(model=model, input=text)
    return resp.data[0].embedding


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def entry_text(entry: Dict[str, Any]) -> str:
    """Builds the text an entry gets embedded from - its type plus
    whatever free-text fields it has. Returns "" for entries with no
    free-text field at all (e.g. a bare hydration count), which callers
    should skip embedding entirely - the type name alone ("hydration")
    isn't meaningful enough to search on."""
    text_parts = []
    for key in ("content", "note", "description", "last_note"):
        value = entry.get(key)
        if value:
            text_parts.append(str(value))
    if not text_parts:
        return ""
    entry_type = entry.get("type")
    if entry_type:
        text_parts.insert(0, str(entry_type))
    return " ".join(text_parts).strip()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _cache_path() -> Path:
    return storage.HERMES_DIR / "embeddings_cache.json"


def _load_cache() -> Dict[str, Dict[str, Any]]:
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: Dict[str, Dict[str, Any]]) -> None:
    _cache_path().write_text(json.dumps(cache), encoding="utf-8")


def ensure_embeddings(client, model: str, entries: List[Dict[str, Any]]) -> Dict[str, List[float]]:
    """Returns {entry_id: vector} for every entry that has embeddable
    text, computing and caching only what's missing or changed since
    last time (cache key includes a hash of the entry's text, so an
    edited entry - see correct_entry - is transparently re-embedded)."""
    cache = _load_cache()
    vectors: Dict[str, List[float]] = {}
    dirty = False

    for entry in entries:
        entry_id = entry.get("id")
        text = entry_text(entry)
        if not entry_id or not text:
            continue
        text_hash = _text_hash(text)
        cached = cache.get(entry_id)
        if cached and cached.get("text_hash") == text_hash:
            vectors[entry_id] = cached["vector"]
            continue
        vector = get_embedding(client, model, text)
        cache[entry_id] = {"text_hash": text_hash, "vector": vector}
        vectors[entry_id] = vector
        dirty = True

    if dirty:
        _save_cache(cache)
    return vectors


def semantic_search(
    client, model: str, query: str, entries: List[Dict[str, Any]], top_k: int = 5,
) -> List[Tuple[Dict[str, Any], float]]:
    """Ranks `entries` by embedding similarity to `query`, most similar
    first. Entries with no embeddable text are skipped entirely."""
    vectors = ensure_embeddings(client, model, entries)
    if not vectors:
        return []
    query_vector = get_embedding(client, model, query)

    scored = [
        (entry, cosine_similarity(query_vector, vectors[entry["id"]]))
        for entry in entries
        if entry.get("id") in vectors
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_k]
