"""
Tests for the SSE streaming module (app.api.stream).

Regression tests for JSON serialization of track objects in SSE events.
"""

import json

import pytest

from app.api.stream import StreamEvent, sse_format


# ---------------------------------------------------------------------------
# Mock objects simulating PlexTrack and DbTrack behaviours
# ---------------------------------------------------------------------------

class FakePlexTrack:
    """Mimics a plexapi Track where .artist is a method, not a string."""

    def __init__(self, title: str, artist_name: str, rating_key: int = 1):
        self.title = title
        self.grandparentTitle = artist_name
        self.ratingKey = rating_key

    def artist(self):
        """plexapi returns an Artist object; this is a method, NOT a str."""
        return type("Artist", (), {"title": self.grandparentTitle})()


class FakeDbTrack:
    """Mimics a DB Track where .artist is a plain string attribute."""

    def __init__(self, title: str, artist: str):
        self.title = title
        self.artist = artist


# ---------------------------------------------------------------------------
# sse_format — StreamEvent objects
# ---------------------------------------------------------------------------

class TestSseFormatStreamEvent:
    def test_basic_stream_event(self):
        event = StreamEvent(
            phase="llm", step="llm_call", message="Calling LLM"
        )
        result = sse_format(event)
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        payload = json.loads(result.removeprefix("data: "))
        assert payload["phase"] == "llm"
        assert payload["step"] == "llm_call"

    def test_stream_event_with_detail(self):
        event = StreamEvent(
            phase="matching",
            step="matching_complete",
            message="Done",
            detail={"matched": 5, "total": 10},
            timing_ms=123,
            progress=0.75,
        )
        payload = json.loads(sse_format(event).removeprefix("data: "))
        assert payload["detail"]["matched"] == 5
        assert payload["timing_ms"] == 123
        assert payload["progress"] == 0.75


# ---------------------------------------------------------------------------
# sse_format — dict events (from external callbacks)
# ---------------------------------------------------------------------------

class TestSseFormatDict:
    def test_plain_dict_event(self):
        event = {"phase": "sonic", "step": "seed_1", "message": "Searching..."}
        result = sse_format(event)
        payload = json.loads(result.removeprefix("data: "))
        assert payload["phase"] == "sonic"


# ---------------------------------------------------------------------------
# Regression: PlexTrack.artist is a method — must not reach json.dumps
# ---------------------------------------------------------------------------

class TestTrackArtistSerialization:
    """Regression for TypeError: Object of type method is not JSON serializable."""

    def _build_final_event_detail(self, final_tracks):
        """Reproduce the exact detail-building logic from stream.py run_pipeline."""
        return {
            "generation_id": "test-id",
            "playlist_name": "Test Playlist",
            "playlist_description": "A test",
            "tracks": [
                {
                    "title": t.title if hasattr(t, "title") else str(t),
                    "artist": (
                        getattr(t, "grandparentTitle", None)
                        or (t.artist if isinstance(getattr(t, "artist", None), str) else "")
                    ),
                }
                for t in final_tracks[:10]
            ],
            "total_tracks": len(final_tracks),
        }

    def test_plex_track_artist_method_does_not_crash(self):
        """PlexTrack.artist is a method — serialization must use grandparentTitle."""
        tracks = [FakePlexTrack("Bohemian Rhapsody", "Queen")]
        detail = self._build_final_event_detail(tracks)

        # Must not raise TypeError
        serialized = json.dumps(detail)
        parsed = json.loads(serialized)
        assert parsed["tracks"][0]["artist"] == "Queen"
        assert parsed["tracks"][0]["title"] == "Bohemian Rhapsody"

    def test_db_track_string_artist_works(self):
        """DbTrack.artist is a plain string — should serialize normally."""
        tracks = [FakeDbTrack("Yesterday", "The Beatles")]
        detail = self._build_final_event_detail(tracks)

        serialized = json.dumps(detail)
        parsed = json.loads(serialized)
        assert parsed["tracks"][0]["artist"] == "The Beatles"

    def test_mixed_track_types(self):
        """Mix of PlexTrack and DbTrack objects in the same list."""
        tracks = [
            FakePlexTrack("Stairway to Heaven", "Led Zeppelin"),
            FakeDbTrack("Let It Be", "The Beatles"),
            FakePlexTrack("Paranoid", "Black Sabbath"),
        ]
        detail = self._build_final_event_detail(tracks)

        serialized = json.dumps(detail)
        parsed = json.loads(serialized)
        assert parsed["tracks"][0]["artist"] == "Led Zeppelin"
        assert parsed["tracks"][1]["artist"] == "The Beatles"
        assert parsed["tracks"][2]["artist"] == "Black Sabbath"
        assert parsed["total_tracks"] == 3

    def test_track_without_grandparent_or_artist(self):
        """Object with neither grandparentTitle nor string artist → empty string."""
        obj = type("Bare", (), {"title": "Unknown Track"})()
        detail = self._build_final_event_detail([obj])

        serialized = json.dumps(detail)
        parsed = json.loads(serialized)
        assert parsed["tracks"][0]["artist"] == ""

    def test_full_sse_format_with_plex_tracks(self):
        """End-to-end: StreamEvent containing PlexTrack detail → valid SSE line."""
        tracks = [FakePlexTrack("Comfortably Numb", "Pink Floyd")]
        event = StreamEvent(
            phase="complete",
            step="done",
            message="Ready to play or save",
            detail={
                "generation_id": "abc",
                "tracks": [
                    {
                        "title": t.title,
                        "artist": getattr(t, "grandparentTitle", ""),
                    }
                    for t in tracks
                ],
            },
            progress=1.0,
        )
        result = sse_format(event)
        payload = json.loads(result.removeprefix("data: "))
        assert payload["detail"]["tracks"][0]["artist"] == "Pink Floyd"
