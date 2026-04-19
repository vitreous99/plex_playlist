"""
SQLite library query helpers.

Provides parameterised query functions over the local track cache.
All SQL uses SQLAlchemy ORM expressions to prevent injection attacks.
Results are returned as SQLAlchemy Track ORM objects or plain strings,
never raw Row objects, so callers get typed, predictable results.
"""

from __future__ import annotations

import logging
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

    conditions = []
    for kw in keywords:
        pattern = f"%{kw}%"
        conditions.append(
            or_(
                Track.title.ilike(pattern),
                Track.artist.ilike(pattern),
                Track.genre.ilike(pattern),
                Track.style.ilike(pattern),
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
    """Return a sorted list of all unique artist names in the cache.

    Args:
        session: Async DB session.

    Returns:
        Sorted list of artist name strings.
    """
    stmt = select(Track.artist).distinct().order_by(func.lower(Track.artist))
    result = await session.execute(stmt)
    artists = [row for (row,) in result.all() if row]
    logger.debug("get_distinct_artists() → %d artists.", len(artists))
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
