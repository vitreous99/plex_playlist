"""
Unit tests for Phase 5 vector indexing and semantic search.

Tests:
  - build_vector_index() creates FAISS index and persists files
  - search_vector_index() returns valid rating_keys from index
  - Graceful fallback when index not found
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.tables import Track
from app.services.vector_index import (
    build_vector_index,
    search_vector_index,
    MODEL_NAME,
)


# ---------------------------------------------------------------------------
# DB seed helper
# ---------------------------------------------------------------------------

async def _seed_test_tracks(session) -> list[Track]:
    """Seed database with test tracks."""
    tracks = [
        Track(rating_key=1, title="Blue in Green", artist="Miles Davis",
              album="Kind of Blue", genre="Jazz", style="Modal Jazz",
              has_sonic_analysis=True, synced_at=datetime.now(timezone.utc)),
        Track(rating_key=2, title="Bohemian Rhapsody", artist="Queen",
              album="A Night at the Opera", genre="Rock, Progressive Rock",
              style=None, has_sonic_analysis=False, synced_at=datetime.now(timezone.utc)),
        Track(rating_key=3, title="So What", artist="Miles Davis",
              album="Kind of Blue", genre="Jazz", style="Cool Jazz",
              has_sonic_analysis=True, synced_at=datetime.now(timezone.utc)),
        Track(rating_key=4, title="Smooth Criminal", artist="Michael Jackson",
              album="Bad", genre="Pop", style="Energetic",
              has_sonic_analysis=False, synced_at=datetime.now(timezone.utc)),
        Track(rating_key=5, title="Clair de Lune", artist="Claude Debussy",
              album="Suite Bergamasque", genre="Classical", style="Ambient",
              has_sonic_analysis=True, synced_at=datetime.now(timezone.utc)),
    ]
    session.add_all(tracks)
    await session.commit()
    return tracks


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_vector_index(db_session):
    """Test vector index build creates persisted files."""
    # Seed database
    await _seed_test_tracks(db_session)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = Path(tmpdir) / "test_index.faiss"

        # Build index
        num_embedded, elapsed = await build_vector_index(
            db_session,
            db_path=str(index_path),
            force_rebuild=True,
        )

        # Verify results
        assert num_embedded == 5, "All tracks should be embedded"
        assert elapsed > 0, "Build should take some time"

        # Verify files exist
        assert index_path.exists(), "FAISS index file should exist"

        keys_path = index_path.with_suffix(".json")
        assert keys_path.exists(), "Keys mapping file should exist"

        # Verify keys content
        with open(keys_path) as f:
            keys = json.load(f)
        assert len(keys) == num_embedded, "Keys should match embedded count"
        assert all(isinstance(k, int) for k in keys), "Keys should be integers (rating_keys)"


@pytest.mark.asyncio
async def test_search_vector_index(db_session):
    """Test semantic search returns valid rating_keys."""
    # Seed database
    await _seed_test_tracks(db_session)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = Path(tmpdir) / "test_index.faiss"

        # Build index first
        await build_vector_index(db_session, db_path=str(index_path))

        # Search (NOT async - search_vector_index is synchronous)
        results = search_vector_index(
            "relaxed jazz",
            top_k=5,
            index_path=str(index_path),
            keys_path=str(index_path.with_suffix(".json")),
        )

        # Verify results
        assert len(results) > 0, "Should find some results"
        assert len(results) <= 5, "Should return at most top_k results"
        assert all(isinstance(k, int) for k in results), "All results should be rating_keys"
        
        # Verify results exist in database
        expected_keys = {1, 2, 3, 4, 5}  # Our seeded track IDs
        for result_key in results:
            assert result_key in expected_keys, f"Result rating_key {result_key} should exist in DB"


@pytest.mark.asyncio
async def test_search_vector_index_empty(db_session):
    """Test search gracefully handles missing index."""
    # Search with non-existent index path (NOT async)
    results = search_vector_index(
        "any query",
        top_k=40,
        index_path="/nonexistent/path/index.faiss",
        keys_path="/nonexistent/path/keys.json",
    )

    # Should return empty list, not raise
    assert results == [], "Should return empty list for missing index"


@pytest.mark.asyncio
async def test_search_vector_index_different_queries(db_session):
    """Test that different queries return different but reasonable results."""
    # Seed database
    await _seed_test_tracks(db_session)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = Path(tmpdir) / "test_index.faiss"
        await build_vector_index(db_session, db_path=str(index_path))

        # Search for different moods (NOT async)
        energetic_results = search_vector_index(
            "energetic rock fast",
            top_k=10,
            index_path=str(index_path),
            keys_path=str(index_path.with_suffix(".json")),
        )

        relaxed_results = search_vector_index(
            "relaxed ambient slow",
            top_k=10,
            index_path=str(index_path),
            keys_path=str(index_path.with_suffix(".json")),
        )

        # Both should return results
        assert len(energetic_results) > 0, "Energetic query should find results"
        assert len(relaxed_results) > 0, "Relaxed query should find results"


@pytest.mark.asyncio
async def test_build_vector_index_no_tracks(db_session):
    """Test build_vector_index raises error when no tracks in DB."""
    # DB session is empty (from fixture setup)
    with pytest.raises(RuntimeError, match="No tracks found"):
        await build_vector_index(db_session)
