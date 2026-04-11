"""
Tests for the Ollama client (ollama_client.py).
All tests mock the ollama.AsyncClient.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import PlaylistResponse, SuggestedTrack
from app.services.ollama_client import OllamaError, _deduplicate_tracks, generate_playlist


def _make_playlist_response(track_count: int, prefix: str = "Track") -> PlaylistResponse:
    return PlaylistResponse(
        name="Test Playlist",
        description="A great playlist.",
        tracks=[
            SuggestedTrack(title=f"{prefix} {i}", artist=f"Artist {i}", reasoning="Good.")
            for i in range(track_count)
        ],
    )


# ---------------------------------------------------------------------------
# _deduplicate_tracks()
# ---------------------------------------------------------------------------

def test_deduplicate_removes_exact_duplicates() -> None:
    tracks = [
        SuggestedTrack(title="Song A", artist="Artist", reasoning="R"),
        SuggestedTrack(title="Song A", artist="Artist", reasoning="R"),
    ]
    assert len(_deduplicate_tracks(tracks)) == 1


def test_deduplicate_case_insensitive() -> None:
    tracks = [
        SuggestedTrack(title="Song A", artist="artist", reasoning="R"),
        SuggestedTrack(title="song a", artist="ARTIST", reasoning="R"),
    ]
    assert len(_deduplicate_tracks(tracks)) == 1


def test_deduplicate_keeps_distinct_tracks() -> None:
    tracks = [
        SuggestedTrack(title="Song A", artist="Artist", reasoning="R"),
        SuggestedTrack(title="Song B", artist="Artist", reasoning="R"),
    ]
    assert len(_deduplicate_tracks(tracks)) == 2


# ---------------------------------------------------------------------------
# generate_playlist() success path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_playlist_success() -> None:
    playlist = _make_playlist_response(5)
    mock_response = MagicMock()
    mock_response.message.content = playlist.model_dump_json()
    mock_client = AsyncMock()
    mock_client.chat.return_value = mock_response

    with patch("app.services.ollama_client.AsyncClient", return_value=mock_client):
        result = await generate_playlist("sys", "user", 5)

    assert isinstance(result, PlaylistResponse)
    assert len(result.tracks) == 5


@pytest.mark.asyncio
async def test_generate_playlist_trims_to_track_count() -> None:
    playlist = _make_playlist_response(10)
    mock_response = MagicMock()
    mock_response.message.content = playlist.model_dump_json()
    mock_client = AsyncMock()
    mock_client.chat.return_value = mock_response

    with patch("app.services.ollama_client.AsyncClient", return_value=mock_client):
        result = await generate_playlist("sys", "user", 5)

    assert len(result.tracks) == 5


# ---------------------------------------------------------------------------
# JSON retry logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_playlist_retries_on_json_error() -> None:
    valid_playlist = _make_playlist_response(5)
    bad_resp = MagicMock()
    bad_resp.message.content = "NOT VALID JSON {"
    good_resp = MagicMock()
    good_resp.message.content = valid_playlist.model_dump_json()
    mock_client = AsyncMock()
    mock_client.chat.side_effect = [bad_resp, good_resp]

    with patch("app.services.ollama_client.AsyncClient", return_value=mock_client):
        result = await generate_playlist("sys", "user", 5)

    assert isinstance(result, PlaylistResponse)
    assert mock_client.chat.call_count == 2


@pytest.mark.asyncio
async def test_generate_playlist_raises_after_max_json_errors() -> None:
    bad_resp = MagicMock()
    bad_resp.message.content = "NOT JSON"
    mock_client = AsyncMock()
    mock_client.chat.return_value = bad_resp

    with patch("app.services.ollama_client.AsyncClient", return_value=mock_client):
        with pytest.raises(OllamaError, match="invalid JSON"):
            await generate_playlist("sys", "user", 5)

    assert mock_client.chat.call_count == 3


# ---------------------------------------------------------------------------
# Under-count retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_playlist_retries_on_under_count() -> None:
    short = _make_playlist_response(2)   # fewer than requested 5
    extra = _make_playlist_response(5, prefix="Extra")   # supplement
    short_resp = MagicMock()
    short_resp.message.content = short.model_dump_json()
    extra_resp = MagicMock()
    extra_resp.message.content = extra.model_dump_json()
    mock_client = AsyncMock()
    mock_client.chat.side_effect = [short_resp, extra_resp]

    with patch("app.services.ollama_client.AsyncClient", return_value=mock_client):
        result = await generate_playlist("sys", "user", 5)

    assert len(result.tracks) == 5
    assert mock_client.chat.call_count == 2


# ---------------------------------------------------------------------------
# Connection error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_playlist_raises_on_connection_error() -> None:
    mock_client = AsyncMock()
    mock_client.chat.side_effect = ConnectionRefusedError("refused")

    with patch("app.services.ollama_client.AsyncClient", return_value=mock_client):
        with pytest.raises(OllamaError, match="Cannot reach Ollama"):
            await generate_playlist("sys", "user", 5)


# ---------------------------------------------------------------------------
# Deduplication across retries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_playlist_deduplicates_across_retries() -> None:
    """All 3 attempts return the same 3 tracks — dedup keeps only 3, best-effort."""
    same = _make_playlist_response(3)
    # Provide 3 responses (one per MAX_ATTEMPTS) with identical tracks
    make_resp = lambda: MagicMock(**{"message.content": same.model_dump_json()})
    mock_client = AsyncMock()
    mock_client.chat.side_effect = [make_resp(), make_resp(), make_resp()]

    with patch("app.services.ollama_client.AsyncClient", return_value=mock_client):
        result = await generate_playlist("sys", "user", 5)

    # Only 3 unique tracks exist across all attempts — best-effort result
    assert len(result.tracks) <= 3
    assert mock_client.chat.call_count == 3
