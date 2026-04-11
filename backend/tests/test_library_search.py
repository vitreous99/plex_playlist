"""
Tests for the library search query helpers (library_search.py).
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Track
from app.services.library_search import (
    get_distinct_artists,
    get_distinct_genres,
    get_tracks_by_artist,
    search_tracks_by_keywords,
)


async def _seed_tracks(session: AsyncSession) -> None:
    tracks = [
        Track(rating_key=1, title="Bohemian Rhapsody", artist="Queen",
              album="A Night at the Opera", genre="Rock, Progressive Rock",
              style="Classic Rock", has_sonic_analysis=True,
              synced_at=datetime.now(timezone.utc)),
        Track(rating_key=2, title="Thriller", artist="Michael Jackson",
              album="Thriller", genre="Pop, R&B",
              style="Dance Pop", has_sonic_analysis=False,
              synced_at=datetime.now(timezone.utc)),
        Track(rating_key=3, title="Coltrane Blues", artist="John Coltrane",
              album="Blue Train", genre="Jazz, Blues",
              style="Hard Bop", has_sonic_analysis=True,
              synced_at=datetime.now(timezone.utc)),
        Track(rating_key=4, title="We Will Rock You", artist="Queen",
              album="News of the World", genre="Rock, Arena Rock",
              style=None, has_sonic_analysis=False,
              synced_at=datetime.now(timezone.utc)),
        Track(rating_key=5, title="Blue in Green", artist="Miles Davis",
              album="Kind of Blue", genre="Jazz",
              style="Modal Jazz", has_sonic_analysis=True,
              synced_at=datetime.now(timezone.utc)),
    ]
    session.add_all(tracks)
    await session.commit()


@pytest.mark.asyncio
async def test_search_by_title_keyword(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    results = await search_tracks_by_keywords(db_session, ["bohemian"])
    assert len(results) == 1
    assert results[0].title == "Bohemian Rhapsody"


@pytest.mark.asyncio
async def test_search_by_artist_keyword(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    results = await search_tracks_by_keywords(db_session, ["queen"])
    assert len(results) == 2
    assert all(t.artist == "Queen" for t in results)


@pytest.mark.asyncio
async def test_search_by_genre_keyword(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    results = await search_tracks_by_keywords(db_session, ["jazz"])
    titles = {t.title for t in results}
    assert "Coltrane Blues" in titles
    assert "Blue in Green" in titles


@pytest.mark.asyncio
async def test_search_by_style_keyword(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    results = await search_tracks_by_keywords(db_session, ["bop"])
    assert len(results) == 1
    assert results[0].title == "Coltrane Blues"


@pytest.mark.asyncio
async def test_search_multiple_keywords_or_semantics(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    results = await search_tracks_by_keywords(db_session, ["queen", "jazz"])
    titles = {t.title for t in results}
    assert "Bohemian Rhapsody" in titles
    assert "We Will Rock You" in titles
    assert "Coltrane Blues" in titles


@pytest.mark.asyncio
async def test_search_empty_keywords(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    results = await search_tracks_by_keywords(db_session, [])
    assert results == []


@pytest.mark.asyncio
async def test_search_no_match(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    results = await search_tracks_by_keywords(db_session, ["zzznomatch"])
    assert results == []


@pytest.mark.asyncio
async def test_get_distinct_artists_unique(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    artists = await get_distinct_artists(db_session)
    assert artists.count("Queen") == 1
    assert "Michael Jackson" in artists
    assert "John Coltrane" in artists
    assert "Miles Davis" in artists


@pytest.mark.asyncio
async def test_get_distinct_artists_sorted(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    artists = await get_distinct_artists(db_session)
    assert artists == sorted(artists, key=str.lower)


@pytest.mark.asyncio
async def test_get_distinct_artists_empty_db(db_session: AsyncSession) -> None:
    artists = await get_distinct_artists(db_session)
    assert artists == []


@pytest.mark.asyncio
async def test_get_distinct_genres_flattens_csv(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    genres = await get_distinct_genres(db_session)
    assert "Rock" in genres
    assert "Progressive Rock" in genres
    assert "Jazz" in genres
    assert "Blues" in genres


@pytest.mark.asyncio
async def test_get_distinct_genres_no_duplicates(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    genres = await get_distinct_genres(db_session)
    assert genres.count("Rock") == 1


@pytest.mark.asyncio
async def test_get_distinct_genres_sorted(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    genres = await get_distinct_genres(db_session)
    assert genres == sorted(genres, key=str.lower)


@pytest.mark.asyncio
async def test_get_tracks_by_artist_exact_match(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    tracks = await get_tracks_by_artist(db_session, "Queen")
    assert len(tracks) == 2
    assert all(t.artist == "Queen" for t in tracks)


@pytest.mark.asyncio
async def test_get_tracks_by_artist_case_insensitive(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    tracks_lower = await get_tracks_by_artist(db_session, "queen")
    tracks_upper = await get_tracks_by_artist(db_session, "QUEEN")
    assert len(tracks_lower) == len(tracks_upper) == 2


@pytest.mark.asyncio
async def test_get_tracks_by_artist_no_match(db_session: AsyncSession) -> None:
    await _seed_tracks(db_session)
    tracks = await get_tracks_by_artist(db_session, "NonExistentArtist")
    assert tracks == []
