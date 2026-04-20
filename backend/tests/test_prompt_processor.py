"""
Tests for the prompt processor (prompt_processor.py).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Track
from app.models.schemas import PlaylistIntent, SeedSelection
from app.services.prompt_processor import (
    build_context_pool,
    build_prompt,
    build_system_prompt,
    extract_keywords,
    parse_intent,
    select_seeds,
)


# ---------------------------------------------------------------------------
# extract_keywords()
# ---------------------------------------------------------------------------

def test_extract_keywords_basic() -> None:
    kws = extract_keywords("chill jazz for a rainy night")
    assert "jazz" in kws
    assert "chill" in kws
    assert "rainy" in kws
    assert "night" in kws
    assert "for" not in kws
    assert "a" not in kws


def test_extract_keywords_deduplicates() -> None:
    kws = extract_keywords("jazz jazz jazz")
    assert kws.count("jazz") == 1


def test_extract_keywords_removes_punctuation() -> None:
    kws = extract_keywords("rock, metal! blues?")
    assert "rock" in kws
    assert "metal" in kws
    assert "blues" in kws


def test_extract_keywords_single_char_removed() -> None:
    kws = extract_keywords("a b c rock")
    assert "rock" in kws
    assert "a" not in kws
    assert "b" not in kws


def test_extract_keywords_empty_string() -> None:
    assert extract_keywords("") == []


def test_extract_keywords_only_stopwords() -> None:
    assert extract_keywords("the and or but for of") == []


# ---------------------------------------------------------------------------
# DB seed helper
# ---------------------------------------------------------------------------

async def _seed_tracks(session: AsyncSession) -> None:
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
    ]
    session.add_all(tracks)
    await session.commit()


# ---------------------------------------------------------------------------
# build_context_pool()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_context_pool_matching_artists(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    pool = await build_context_pool(db_session, ["davis"])
    assert "Miles Davis" in pool["artists"]


@pytest.mark.asyncio
async def test_build_context_pool_matching_genres(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    pool = await build_context_pool(db_session, ["jazz"])
    assert "Jazz" in pool["genres"]


@pytest.mark.asyncio
async def test_build_context_pool_sample_tracks(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    pool = await build_context_pool(db_session, ["jazz"])
    assert len(pool["sample_tracks"]) > 0
    combined = " ".join(pool["sample_tracks"])
    assert "Miles Davis" in combined


@pytest.mark.asyncio
async def test_build_context_pool_falls_back_all_artists(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    pool = await build_context_pool(db_session, ["zzznomatch"])
    assert "Miles Davis" in pool["artists"]
    assert "Queen" in pool["artists"]


@pytest.mark.asyncio
async def test_build_context_pool_empty_keywords(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    pool = await build_context_pool(db_session, [])
    assert len(pool["artists"]) > 0


# ---------------------------------------------------------------------------
# build_system_prompt()
# ---------------------------------------------------------------------------

def test_build_system_prompt_contains_track_count() -> None:
    ctx = {"artists": ["Miles Davis"], "genres": ["Jazz"], "sample_tracks": []}
    prompt = build_system_prompt(ctx, track_count=20)
    assert "20" in prompt


def test_build_system_prompt_contains_artists() -> None:
    ctx = {"artists": ["Miles Davis", "Queen"], "genres": ["Jazz"], "sample_tracks": []}
    prompt = build_system_prompt(ctx, track_count=10)
    assert "Miles Davis" in prompt
    assert "Queen" in prompt


def test_build_system_prompt_contains_schema() -> None:
    ctx = {"artists": [], "genres": [], "sample_tracks": []}
    prompt = build_system_prompt(ctx, track_count=5)
    assert "tracks" in prompt
    assert "description" in prompt


def test_build_system_prompt_empty_context() -> None:
    ctx = {"artists": [], "genres": [], "sample_tracks": []}
    prompt = build_system_prompt(ctx, track_count=10)
    assert "(none found)" in prompt


# ---------------------------------------------------------------------------
# build_prompt() — full pipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_prompt_returns_tuple(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    system_prompt, user_message = await build_prompt(
        db_session, "mellow jazz", search_terms=["jazz", "mellow"], track_count=10
    )
    assert isinstance(system_prompt, str)
    assert isinstance(user_message, str)
    assert len(system_prompt) > 100


@pytest.mark.asyncio
async def test_build_prompt_user_message_contains_prompt(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    _, user_message = await build_prompt(
        db_session, "chill rainy jazz", search_terms=["jazz", "chill"], track_count=5
    )
    assert "chill rainy jazz" in user_message


# ---------------------------------------------------------------------------
# Phase 5: parse_intent() — structured intent extraction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_intent_returns_valid_intent() -> None:
    """Test parse_intent returns a valid PlaylistIntent with required fields."""
    with patch("app.services.prompt_processor.AsyncClient") as mock_client_class:
        # Mock Ollama response
        mock_response = MagicMock()
        mock_response.message.content = '{"mood": "relaxed", "tempo": "slow", "genre_hint": "jazz", "exclude": []}'
        
        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        intent = await parse_intent("chill Sunday morning")
        
        assert isinstance(intent, PlaylistIntent)
        assert intent.mood == "relaxed"
        assert intent.tempo == "slow"
        assert intent.genre_hint == "jazz"
        assert intent.exclude == []


@pytest.mark.asyncio
async def test_parse_intent_with_exclude_list() -> None:
    """Test parse_intent correctly parses exclude list."""
    with patch("app.services.prompt_processor.AsyncClient") as mock_client_class:
        mock_response = MagicMock()
        mock_response.message.content = '{"mood": "happy", "tempo": "fast", "genre_hint": "", "exclude": ["christmas", "sad"]}'
        
        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        intent = await parse_intent("upbeat party songs, but no sad stuff")
        
        assert "christmas" in intent.exclude
        assert "sad" in intent.exclude


@pytest.mark.asyncio
async def test_parse_intent_graceful_failure() -> None:
    """Test parse_intent raises RuntimeError on Ollama failure."""
    with patch("app.services.prompt_processor.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(side_effect=Exception("Ollama unreachable"))
        mock_client_class.return_value = mock_client

        with pytest.raises(RuntimeError):
            await parse_intent("any prompt")


# ---------------------------------------------------------------------------
# Phase 5: select_seeds() — seed selection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_select_seeds_returns_valid_tracks() -> None:
    """Test select_seeds returns Track objects from candidates."""
    tracks = [
        Track(rating_key=1, title="Blue in Green", artist="Miles Davis", genre="Jazz"),
        Track(rating_key=2, title="Bohemian Rhapsody", artist="Queen", genre="Rock"),
        Track(rating_key=3, title="So What", artist="Miles Davis", genre="Jazz"),
    ]
    
    intent = PlaylistIntent(mood="relaxed", tempo="slow", genre_hint="jazz", exclude=[])
    
    with patch("app.services.prompt_processor.AsyncClient") as mock_client_class:
        mock_response = MagicMock()
        # Now that genre-matched tracks are reordered first, indices [1, 2] select the two jazz tracks
        mock_response.message.content = '{"indices": [1, 2]}'
        
        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        selected = await select_seeds(intent, tracks)
        
        assert len(selected) == 2
        assert selected[0].title == "Blue in Green"
        assert selected[1].title == "So What"


@pytest.mark.asyncio
async def test_select_seeds_respects_exclude_list() -> None:
    """Test select_seeds filters candidates by exclude list."""
    tracks = [
        Track(rating_key=1, title="Blue in Green", artist="Miles Davis", genre="Jazz", style="Modal Jazz"),
        Track(rating_key=2, title="Bohemian Rhapsody", artist="Queen", genre="Rock, Christmas"),
        Track(rating_key=3, title="So What", artist="Miles Davis", genre="Jazz"),
    ]
    
    intent = PlaylistIntent(mood="happy", tempo="medium", genre_hint="jazz", exclude=["christmas"])
    
    with patch("app.services.prompt_processor.AsyncClient") as mock_client_class:
        mock_response = MagicMock()
        # Should only receive indices 1 and 2 (Bohemian excluded), so indices refer to filtered list
        mock_response.message.content = '{"indices": [1, 2]}'
        
        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        selected = await select_seeds(intent, tracks)
        
        # Verify no "christmas" tracks selected
        for track in selected:
            assert "christmas" not in (track.genre or "").lower()


@pytest.mark.asyncio
async def test_select_seeds_fallback_to_top_2() -> None:
    """Test select_seeds returns top 2 on parsing failure."""
    tracks = [
        Track(rating_key=1, title="Track1", artist="Artist1", genre="Jazz"),
        Track(rating_key=2, title="Track2", artist="Artist2", genre="Jazz"),
        Track(rating_key=3, title="Track3", artist="Artist3", genre="Jazz"),
    ]
    
    intent = PlaylistIntent(mood="relaxed", tempo="slow", genre_hint="", exclude=[])
    
    with patch("app.services.prompt_processor.AsyncClient") as mock_client_class:
        # Invalid JSON response to trigger fallback
        mock_response = MagicMock()
        mock_response.message.content = "not valid json"
        
        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        selected = await select_seeds(intent, tracks)
        
        # Should fallback to top 2
        assert len(selected) == 2
        assert selected[0].title == "Track1"
        assert selected[1].title == "Track2"

