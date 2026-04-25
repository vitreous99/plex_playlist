"""
Tests for the metadata sync service (sync.py).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import SyncStatus
from app.models.tables import Track
from app.services.plex_client import PlexConnectionError
from app.services.sync import _join_tags, get_sync_status, run_sync


# ---------------------------------------------------------------------------
# _join_tags helper
# ---------------------------------------------------------------------------

def test_join_tags_empty() -> None:
    assert _join_tags([]) is None


def test_join_tags_single() -> None:
    tag = MagicMock()
    tag.tag = "Rock"
    assert _join_tags([tag]) == "Rock"


def test_join_tags_multiple() -> None:
    tags = [MagicMock(tag="Jazz"), MagicMock(tag="Blues")]
    result = _join_tags(tags)
    assert "Jazz" in result
    assert "Blues" in result


def test_join_tags_filters_empty_tags() -> None:
    tags = [MagicMock(tag="Rock"), MagicMock(tag=""), MagicMock(tag="Pop")]
    result = _join_tags(tags)
    assert result == "Rock, Pop"


# ---------------------------------------------------------------------------
# get_sync_status()
# ---------------------------------------------------------------------------

def test_get_sync_status_initial() -> None:
    status = get_sync_status()
    assert status.synced_tracks == 0
    assert status.total_tracks == 0
    assert status.in_progress is False
    assert status.last_synced_at is None


# ---------------------------------------------------------------------------
# Mock Plex track factory
# ---------------------------------------------------------------------------

def _make_mock_track(
    rating_key: int,
    title: str,
    artist: str = "Artist",
    album: str = "Album",
    genre_tags: list = None,
    mood_tags: list = None,
    has_sonic: bool = False,
    bpm: float | None = None,
) -> MagicMock:
    track = MagicMock()
    track.ratingKey = rating_key
    track.title = title
    track.grandparentTitle = artist
    track.parentTitle = album
    track.genres = genre_tags or []
    track.moods = mood_tags or []
    track.hasSonicAnalysis = has_sonic
    if bpm is not None:
        track.musicAnalysis.tempo = bpm
    else:
        # Simulate missing musicAnalysis (AttributeError on access)
        del track.musicAnalysis
    return track


# ---------------------------------------------------------------------------
# run_sync()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_sync_upserts_tracks(db_session: AsyncSession) -> None:
    mock_tracks = [
        _make_mock_track(1, "Song A", "Artist A"),
        _make_mock_track(2, "Song B", "Artist B"),
        _make_mock_track(3, "Song C", "Artist C"),
    ]
    mock_section = MagicMock()
    mock_section.title = "Music"
    mock_section.searchTracks.return_value = mock_tracks

    with patch("app.services.sync.get_music_section", return_value=mock_section):
        status = await run_sync(db_session)

    assert status.synced_tracks == 3
    assert status.total_tracks == 3
    assert status.in_progress is False
    assert status.last_synced_at is not None

    result = await db_session.execute(select(Track))
    db_tracks = result.scalars().all()
    assert len(db_tracks) == 3
    titles = {t.title for t in db_tracks}
    assert "Song A" in titles
    assert "Song C" in titles


@pytest.mark.asyncio
async def test_run_sync_upserts_on_conflict(db_session: AsyncSession) -> None:
    """run_sync() updates existing tracks rather than failing on duplicate rating_key."""
    import app.services.sync as sync_service

    mock_section = MagicMock()
    mock_section.title = "Music"
    mock_section.searchTracks.return_value = [_make_mock_track(1, "Original Title")]
    with patch("app.services.sync.get_music_section", return_value=mock_section):
        await run_sync(db_session)

    # Reset for second sync
    sync_service._sync_state = SyncStatus()
    mock_section.searchTracks.return_value = [_make_mock_track(1, "Updated Title")]
    with patch("app.services.sync.get_music_section", return_value=mock_section):
        await run_sync(db_session)

    result = await db_session.execute(select(Track).where(Track.rating_key == 1))
    track = result.scalar_one()
    assert track.title == "Updated Title"


@pytest.mark.asyncio
async def test_run_sync_stores_genres(db_session: AsyncSession) -> None:
    genre1 = MagicMock(tag="Jazz")
    genre2 = MagicMock(tag="Blues")
    mock_track = _make_mock_track(10, "Jazz Song", genre_tags=[genre1, genre2])
    mock_section = MagicMock()
    mock_section.title = "Music"
    mock_section.searchTracks.return_value = [mock_track]

    with patch("app.services.sync.get_music_section", return_value=mock_section):
        await run_sync(db_session)

    result = await db_session.execute(select(Track).where(Track.rating_key == 10))
    track = result.scalar_one()
    assert "Jazz" in track.genre
    assert "Blues" in track.genre


@pytest.mark.asyncio
async def test_run_sync_stores_bpm(db_session: AsyncSession) -> None:
    mock_track = _make_mock_track(20, "Tempo Track", bpm=128.0)
    mock_section = MagicMock()
    mock_section.title = "Music"
    mock_section.searchTracks.return_value = [mock_track]

    with patch("app.services.sync.get_music_section", return_value=mock_section):
        await run_sync(db_session)

    result = await db_session.execute(select(Track).where(Track.rating_key == 20))
    track = result.scalar_one()
    assert track.bpm == 128.0


@pytest.mark.asyncio
async def test_run_sync_stores_null_bpm_when_no_analysis(db_session: AsyncSession) -> None:
    mock_track = _make_mock_track(21, "No BPM Track")  # bpm=None → no musicAnalysis
    mock_section = MagicMock()
    mock_section.title = "Music"
    mock_section.searchTracks.return_value = [mock_track]

    with patch("app.services.sync.get_music_section", return_value=mock_section):
        await run_sync(db_session)

    result = await db_session.execute(select(Track).where(Track.rating_key == 21))
    track = result.scalar_one()
    assert track.bpm is None


@pytest.mark.asyncio
async def test_run_sync_skips_if_in_progress(db_session: AsyncSession) -> None:
    import app.services.sync as sync_service
    sync_service._sync_state = SyncStatus(in_progress=True, synced_tracks=5, total_tracks=100)

    with patch("app.services.sync.get_music_section") as mock_section:
        status = await run_sync(db_session)
        mock_section.assert_not_called()

    assert status.in_progress is True


@pytest.mark.asyncio
async def test_run_sync_raises_on_plex_error(db_session: AsyncSession) -> None:
    with patch(
        "app.services.sync.get_music_section",
        side_effect=PlexConnectionError("Cannot connect"),
    ):
        with pytest.raises(PlexConnectionError):
            await run_sync(db_session)

    status = get_sync_status()
    assert status.in_progress is False


@pytest.mark.asyncio
async def test_run_sync_empty_library(db_session: AsyncSession) -> None:
    mock_section = MagicMock()
    mock_section.title = "Music"
    mock_section.searchTracks.return_value = []

    with patch("app.services.sync.get_music_section", return_value=mock_section):
        status = await run_sync(db_session)

    assert status.synced_tracks == 0
    assert status.total_tracks == 0
    assert status.in_progress is False
