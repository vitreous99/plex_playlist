"""
Vector embedding and semantic search service (Phase 5: Semantic Bridge).

Builds a FAISS flat index of sentence embeddings for all tracks in the
library, enabling fast semantic search without LLM calls or Plex API overhead.

Design:
  - One-time index build triggered after sync completes.
  - Uses sentence-transformers all-MiniLM-L6-v2 (22 MB, 384-dim, fast).
  - FAISS IndexFlatIP for cosine similarity (inner-product normalized vectors).
  - Persists index and rating_key mapping to disk: db/vector_index.faiss, db/vector_index_keys.json
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Lazy imports to avoid hard dependency if not used
try:
    import faiss
    from sentence_transformers import SentenceTransformer
except ImportError:
    logger.warning(
        "FAISS or sentence-transformers not installed. "
        "Vector search will not be available until dependencies are installed."
    )
    faiss = None
    SentenceTransformer = None


# ---------------------------------------------------------------------------
# Module-level configuration
# ---------------------------------------------------------------------------

MODEL_NAME = "all-MiniLM-L6-v2"
VECTOR_INDEX_PATH = Path(__file__).parent.parent.parent.parent / "db" / "vector_index.faiss"
VECTOR_KEYS_PATH = Path(__file__).parent.parent.parent.parent / "db" / "vector_index_keys.json"
BATCH_SIZE = 100  # Embed tracks in batches to manage memory

# ---------------------------------------------------------------------------
# Module-level singletons — loaded once, reused across requests
# ---------------------------------------------------------------------------

_model: "SentenceTransformer | None" = None  # type: ignore[type-arg]
_index: "faiss.Index | None" = None  # type: ignore[type-arg]
_rating_keys: list[int] = []
_singleton_lock = threading.Lock()


def _load_search_singletons(
    index_path: Path | None = None,
    keys_path: Path | None = None,
) -> tuple["SentenceTransformer", "faiss.Index", list[int]]:  # type: ignore[type-arg]
    """Load (or return cached) the sentence-transformer model and FAISS index.

    If explicit override paths are supplied (used in tests), those are loaded
    directly without touching or polluting the module-level singletons.

    Thread-safe: uses a module-level lock so concurrent first requests don't
    race to load the model simultaneously.
    """
    global _model, _index, _rating_keys

    idx_path = index_path or VECTOR_INDEX_PATH
    key_path = keys_path or VECTOR_KEYS_PATH

    # When explicit paths are given (test mode), load fresh without caching
    if index_path is not None or keys_path is not None:
        if not idx_path.exists() or not key_path.exists():
            raise FileNotFoundError(
                f"Vector index not found at {idx_path}. Run a library sync first."
            )
        model_instance = _model
        if model_instance is None:
            with _singleton_lock:
                if _model is None:
                    logger.info("Loading SentenceTransformer model '%s' (first call)…", MODEL_NAME)
                    _model = SentenceTransformer(MODEL_NAME)
                model_instance = _model
        index_instance = faiss.read_index(str(idx_path))
        with open(key_path, "r") as f:
            keys = json.load(f)
        return model_instance, index_instance, keys

    with _singleton_lock:
        if _model is None:
            logger.info("Loading SentenceTransformer model '%s' (first call)…", MODEL_NAME)
            _model = SentenceTransformer(MODEL_NAME)

        if _index is None or not _rating_keys:
            if not idx_path.exists() or not key_path.exists():
                raise FileNotFoundError(
                    f"Vector index not found at {idx_path}. Run a library sync first."
                )
            logger.info("Loading FAISS index from %s (first call)…", idx_path)
            _index = faiss.read_index(str(idx_path))
            with open(key_path, "r") as f:
                _rating_keys = json.load(f)

    return _model, _index, _rating_keys


def invalidate_search_singletons() -> None:
    """Discard cached index/keys so the next search call reloads from disk.

    Call this after ``build_vector_index`` completes to pick up the new index.
    """
    global _index, _rating_keys
    with _singleton_lock:
        _index = None
        _rating_keys = []
    logger.info("Vector search singletons invalidated — will reload on next search.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def build_vector_index(
    session: AsyncSession,
    db_path: str | None = None,
    force_rebuild: bool = False,
) -> tuple[int, float]:
    """Build semantic vector index for all tracks in the database.

    One-time operation called after library sync completes. Embeds each track's
    metadata (artist, title, album, genre, style) into a dense vector, then
    persists the FAISS index and rating_key mapping to disk.

    Args:
        session:       Async DB session with access to tracks table.
        db_path:       Optional explicit path to vector_index.faiss (for testing).
        force_rebuild: If True, rebuild even if index already exists.

    Returns:
        (num_embedded, elapsed_seconds): Count of embedded tracks and build time.

    Raises:
        ImportError: If FAISS or sentence-transformers not installed.
        RuntimeError: If no tracks found in database.
    """
    if faiss is None or SentenceTransformer is None:
        raise ImportError(
            "FAISS and sentence-transformers required for vector indexing. "
            "Run: pip install faiss-cpu sentence-transformers"
        )

    import time

    start_time = time.time()

    # Load all tracks from database
    from app.models.tables import Track

    result = await session.execute(select(Track))
    all_tracks = result.scalars().all()

    if not all_tracks:
        raise RuntimeError("No tracks found in database; cannot build vector index.")

    logger.info(f"Building vector index for {len(all_tracks)} tracks using {MODEL_NAME}...")

    # Initialize model (downloads if first time, caches thereafter)
    model = SentenceTransformer(MODEL_NAME)
    dimension = model.get_sentence_embedding_dimension()

    # Build descriptions and embed in batches
    descriptions = []
    rating_keys = []

    for track in all_tracks:
        desc = _build_track_description(track)
        descriptions.append(desc)
        rating_keys.append(track.rating_key)

    logger.debug(f"Sample description: {descriptions[0] if descriptions else '(empty)'}")

    # Embed all descriptions in batches
    embeddings = []
    for i in range(0, len(descriptions), BATCH_SIZE):
        batch = descriptions[i : i + BATCH_SIZE]
        batch_embeddings = model.encode(batch, convert_to_numpy=True, show_progress_bar=False)
        embeddings.extend(batch_embeddings)
        logger.debug(f"Embedded batch {i // BATCH_SIZE + 1}/{(len(descriptions) + BATCH_SIZE - 1) // BATCH_SIZE}")

    # Normalize embeddings for cosine similarity (FAISS IndexFlatIP expects normalized vectors)
    embeddings = np.array(embeddings, dtype=np.float32)
    faiss.normalize_L2(embeddings)

    # Create FAISS index
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)

    # Persist index and mapping
    index_path = Path(db_path) if db_path else VECTOR_INDEX_PATH
    keys_path = Path(db_path).with_suffix(".json") if db_path else VECTOR_KEYS_PATH

    index_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))

    with open(keys_path, "w") as f:
        json.dump(rating_keys, f)

    elapsed = time.time() - start_time
    logger.info(
        f"Vector index built: {len(all_tracks)} tracks, {dimension}-dim, "
        f"{index.ntotal} vectors in FAISS index. "
        f"Saved to {index_path} and {keys_path}. Elapsed: {elapsed:.2f}s"
    )

    return len(all_tracks), elapsed


def search_vector_index(
    query: str,
    top_k: int = 40,
    index_path: str | None = None,
    keys_path: str | None = None,
) -> list[int]:
    """Search the vector index for tracks semantically similar to query.

    Uses module-level singletons for the SentenceTransformer model and FAISS
    index so that neither is reloaded from disk on each call.

    Args:
        query:       Natural-language query (e.g., "relaxed jazz").
        top_k:       Number of results to return (default 40).
        index_path:  Explicit path to vector_index.faiss (for testing / overrides singleton).
        keys_path:   Explicit path to vector_index_keys.json (for testing / overrides singleton).

    Returns:
        List of rating_keys (Plex track IDs) ranked by similarity.

    Raises:
        ImportError: If FAISS or sentence-transformers not installed.
        FileNotFoundError: If index files not found on disk.
        RuntimeError: If index is empty or corrupted.
    """
    if faiss is None or SentenceTransformer is None:
        raise ImportError(
            "FAISS and sentence-transformers required for vector search. "
            "Run: pip install faiss-cpu sentence-transformers"
        )

    # Resolve explicit override paths (used in tests)
    idx_override = Path(index_path) if index_path else None
    key_override = Path(keys_path) if keys_path else None

    try:
        model, index, rating_keys = _load_search_singletons(idx_override, key_override)
    except FileNotFoundError as e:
        logger.warning(str(e) + " — returning empty results.")
        return []

    if index.ntotal == 0:
        logger.warning("Vector index is empty. No tracks to search.")
        return []

    # Embed query and search
    query_embedding = model.encode(query, convert_to_numpy=True)
    query_embedding = np.array([query_embedding], dtype=np.float32)
    faiss.normalize_L2(query_embedding)

    distances, indices = index.search(query_embedding, min(top_k, index.ntotal))

    # Map FAISS indices to rating_keys
    result_keys = [rating_keys[int(idx)] for idx in indices[0] if idx < len(rating_keys)]

    logger.debug(
        f"Vector search for '{query}': found {len(result_keys)} results. "
        f"Top 3 distances: {distances[0][:3]}"
    )

    return result_keys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_track_description(track) -> str:
    """Build a plain-English description of a track for embedding.

    Combines title, artist, album, genre, and style into a narrative
    string that captures the track's semantic content.
    """
    parts = []

    if track.artist:
        parts.append(f"Artist: {track.artist}")
    if track.title:
        parts.append(f"Title: {track.title}")
    if track.album:
        parts.append(f"Album: {track.album}")
    if track.genre:
        parts.append(f"Genre: {track.genre}")
    if track.style:
        parts.append(f"Mood: {track.style}")

    return " | ".join(parts)
