"""
Tests for the database schema and ORM models.

Validates that the Track model can be created, queried, and
that constraints (unique rating_key) are enforced.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Track


@pytest.mark.asyncio
async def test_create_track(db_session: AsyncSession) -> None:
    """A Track row can be inserted and retrieved."""
    track = Track(
        rating_key=12345,
        title="Bohemian Rhapsody",
        artist="Queen",
        album="A Night at the Opera",
        genre="Rock",
        style="Progressive Rock",
        has_sonic_analysis=True,
        synced_at=datetime.now(timezone.utc),
    )
    db_session.add(track)
    await db_session.commit()

    result = await db_session.execute(select(Track).where(Track.rating_key == 12345))
    fetched = result.scalar_one()

    assert fetched.title == "Bohemian Rhapsody"
    assert fetched.artist == "Queen"
    assert fetched.album == "A Night at the Opera"
    assert fetched.genre == "Rock"
    assert fetched.has_sonic_analysis is True


@pytest.mark.asyncio
async def test_track_unique_rating_key(db_session: AsyncSession) -> None:
    """Inserting two tracks with the same rating_key raises IntegrityError."""
    track1 = Track(
        rating_key=99999,
        title="Track A",
        artist="Artist A",
        has_sonic_analysis=False,
        synced_at=datetime.now(timezone.utc),
    )
    track2 = Track(
        rating_key=99999,
        title="Track B",
        artist="Artist B",
        has_sonic_analysis=False,
        synced_at=datetime.now(timezone.utc),
    )
    db_session.add(track1)
    await db_session.commit()

    db_session.add(track2)
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_track_nullable_fields(db_session: AsyncSession) -> None:
    """Optional fields (album, genre, style) can be None."""
    track = Track(
        rating_key=11111,
        title="Mystery Track",
        artist="Unknown Artist",
        album=None,
        genre=None,
        style=None,
        has_sonic_analysis=False,
        synced_at=datetime.now(timezone.utc),
    )
    db_session.add(track)
    await db_session.commit()

    result = await db_session.execute(select(Track).where(Track.rating_key == 11111))
    fetched = result.scalar_one()

    assert fetched.album is None
    assert fetched.genre is None
    assert fetched.style is None


@pytest.mark.asyncio
async def test_track_repr(db_session: AsyncSession) -> None:
    """Track __repr__ produces a readable string."""
    track = Track(
        rating_key=77777,
        title="Test Song",
        artist="Test Artist",
        has_sonic_analysis=False,
        synced_at=datetime.now(timezone.utc),
    )
    db_session.add(track)
    await db_session.commit()

    assert "Test Song" in repr(track)
    assert "Test Artist" in repr(track)


@pytest.mark.asyncio
async def test_multiple_tracks_query(db_session: AsyncSession) -> None:
    """Multiple tracks can be inserted and queried."""
    tracks = [
        Track(
            rating_key=i,
            title=f"Track {i}",
            artist=f"Artist {i}",
            genre="Rock" if i % 2 == 0 else "Jazz",
            has_sonic_analysis=bool(i % 3),
            synced_at=datetime.now(timezone.utc),
        )
        for i in range(1, 6)
    ]
    db_session.add_all(tracks)
    await db_session.commit()

    result = await db_session.execute(select(Track))
    all_tracks = result.scalars().all()

    assert len(all_tracks) == 5


@pytest.mark.asyncio
async def test_synced_at_default(db_session: AsyncSession) -> None:
    """synced_at defaults to a UTC timestamp when not explicitly set."""
    track = Track(
        rating_key=55555,
        title="Default Time Track",
        artist="Timeless",
        has_sonic_analysis=False,
    )
    db_session.add(track)
    await db_session.commit()

    result = await db_session.execute(select(Track).where(Track.rating_key == 55555))
    fetched = result.scalar_one()

    assert fetched.synced_at is not None
    # Should be very recent (within the last 10 seconds)
    delta = datetime.now(timezone.utc) - fetched.synced_at.replace(tzinfo=timezone.utc)
    assert delta.total_seconds() < 10
