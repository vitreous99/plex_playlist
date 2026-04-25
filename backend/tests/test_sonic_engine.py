"""
Tests for the Sonic Engine (Phase 3).
"""

import pytest
from unittest.mock import MagicMock, patch
from app.models.tables import Track as DbTrack
from app.services.sonic_engine import (
    expand_with_sonic_similarity,
    build_sonic_adventure,
    _sort_by_bpm_arc,
    _get_bpm,
)


class MockMusicAnalysis:
    def __init__(self, tempo: float):
        self.tempo = tempo


class MockPlexTrack:
    def __init__(self, rating_key, title="Mock", bpm: float | None = None):
        self.ratingKey = rating_key
        self.title = title
        self.musicAnalysis = MockMusicAnalysis(bpm) if bpm is not None else None

    def sonicallySimilar(self, limit=10, maxDistance=0.25):
        # Return mock similar tracks with BPMs so arc ordering has data to work with
        return [
            MockPlexTrack(self.ratingKey + 100, bpm=100.0),
            MockPlexTrack(self.ratingKey + 200, bpm=140.0),
        ]

    def sonicAdventure(self, to):
        # Return a mock path
        return [self, MockPlexTrack(500), MockPlexTrack(600), to]


@patch('app.services.sonic_engine.get_music_section')
def test_sonically_similar_expansion(mock_get_section):
    mock_section = MagicMock()
    mock_get_section.return_value = mock_section

    def mock_fetch(rating_key):
        return MockPlexTrack(rating_key, bpm=120.0)

    mock_section.fetchItem = mock_fetch

    seeds = [DbTrack(rating_key=1), DbTrack(rating_key=2)]

    result = expand_with_sonic_similarity(seeds, target_count=4)

    assert len(result) == 4
    # After BPM arc ordering the seeds won't necessarily be first —
    # assert both seeds appear somewhere in the result instead.
    result_keys = {t.ratingKey for t in result}
    assert 1 in result_keys
    assert 2 in result_keys


@patch('app.services.sonic_engine.get_music_section')
def test_sonic_adventure_bridging(mock_get_section):
    mock_section = MagicMock()
    mock_get_section.return_value = mock_section

    def mock_fetch(rating_key):
        return MockPlexTrack(rating_key)

    mock_section.fetchItem = mock_fetch

    source = DbTrack(rating_key=1)
    target = DbTrack(rating_key=10)

    result = build_sonic_adventure(source, target, target_count=5)

    assert len(result) == 4
    assert result[0].ratingKey == 1
    assert result[-1].ratingKey == 10


@patch('app.services.sonic_engine.get_music_section')
def test_sonic_engine_limits(mock_get_section):
    mock_section = MagicMock()
    mock_get_section.return_value = mock_section

    def mock_fetch(rating_key):
        return MockPlexTrack(rating_key)

    mock_section.fetchItem = mock_fetch

    seeds = [DbTrack(rating_key=1)]

    # Even if sonicallySimilar returns tracks, limit to target_count
    result = expand_with_sonic_similarity(seeds, target_count=2)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# BPM arc unit tests
# ---------------------------------------------------------------------------

def test_bpm_arc_ascending():
    """Tracks should be arranged in ascending BPM order when seeds go low → high."""
    bpms = [160.0, 80.0, 120.0, 100.0, 140.0]
    tracks = [MockPlexTrack(i, bpm=b) for i, b in enumerate(bpms)]
    seed_low = MockPlexTrack(99, bpm=80.0)
    seed_high = MockPlexTrack(100, bpm=160.0)

    result = _sort_by_bpm_arc(tracks, [seed_low, seed_high])

    result_bpms = [_get_bpm(t) for t in result]
    # Result should be monotonically ascending (greedy NN on linear targets)
    assert result_bpms == sorted(bpms)


def test_bpm_arc_descending():
    """Tracks should be arranged in descending BPM order when seeds go high → low."""
    bpms = [80.0, 120.0, 100.0, 140.0, 160.0]
    tracks = [MockPlexTrack(i, bpm=b) for i, b in enumerate(bpms)]
    seed_high = MockPlexTrack(99, bpm=160.0)
    seed_low = MockPlexTrack(100, bpm=80.0)

    result = _sort_by_bpm_arc(tracks, [seed_high, seed_low])

    result_bpms = [_get_bpm(t) for t in result]
    assert result_bpms == sorted(bpms, reverse=True)


def test_bpm_arc_no_bpm_tracks_spliced_to_middle():
    """Tracks without BPM are inserted into the middle of the ordered list."""
    tracks_with_bpm = [MockPlexTrack(i, bpm=float(80 + i * 20)) for i in range(4)]
    track_no_bpm = MockPlexTrack(99)  # no BPM
    all_tracks = tracks_with_bpm + [track_no_bpm]

    seed = MockPlexTrack(50, bpm=80.0)
    result = _sort_by_bpm_arc(all_tracks, [seed, seed])

    assert len(result) == 5
    # The no-BPM track should not be at position 0 or last
    mid = len(result) // 2
    assert result[mid].ratingKey == 99


def test_bpm_arc_single_track_unchanged():
    """A single-element list is returned as-is."""
    tracks = [MockPlexTrack(1, bpm=120.0)]
    result = _sort_by_bpm_arc(tracks, tracks)
    assert result == tracks


def test_bpm_arc_all_no_bpm_unchanged():
    """When no tracks have BPM data, the list is returned as-is."""
    tracks = [MockPlexTrack(i) for i in range(4)]
    result = _sort_by_bpm_arc(tracks, [])
    assert result == tracks


def test_get_bpm_returns_none_without_music_analysis():
    track = MockPlexTrack(1)  # no musicAnalysis
    assert _get_bpm(track) is None


def test_get_bpm_returns_float():
    track = MockPlexTrack(1, bpm=128.5)
    assert _get_bpm(track) == 128.5
