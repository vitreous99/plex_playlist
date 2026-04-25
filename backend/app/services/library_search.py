"""
SQLite library query helpers.

Provides parameterised query functions over the local track cache.
All SQL uses SQLAlchemy ORM expressions to prevent injection attacks.
Results are returned as SQLAlchemy Track ORM objects or plain strings,
never raw Row objects, so callers get typed, predictable results.
"""

from __future__ import annotations

import logging
import random
from typing import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Track

logger = logging.getLogger(__name__)


async def search_tracks_by_keywords(
    session: AsyncSession,
    keywords: list[str],
    *,
    limit: int = 200,
) -> Sequence[Track]:
    """Return tracks whose title, artist, genre, or style contain any keyword.

    Case-insensitive LIKE matching is used; each keyword is tested against
    all four text columns with OR semantics (any match counts).

    Args:
        session:  Async DB session.
        keywords: List of keyword strings to search for.
        limit:    Maximum number of rows to return (default 200).

    Returns:
        Sequence of matching Track ORM objects.
    """
    if not keywords:
        logger.debug("search_tracks_by_keywords called with empty keywords list.")
        return []

    def _escape_like(kw: str) -> str:
        """Escape LIKE metacharacters so user text is treated as a literal string."""
        return kw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    conditions = []
    for kw in keywords:
        pattern = f"%{_escape_like(kw)}%"
        conditions.append(
            or_(
                Track.title.ilike(pattern, escape="\\"),
                Track.artist.ilike(pattern, escape="\\"),
                Track.genre.ilike(pattern, escape="\\"),
                Track.style.ilike(pattern, escape="\\"),
            )
        )

    stmt = select(Track).where(or_(*conditions)).limit(limit)
    result = await session.execute(stmt)
    rows = result.scalars().all()
    logger.debug(
        "search_tracks_by_keywords(%r) → %d results.", keywords, len(rows)
    )
    return rows


async def get_distinct_artists(session: AsyncSession) -> list[str]:
    """Return a list of all unique artist names in the cache (shuffled for diversity).

    Results are randomized to avoid alphabetical bias in playlist generation.

    Args:
        session: Async DB session.

    Returns:
        List of artist name strings in random order.
    """
    stmt = select(Track.artist).distinct()
    result = await session.execute(stmt)
    artists = [row for (row,) in result.all() if row]
    random.shuffle(artists)
    logger.debug("get_distinct_artists() → %d artists (shuffled).", len(artists))
    return artists


async def get_distinct_genres(session: AsyncSession) -> list[str]:
    """Return a deduplicated, sorted list of all genre tokens in the cache.

    Because genres are stored as comma-separated strings, this function
    splits each value and flattens the result into individual genre tokens.

    Args:
        session: Async DB session.

    Returns:
        Sorted list of unique genre strings.
    """
    stmt = select(Track.genre).where(Track.genre.isnot(None))
    result = await session.execute(stmt)
    genre_set: set[str] = set()
    for (genre_str,) in result.all():
        if genre_str:
            for token in genre_str.split(","):
                stripped = token.strip()
                if stripped:
                    genre_set.add(stripped)
    genres = sorted(genre_set, key=str.lower)
    logger.debug("get_distinct_genres() → %d genres.", len(genres))
    return genres


async def get_artists_by_genres(
    session: AsyncSession,
    genres: list[str],
) -> list[str]:
    """Return distinct artists whose tracks match any of the given genres (shuffled for diversity).

    Filters artists to only those with tracks tagged in the provided genres.
    Results are randomized to avoid alphabetical bias in playlist generation.
    Useful for genre-specific playlist context building.

    Args:
        session: Async DB session.
        genres:  List of genre names to filter by.

    Returns:
        List of unique artist names for tracks in those genres (in random order).
    """
    if not genres:
        logger.debug("get_artists_by_genres called with empty genres list.")
        return []

    # Build OR conditions for each genre (substring match)
    conditions = []
    for genre in genres:
        pattern = f"%{genre}%"
        conditions.append(Track.genre.ilike(pattern))

    stmt = select(Track.artist).distinct().where(or_(*conditions))
    result = await session.execute(stmt)
    artists = [row for (row,) in result.all() if row]
    random.shuffle(artists)
    logger.debug("get_artists_by_genres(%s) → %d artists (shuffled).", genres, len(artists))
    return artists


async def get_tracks_by_artist(
    session: AsyncSession,
    artist: str,
    *,
    limit: int = 500,
) -> Sequence[Track]:
    """Return all tracks by the specified artist (case-insensitive exact match).

    Args:
        session: Async DB session.
        artist:  Artist name to filter by.
        limit:   Maximum number of rows to return.

    Returns:
        Sequence of Track ORM objects for the given artist.
    """
    stmt = (
        select(Track)
        .where(func.lower(Track.artist) == artist.lower())
        .order_by(Track.album, Track.title)
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()
    logger.debug(
        "get_tracks_by_artist(%r) → %d tracks.", artist, len(rows)
    )
    return rows
