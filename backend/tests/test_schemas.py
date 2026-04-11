"""
Tests for Pydantic schemas (schemas.py).
"""

import pytest
from pydantic import ValidationError

from app.models.schemas import PlaylistResponse, PromptRequest, SuggestedTrack, SyncStatus


# ---------------------------------------------------------------------------
# SuggestedTrack
# ---------------------------------------------------------------------------

def test_suggested_track_valid() -> None:
    t = SuggestedTrack(
        title="Bohemian Rhapsody",
        artist="Queen",
        album="A Night at the Opera",
        reasoning="Epic rock classic.",
    )
    assert t.title == "Bohemian Rhapsody"
    assert t.artist == "Queen"
    assert t.album == "A Night at the Opera"


def test_suggested_track_album_optional() -> None:
    t = SuggestedTrack(title="Song", artist="Artist", reasoning="Good track.")
    assert t.album is None


def test_suggested_track_strips_whitespace() -> None:
    t = SuggestedTrack(title="  Song  ", artist=" Artist ", reasoning="OK")
    assert t.title == "Song"
    assert t.artist == "Artist"


def test_suggested_track_missing_required_fields() -> None:
    with pytest.raises(ValidationError):
        SuggestedTrack(title="Song")  # missing artist and reasoning


# ---------------------------------------------------------------------------
# PlaylistResponse
# ---------------------------------------------------------------------------

def test_playlist_response_valid() -> None:
    playlist = PlaylistResponse(
        name="Chill Jazz",
        description="Relaxing jazz tunes.",
        tracks=[
            SuggestedTrack(title="Blue in Green", artist="Miles Davis", reasoning="Mellow."),
        ],
    )
    assert playlist.name == "Chill Jazz"
    assert len(playlist.tracks) == 1


def test_playlist_response_empty_tracks() -> None:
    playlist = PlaylistResponse(name="Empty", description="No tracks yet.")
    assert playlist.tracks == []


def test_playlist_response_json_schema_is_valid() -> None:
    """PlaylistResponse.model_json_schema() returns a valid JSON schema dict."""
    schema = PlaylistResponse.model_json_schema()
    assert "properties" in schema
    assert "tracks" in schema["properties"]
    assert "name" in schema["properties"]
    assert "description" in schema["properties"]


def test_playlist_response_serializes_to_json() -> None:
    """PlaylistResponse can be serialised to a JSON-compatible dict."""
    playlist = PlaylistResponse(
        name="Test",
        description="Desc",
        tracks=[SuggestedTrack(title="T", artist="A", reasoning="R")],
    )
    data = playlist.model_dump(mode="json")
    assert data["name"] == "Test"
    assert len(data["tracks"]) == 1


# ---------------------------------------------------------------------------
# PromptRequest
# ---------------------------------------------------------------------------

def test_prompt_request_defaults() -> None:
    req = PromptRequest(prompt="chill jazz for a rainy night")
    assert req.track_count == 20


def test_prompt_request_custom_count() -> None:
    req = PromptRequest(prompt="upbeat workout music", track_count=50)
    assert req.track_count == 50


def test_prompt_request_min_length_enforced() -> None:
    with pytest.raises(ValidationError):
        PromptRequest(prompt="ab")  # too short


def test_prompt_request_max_count_enforced() -> None:
    with pytest.raises(ValidationError):
        PromptRequest(prompt="valid prompt", track_count=101)  # exceeds max


def test_prompt_request_zero_count_rejected() -> None:
    with pytest.raises(ValidationError):
        PromptRequest(prompt="valid prompt", track_count=0)


# ---------------------------------------------------------------------------
# SyncStatus
# ---------------------------------------------------------------------------

def test_sync_status_defaults() -> None:
    status = SyncStatus()
    assert status.synced_tracks == 0
    assert status.total_tracks == 0
    assert status.in_progress is False
    assert status.last_synced_at is None


def test_sync_status_model_dump_json() -> None:
    """SyncStatus serialises to a JSON-safe dict."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    status = SyncStatus(synced_tracks=10, total_tracks=100,
                        last_synced_at=now, in_progress=True)
    data = status.model_dump(mode="json")
    assert data["synced_tracks"] == 10
    assert data["in_progress"] is True
    assert data["last_synced_at"] is not None
